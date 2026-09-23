#!/usr/bin/env python3
"""POC v5 Large Scale — 500 experiences, dual surprise calibration.

Tests two surprise mechanisms head-to-head:
  A. Z-score: running mean/std of prediction error norms (no neural head)
  B. ErrorFamiliarityHead: neural head on [error, error_norm, gate_values]

Both use the SAME signal (prediction error) but process it differently.
Z-score is statistics-only. ErrorFamiliarity is learned.
"""

import json
import os
import sys
import time
import torch
import torch.nn.functional as F
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.experience_model import ExperienceModel

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


def load_jsonl(path):
    items = []
    with open(path) as f:
        for line in f:
            items.append(json.loads(line.strip()))
    return items


TEST_QUERIES = [
    {"query": "fixing JWT token expiry in test suite",
     "ideal": "JWT tokens expire after 3600 seconds. Tests expect valid tokens for full run. Auth refactored to async handlers."},
    {"query": "resolving database connection pool exhaustion",
     "ideal": "Connection pool size 10 exhausts at 50 concurrent users. Each request holds connection during auth check. Consider pgbouncer."},
    {"query": "configuring API rate limiting with Redis",
     "ideal": "Sliding window counter in Redis. 100 requests per minute per API key. Token bucket backend. Burst configurable."},
    {"query": "investigating production memory leak",
     "ideal": "Unbounded LRU cache missing max_size. Grows to 2GB over 24 hours. Redis at 3.2GB of 4GB limit."},
    {"query": "hardening security after vulnerability scan",
     "ideal": "XSS in search endpoint. SQL injection risk. Dependencies have critical CVEs. Input sanitization needed."},
    {"query": "setting up Kubernetes autoscaling",
     "ideal": "HPA scales based on CPU. Pod disruption budget configured. Rolling update strategy. Resource limits per container."},
    {"query": "debugging slow GraphQL queries",
     "ideal": "N+1 query pattern. Missing dataloader. Complexity limit 1000. Depth limit 10. Use composite index."},
    {"query": "configuring monitoring alerts for production",
     "ideal": "Prometheus alerts for error rate, latency, pod restarts. PagerDuty escalation. Grafana dashboards. MTTR targets."},
]


class VectorStore:
    def __init__(self, model):
        self.model = model
        self.entries = []
        self.embs = []

    def store(self, text: str):
        self.entries.append(text)
        self.embs.append(self.model._encode(text))

    def retrieve(self, query: str, top_k: int = 5) -> str:
        q = self.model._encode(query)
        sims = [F.cosine_similarity(q, e).item() for e in self.embs]
        top = sorted(range(len(sims)), key=lambda i: sims[i], reverse=True)[:top_k]
        return " ".join(self.entries[i] for i in top)


def run():
    print("=" * 90)
    print("PExM v5 — DUAL SURPRISE CALIBRATION (Z-score vs ErrorHead)")
    print("=" * 90)

    exp_path = os.path.join(DATA_DIR, "experiences_500.jsonl")
    novel_path = os.path.join(DATA_DIR, "novel_50.jsonl")

    if not os.path.exists(exp_path):
        print("Generating data...")
        exec(open(os.path.join(os.path.dirname(__file__), "generate_experiences.py")).read())

    experiences = load_jsonl(exp_path)
    novels = load_jsonl(novel_path)
    device = "mps" if torch.backends.mps.is_available() else "cpu"

    print(f"Experiences: {len(experiences)}  |  Novel: {len(novels)}  |  Device: {device}")

    print("\nLoading backbone...")
    t0 = time.time()
    model = ExperienceModel(backbone_name="answerdotai/ModernBERT-base",
                            device=device, max_length=256)
    optimizer = model.get_optimizer()
    optimizer.zero_grad()
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"Loaded in {time.time()-t0:.1f}s  |  Trainable: {trainable:,}")

    vs = VectorStore(model)

    # ═════════════════════════════════════════════════════════════════════════
    print(f"\n{'=' * 90}")
    print("PHASE 1: ABSORB 500 EXPERIENCES (3 epochs + replay)")
    print(f"{'=' * 90}")

    checkpoints = []

    for epoch in range(3):
        ep = {"z_surprise": [], "efam": [], "ctx": [], "enorm": []}
        t_ep = time.perf_counter()

        for i, exp in enumerate(experiences):
            m = model.absorb(exp["state"], exp["outcome"])
            model.maybe_optimizer_step(optimizer)

            ep["z_surprise"].append(m["z_surprise"])
            ep["efam"].append(m["error_fam"])
            ep["ctx"].append(m["context_loss"])
            ep["enorm"].append(m["error_norm"])

            if epoch == 0:
                vs.store(exp["outcome"])

            if (i + 1) % 20 == 0 and len(model.replay_buffer) >= 8:
                model.replay_step(batch_size=8)
                model.maybe_optimizer_step(optimizer)

            # Checkpoint during epoch 1
            if epoch == 0 and (i + 1) in [50, 100, 200, 300, 400, 500]:
                optimizer.step(); optimizer.zero_grad()

                k_z = [model.surprise_z(experiences[j]["state"], experiences[j]["outcome"])
                       for j in range(min(10, i + 1))]
                n_z = [model.surprise_z(novels[j]["state"], novels[j]["outcome"])
                       for j in range(10)]
                k_h = [model.surprise_head(experiences[j]["state"], experiences[j]["outcome"])
                       for j in range(min(10, i + 1))]
                n_h = [model.surprise_head(novels[j]["state"], novels[j]["outcome"])
                       for j in range(10)]

                cp = {
                    "n": i + 1,
                    "z_known": float(np.mean(k_z)), "z_novel": float(np.mean(n_z)),
                    "z_sep": float(np.mean(n_z) - np.mean(k_z)),
                    "h_known": float(np.mean(k_h)), "h_novel": float(np.mean(n_h)),
                    "h_sep": float(np.mean(n_h) - np.mean(k_h)),
                    "error_mean": model.error_stats.mean,
                    "error_std": model.error_stats.std(),
                }
                checkpoints.append(cp)
                print(f"    @{i+1:>3}: "
                      f"z[k={np.mean(k_z):.3f} n={np.mean(n_z):.3f} sep={np.mean(n_z)-np.mean(k_z):+.3f}]  "
                      f"h[k={np.mean(k_h):.3f} n={np.mean(n_h):.3f} sep={np.mean(n_h)-np.mean(k_h):+.3f}]  "
                      f"err[mu={model.error_stats.mean:.2f} std={model.error_stats.std():.2f}]")

        optimizer.step(); optimizer.zero_grad()
        elapsed = time.perf_counter() - t_ep
        print(f"\n  Epoch {epoch+1}/3: "
              f"z_surprise={np.mean(ep['z_surprise']):.3f}  "
              f"error_fam={np.mean(ep['efam']):.3f}  "
              f"ctx_loss={np.mean(ep['ctx']):.4f}  "
              f"error_norm={np.mean(ep['enorm']):.2f}  "
              f"{elapsed:.0f}s")

    # Extra replay
    print("\n  80 extra replay steps...")
    for i in range(80):
        model.replay_step(batch_size=8)
        model.maybe_optimizer_step(optimizer)
    optimizer.step(); optimizer.zero_grad()
    print("  Done.")

    # ═════════════════════════════════════════════════════════════════════════
    print(f"\n{'=' * 90}")
    print("PHASE 2: SURPRISE CALIBRATION — HEAD-TO-HEAD COMPARISON")
    print(f"{'=' * 90}")

    n_test = 30

    # Known pairs
    known_z = [model.surprise_z(experiences[i]["state"], experiences[i]["outcome"])
               for i in range(n_test)]
    known_h = [model.surprise_head(experiences[i]["state"], experiences[i]["outcome"])
               for i in range(n_test)]
    known_raw = [model.raw_error_norm(experiences[i]["state"], experiences[i]["outcome"])
                 for i in range(n_test)]

    # Novel pairs
    novel_z = [model.surprise_z(novels[i]["state"], novels[i]["outcome"])
               for i in range(min(n_test, len(novels)))]
    novel_h = [model.surprise_head(novels[i]["state"], novels[i]["outcome"])
               for i in range(min(n_test, len(novels)))]
    novel_raw = [model.raw_error_norm(novels[i]["state"], novels[i]["outcome"])
                 for i in range(min(n_test, len(novels)))]

    # Shuffled (mismatched state/outcome from known)
    shuffled_z, shuffled_h, shuffled_raw = [], [], []
    for i in range(n_test):
        j = (i + 17) % len(experiences)
        shuffled_z.append(model.surprise_z(experiences[i]["state"], experiences[j]["outcome"]))
        shuffled_h.append(model.surprise_head(experiences[i]["state"], experiences[j]["outcome"]))
        shuffled_raw.append(model.raw_error_norm(experiences[i]["state"], experiences[j]["outcome"]))

    print(f"\n  METHOD A: Z-SCORE SURPRISE (0=familiar, 1=novel)")
    print(f"  {'Category':<25} {'Mean':>8} {'Std':>8} {'Min':>8} {'Max':>8}")
    print(f"  {'─' * 57}")
    for name, vals in [("Known (n=30)", known_z), ("Novel (n=30)", novel_z),
                       ("Shuffled (n=30)", shuffled_z)]:
        print(f"  {name:<25} {np.mean(vals):>8.4f} {np.std(vals):>8.4f} "
              f"{np.min(vals):>8.4f} {np.max(vals):>8.4f}")
    z_sep_novel = np.mean(novel_z) - np.mean(known_z)
    z_sep_shuffled = np.mean(shuffled_z) - np.mean(known_z)
    print(f"  Separation known→novel:    {z_sep_novel:+.4f}")
    print(f"  Separation known→shuffled: {z_sep_shuffled:+.4f}")

    print(f"\n  METHOD B: ERROR-FAMILIARITY HEAD (0=familiar, 1=novel)")
    print(f"  {'Category':<25} {'Mean':>8} {'Std':>8} {'Min':>8} {'Max':>8}")
    print(f"  {'─' * 57}")
    for name, vals in [("Known (n=30)", known_h), ("Novel (n=30)", novel_h),
                       ("Shuffled (n=30)", shuffled_h)]:
        print(f"  {name:<25} {np.mean(vals):>8.4f} {np.std(vals):>8.4f} "
              f"{np.min(vals):>8.4f} {np.max(vals):>8.4f}")
    h_sep_novel = np.mean(novel_h) - np.mean(known_h)
    h_sep_shuffled = np.mean(shuffled_h) - np.mean(known_h)
    print(f"  Separation known→novel:    {h_sep_novel:+.4f}")
    print(f"  Separation known→shuffled: {h_sep_shuffled:+.4f}")

    print(f"\n  RAW ERROR NORM (for reference)")
    print(f"  {'Category':<25} {'Mean':>8} {'Std':>8}")
    print(f"  {'─' * 41}")
    for name, vals in [("Known", known_raw), ("Novel", novel_raw), ("Shuffled", shuffled_raw)]:
        print(f"  {name:<25} {np.mean(vals):>8.2f} {np.std(vals):>8.2f}")
    print(f"  Running stats: mean={model.error_stats.mean:.2f}  std={model.error_stats.std():.2f}  n={model.error_stats.n}")

    # Determine winner
    print(f"\n  {'─' * 60}")
    print(f"  VERDICT:")
    z_works = z_sep_novel > 0.05
    h_works = h_sep_novel > 0.05
    if z_works and h_works:
        winner = "Z-SCORE" if z_sep_novel > h_sep_novel else "ERROR-HEAD"
        print(f"  Both work! Winner: {winner}")
        print(f"    Z-score separation:    {z_sep_novel:+.4f}")
        print(f"    Error-head separation: {h_sep_novel:+.4f}")
    elif z_works:
        print(f"  Z-SCORE WINS (sep={z_sep_novel:+.4f}). Error-head failed (sep={h_sep_novel:+.4f})")
    elif h_works:
        print(f"  ERROR-HEAD WINS (sep={h_sep_novel:+.4f}). Z-score failed (sep={z_sep_novel:+.4f})")
    else:
        print(f"  BOTH FAIL. Z-score sep={z_sep_novel:+.4f}, Error-head sep={h_sep_novel:+.4f}")
        print(f"  Raw error norm: known={np.mean(known_raw):.2f} vs novel={np.mean(novel_raw):.2f}")
        if np.mean(novel_raw) > np.mean(known_raw):
            print(f"  NOTE: Raw error norms DO separate — the normalization/head is the problem")
        else:
            print(f"  NOTE: Even raw error norms don't separate — the prediction head has issues")

    # ═════════════════════════════════════════════════════════════════════════
    print(f"\n{'=' * 90}")
    print("PHASE 3: CONTEXT QUALITY")
    print(f"{'=' * 90}")

    results = {"pexm": [], "vector": [], "none": []}
    for tq in TEST_QUERIES:
        q_emb = model._encode(tq["query"])
        i_emb = model._encode(tq["ideal"])
        results["none"].append(F.cosine_similarity(q_emb, i_emb).item())
        ret = vs.retrieve(tq["query"], top_k=5)
        results["vector"].append(F.cosine_similarity(model._encode(ret), i_emb).item())
        results["pexm"].append(model.context_similarity(tq["query"], tq["ideal"]))

    print(f"\n  {'Condition':<25} {'Mean':>8} {'Min':>8} {'Max':>8}")
    print(f"  {'─' * 49}")
    for c in ["none", "vector", "pexm"]:
        label = {"none": "No Memory", "vector": "Vector (top-5)", "pexm": "PExM v5"}[c]
        v = results[c]
        print(f"  {label:<25} {np.mean(v):>8.4f} {np.min(v):>8.4f} {np.max(v):>8.4f}")
    d_pv = np.mean(results["pexm"]) - np.mean(results["vector"])
    wins = sum(1 for i in range(len(TEST_QUERIES)) if results["pexm"][i] > results["vector"][i])
    print(f"\n  PExM vs Vector: {d_pv:+.4f}  |  Wins: {wins}/{len(TEST_QUERIES)}")

    # ═════════════════════════════════════════════════════════════════════════
    print(f"\n{'=' * 90}")
    print("PHASE 4: LATENCY")
    print(f"{'=' * 90}")

    model.generate(TEST_QUERIES[0]["query"])

    at = []
    for exp in experiences[:20]:
        t0 = time.perf_counter()
        model.absorb(exp["state"], exp["outcome"])
        model.maybe_optimizer_step(optimizer)
        at.append((time.perf_counter() - t0) * 1000)
    optimizer.step(); optimizer.zero_grad()

    gt = []
    for tq in TEST_QUERIES:
        t0 = time.perf_counter(); model.generate(tq["query"]); gt.append((time.perf_counter() - t0) * 1000)

    sz = []
    for exp in experiences[:20]:
        t0 = time.perf_counter(); model.surprise_z(exp["state"], exp["outcome"]); sz.append((time.perf_counter() - t0) * 1000)

    sh = []
    for exp in experiences[:20]:
        t0 = time.perf_counter(); model.surprise_head(exp["state"], exp["outcome"]); sh.append((time.perf_counter() - t0) * 1000)

    rt = []
    for tq in TEST_QUERIES:
        t0 = time.perf_counter(); vs.retrieve(tq["query"]); rt.append((time.perf_counter() - t0) * 1000)

    print(f"  Absorb:       p50={np.median(at):.0f}ms")
    print(f"  Generate:     p50={np.median(gt):.0f}ms")
    print(f"  Surprise(z):  p50={np.median(sz):.0f}ms")
    print(f"  Surprise(h):  p50={np.median(sh):.0f}ms")
    print(f"  Retrieve:     p50={np.median(rt):.0f}ms  (500 entries)")

    # ═════════════════════════════════════════════════════════════════════════
    print(f"\n{'=' * 90}")
    print("PHASE 5: SATURATION + FORGETTING")
    print(f"{'=' * 90}")

    sat = model.stream_saturation()
    print(f"  Experiences: {sat['experience_count']}  |  Buffer: {len(model.replay_buffer)}")
    print(f"  Streams: fast={sat['norms']['fast']:.3f}  med={sat['norms']['medium']:.3f}  slow={sat['norms']['slow']:.4f}")

    # Forgetting
    old_sim = model.context_similarity("checking auth config",
        "JWT tokens with RS256 signing and 3600 second expiry")
    for _ in range(8):
        model.absorb("auth module rewritten",
            "Now uses OAuth2 with PKCE. JWT replaced with opaque tokens. Sessions in PostgreSQL.")
        model.maybe_optimizer_step(optimizer)
    optimizer.step(); optimizer.zero_grad()
    new_sim = model.context_similarity("checking auth config",
        "JWT tokens with RS256 signing and 3600 second expiry")
    oauth_sim = model.context_similarity("checking auth config",
        "OAuth2 with PKCE. Opaque tokens. Sessions in PostgreSQL.")
    print(f"  Forgetting: JWT {old_sim:.4f}->{new_sim:.4f}  OAuth2={oauth_sim:.4f}  "
          f"{'PASS' if oauth_sim > new_sim else 'FAIL'}")

    # ═════════════════════════════════════════════════════════════════════════
    print(f"\n{'=' * 90}")
    print("SCALING CURVE (surprise evolution during epoch 1)")
    print(f"{'=' * 90}")
    print(f"\n  {'N':>5} {'Z known':>8} {'Z novel':>8} {'Z sep':>8} "
          f"{'H known':>8} {'H novel':>8} {'H sep':>8} {'err_mu':>8} {'err_std':>8}")
    print(f"  {'─' * 80}")
    for cp in checkpoints:
        print(f"  {cp['n']:>5} {cp['z_known']:>8.4f} {cp['z_novel']:>8.4f} {cp['z_sep']:>+8.4f} "
              f"{cp['h_known']:>8.4f} {cp['h_novel']:>8.4f} {cp['h_sep']:>+8.4f} "
              f"{cp['error_mean']:>8.2f} {cp['error_std']:>8.2f}")

    # ═════════════════════════════════════════════════════════════════════════
    print(f"\n{'=' * 90}")
    print("VERSION HISTORY")
    print(f"{'=' * 90}")
    print(f"\n  {'Metric':<35} {'v1':>8} {'v2':>8} {'v3':>8} {'v4':>8} {'v5':>8}")
    print(f"  {'─' * 75}")
    print(f"  {'Context sim (mean)':<35} {'0.029':>8} {'0.985':>8} {'0.978':>8} {'0.979':>8} {np.mean(results['pexm']):>8.3f}")
    print(f"  {'PExM wins / queries':<35} {'0/5':>8} {'5/5':>8} {'7/8':>8} {'8/8':>8} {f'{wins}/{len(TEST_QUERIES)}':>8}")
    z_verdict = f"{z_sep_novel:+.3f}" if z_works else "FAIL"
    h_verdict = f"{h_sep_novel:+.3f}" if h_works else "FAIL"
    print(f"  {'Surprise sep (z-score)':<35} {'N/A':>8} {'N/A':>8} {'N/A':>8} {'N/A':>8} {z_verdict:>8}")
    print(f"  {'Surprise sep (error-head)':<35} {'N/A':>8} {'N/A':>8} {'N/A':>8} {'FAIL':>8} {h_verdict:>8}")
    print(f"  {'Generate latency':<35} {'403ms':>8} {'207ms':>8} {'121ms':>8} {'119ms':>8} {f'{np.median(gt):.0f}ms':>8}")
    print(f"  {'Experiences':<35} {'15':>8} {'15':>8} {'60':>8} {'500':>8} {'500':>8}")

    # Save
    output = {
        "version": "v5",
        "calibration": {
            "z_score": {"known": float(np.mean(known_z)), "novel": float(np.mean(novel_z)),
                        "shuffled": float(np.mean(shuffled_z)),
                        "sep_novel": float(z_sep_novel), "sep_shuffled": float(z_sep_shuffled),
                        "works": bool(z_works)},
            "error_head": {"known": float(np.mean(known_h)), "novel": float(np.mean(novel_h)),
                           "shuffled": float(np.mean(shuffled_h)),
                           "sep_novel": float(h_sep_novel), "sep_shuffled": float(h_sep_shuffled),
                           "works": bool(h_works)},
            "raw_norms": {"known": float(np.mean(known_raw)), "novel": float(np.mean(novel_raw)),
                          "shuffled": float(np.mean(shuffled_raw))},
        },
        "context_quality": {"pexm": float(np.mean(results["pexm"])),
                            "vector": float(np.mean(results["vector"])),
                            "delta": float(d_pv), "wins": wins},
        "latency": {"absorb": float(np.median(at)), "generate": float(np.median(gt)),
                    "surprise_z": float(np.median(sz)), "surprise_h": float(np.median(sh)),
                    "retrieve": float(np.median(rt))},
        "checkpoints": checkpoints,
        "diagnostics": model.diagnostics(),
    }
    out_path = os.path.join(DATA_DIR, "poc_v5_results.json")
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nSaved to {out_path}")
    print("Done.")


if __name__ == "__main__":
    run()
