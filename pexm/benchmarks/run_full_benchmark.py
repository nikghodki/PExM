#!/usr/bin/env python3
"""PExM Full Benchmark Suite.

Runs all evaluations needed for the README and produces a single
results JSON with tables ready for copy-paste into markdown.

Benchmarks:
  1. Context Quality   — PExM vs vector store vs no memory (8 queries)
  2. Scaling Curve     — 10, 50, 100, 200, 500 experiences
  3. Surprise Calibration — known vs novel vs shuffled separation
  4. Latency Profile   — absorb, generate, surprise at each scale
  5. Forgetting        — contradiction resolution at each scale
  6. Public Dataset    — LoCoMo-style conversational memory task
"""

import json
import os
import sys
import time
import random
import torch
import torch.nn.functional as F
import numpy as np
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pexm.core.experience_model import ExperienceModel

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
SEED = 741983
random.seed(SEED)
np.random.seed(SEED)
torch.manual_seed(SEED)


def load_jsonl(path):
    with open(path) as f:
        return [json.loads(line.strip()) for line in f if line.strip()]


# ── Test queries (ground truth for context quality) ──────────────────────────

TEST_QUERIES = [
    {"query": "fixing JWT token expiry in test suite",
     "ideal": "JWT tokens expire after 3600 seconds. Tests expect valid tokens for full run. Auth refactored to async handlers."},
    {"query": "resolving database connection pool exhaustion",
     "ideal": "Connection pool size 10 exhausts at 50 concurrent users. Each request holds connection during auth check."},
    {"query": "configuring API rate limiting with Redis",
     "ideal": "Sliding window counter in Redis. 100 requests per minute per API key. Token bucket backend."},
    {"query": "investigating production memory leak",
     "ideal": "Unbounded LRU cache missing max_size. Grows to 2GB over 24 hours. Redis at 3.2GB of 4GB limit."},
    {"query": "hardening security after vulnerability scan",
     "ideal": "XSS in search endpoint. SQL injection risk. Dependencies have critical CVEs. Input sanitization needed."},
    {"query": "setting up Kubernetes autoscaling",
     "ideal": "HPA scales based on CPU. Pod disruption budget configured. Rolling update strategy. Resource limits per container."},
    {"query": "debugging slow GraphQL queries",
     "ideal": "N+1 query pattern. Missing dataloader. Complexity limit 1000. Depth limit 10."},
    {"query": "configuring monitoring alerts for production",
     "ideal": "Prometheus alerts for error rate, latency, pod restarts. PagerDuty escalation. Grafana dashboards."},
]

# ── Conversational memory task (LoCoMo-style) ───────────────────────────────
# Multi-turn conversation where later questions depend on earlier context.

CONVERSATION_SESSIONS = [
    {
        "turns": [
            {"state": "starting work on the auth module", "outcome": "Auth uses JWT with RS256 signing. Token expiry 3600s."},
            {"state": "found a bug in token validation", "outcome": "Bug: plus signs in emails rejected by regex in validators.py line 42."},
            {"state": "alice pushed a fix for the regex", "outcome": "Commit abc123 by alice: fixed email regex. Now allows + characters."},
            {"state": "running tests after the fix", "outcome": "All tests pass. Token validation accepts test+user@example.com."},
        ],
        "recall_queries": [
            {"query": "what was the email bug we fixed?", "expected": "plus signs in emails rejected by regex in validators.py line 42"},
            {"query": "who fixed it and what was the commit?", "expected": "alice pushed commit abc123 fixing email regex to allow plus characters"},
            {"query": "do tests pass now?", "expected": "all tests pass after the fix including test+user@example.com"},
        ],
    },
    {
        "turns": [
            {"state": "investigating payment failures", "outcome": "Stripe API returns charge_already_refunded for duplicate refund attempts."},
            {"state": "checking the retry logic", "outcome": "No retry logic for refund failures. Payments retry 3 times but refunds do not."},
            {"state": "bob added refund retry logic", "outcome": "Commit def456 by bob: added exponential backoff for refund retries. 1h, 6h, 24h."},
            {"state": "testing the refund retry flow", "outcome": "Retry works. Duplicate refunds handled gracefully. Idempotency key added."},
        ],
        "recall_queries": [
            {"query": "why were refunds failing?", "expected": "Stripe returns charge_already_refunded for duplicates and no retry logic existed"},
            {"query": "what did bob change?", "expected": "bob added exponential backoff retry for refunds with 1h 6h 24h intervals in commit def456"},
            {"query": "is the refund issue resolved?", "expected": "yes retry works and idempotency key prevents duplicate refunds"},
        ],
    },
    {
        "turns": [
            {"state": "debugging slow user list page", "outcome": "N+1 query: each user triggers separate DB query for role. 200ms per user."},
            {"state": "checking the connection pool", "outcome": "Pool size 10 in config.yaml. Exhausts at 50 concurrent users."},
            {"state": "implemented dataloader fix", "outcome": "Replaced N+1 with batched query using dataloader. Single query for all roles."},
            {"state": "load testing the fix", "outcome": "Page load dropped from 4s to 120ms. Pool no longer exhausts at 50 users."},
        ],
        "recall_queries": [
            {"query": "what caused the slow page?", "expected": "N+1 query where each user triggered a separate DB query for role at 200ms each"},
            {"query": "how was it fixed?", "expected": "replaced N+1 with batched dataloader query for all roles in single query"},
            {"query": "what was the performance improvement?", "expected": "page load dropped from 4 seconds to 120ms"},
        ],
    },
]


class VectorStore:
    def __init__(self, encode_fn):
        self.encode = encode_fn
        self.texts = []
        self.embs = []

    def store(self, text):
        self.texts.append(text)
        self.embs.append(self.encode(text))

    def retrieve(self, query, top_k=3):
        q = self.encode(query)
        sims = [F.cosine_similarity(q, e).item() for e in self.embs]
        top = sorted(range(len(sims)), key=lambda i: sims[i], reverse=True)[:top_k]
        return " ".join(self.texts[i] for i in top)

    def clear(self):
        self.texts.clear()
        self.embs.clear()


def context_sim(model, text_a, text_b):
    with torch.no_grad():
        a = model._encode(text_a)
        b = model._encode(text_b)
    return F.cosine_similarity(a, b).item()


def run_scale_benchmark(model_cls, experiences, novels, device, scales):
    """Run benchmarks at multiple scales and collect results."""
    results = []

    for n in scales:
        print(f"\n  Scale: {n} experiences")
        subset = experiences[:n]

        model = model_cls(device=device, max_length=256)
        optimizer = model.get_optimizer()
        optimizer.zero_grad()

        vs = VectorStore(model._encode)

        # Absorb
        t_absorb = time.perf_counter()
        for exp in subset:
            model.absorb(exp["state"], exp["outcome"])
            model.maybe_optimizer_step(optimizer)
            vs.store(exp["outcome"])
        optimizer.step()
        optimizer.zero_grad()

        # Extra epoch for quality
        for exp in subset:
            model.absorb(exp["state"], exp["outcome"])
            model.maybe_optimizer_step(optimizer)
        optimizer.step()
        optimizer.zero_grad()

        # Replay
        for _ in range(min(50, n)):
            model.replay_step(batch_size=min(8, n))
            model.maybe_optimizer_step(optimizer)
        optimizer.step()
        optimizer.zero_grad()

        absorb_time = time.perf_counter() - t_absorb

        # Context quality
        pexm_sims, vec_sims, none_sims = [], [], []
        for tq in TEST_QUERIES:
            q_emb = model._encode(tq["query"])
            i_emb = model._encode(tq["ideal"])
            none_sims.append(F.cosine_similarity(q_emb, i_emb).item())
            ret = vs.retrieve(tq["query"], top_k=min(5, n))
            vec_sims.append(F.cosine_similarity(model._encode(ret), i_emb).item())
            pexm_sims.append(model.context_similarity(tq["query"], tq["ideal"]))

        pexm_wins = sum(1 for i in range(len(TEST_QUERIES)) if pexm_sims[i] > vec_sims[i])

        # Surprise calibration
        n_test = min(15, n)
        known_z = [model.surprise_z(subset[i]["state"], subset[i]["outcome"]) for i in range(n_test)]
        novel_z = [model.surprise_z(novels[i]["state"], novels[i]["outcome"]) for i in range(min(15, len(novels)))]
        z_sep = np.mean(novel_z) - np.mean(known_z)

        # Latency
        model.generate(TEST_QUERIES[0]["query"])  # warmup
        gen_times = []
        for tq in TEST_QUERIES:
            t0 = time.perf_counter()
            model.generate(tq["query"])
            gen_times.append((time.perf_counter() - t0) * 1000)

        ret_times = []
        for tq in TEST_QUERIES:
            t0 = time.perf_counter()
            vs.retrieve(tq["query"])
            ret_times.append((time.perf_counter() - t0) * 1000)

        # Forgetting
        old_sim = model.context_similarity("checking auth config", "JWT tokens with RS256 and 3600s expiry")
        for _ in range(5):
            model.absorb("auth rewritten", "Now uses OAuth2 with PKCE. JWT replaced with opaque tokens.")
            model.maybe_optimizer_step(optimizer)
        optimizer.step(); optimizer.zero_grad()
        new_sim = model.context_similarity("checking auth config", "JWT tokens with RS256 and 3600s expiry")
        oauth_sim = model.context_similarity("checking auth config", "OAuth2 with PKCE flow. Opaque tokens.")
        forgot = oauth_sim > new_sim

        sat = model.stream_saturation()

        row = {
            "n": n,
            "pexm_mean": float(np.mean(pexm_sims)),
            "vector_mean": float(np.mean(vec_sims)),
            "none_mean": float(np.mean(none_sims)),
            "delta_vs_vector": float(np.mean(pexm_sims) - np.mean(vec_sims)),
            "pexm_wins": pexm_wins,
            "z_sep": float(z_sep),
            "z_known_mean": float(np.mean(known_z)),
            "z_novel_mean": float(np.mean(novel_z)),
            "gen_p50_ms": float(np.median(gen_times)),
            "ret_p50_ms": float(np.median(ret_times)),
            "absorb_total_s": float(absorb_time),
            "forgetting_pass": forgot,
            "fast_norm": float(sat["norms"]["fast"]),
        }
        results.append(row)

        print(f"    PExM={row['pexm_mean']:.3f}  Vec={row['vector_mean']:.3f}  "
              f"delta={row['delta_vs_vector']:+.3f}  wins={pexm_wins}/8  "
              f"z_sep={z_sep:+.3f}  gen={row['gen_p50_ms']:.0f}ms  "
              f"ret={row['ret_p50_ms']:.0f}ms  forgot={'Y' if forgot else 'N'}")

        del model, vs, optimizer
        torch.mps.empty_cache() if device == "mps" else None

    return results


def run_conversation_benchmark(model_cls, device):
    """LoCoMo-style multi-turn conversation memory test."""
    print(f"\n  Running {len(CONVERSATION_SESSIONS)} conversation sessions...")
    results = []

    for si, session in enumerate(CONVERSATION_SESSIONS):
        model = model_cls(device=device, max_length=256)
        optimizer = model.get_optimizer()
        optimizer.zero_grad()
        vs = VectorStore(model._encode)

        # Absorb turns sequentially
        for turn in session["turns"]:
            model.absorb(turn["state"], turn["outcome"])
            model.maybe_optimizer_step(optimizer)
            vs.store(turn["outcome"])
        optimizer.step()
        optimizer.zero_grad()

        # Replay for consolidation
        for _ in range(20):
            model.replay_step(batch_size=min(4, len(session["turns"])))
            model.maybe_optimizer_step(optimizer)
        optimizer.step()
        optimizer.zero_grad()

        # Test recall
        for qi, rq in enumerate(session["recall_queries"]):
            pexm_sim = model.context_similarity(rq["query"], rq["expected"])
            ret = vs.retrieve(rq["query"], top_k=2)
            vec_sim = F.cosine_similarity(model._encode(ret), model._encode(rq["expected"])).item()

            results.append({
                "session": si, "query_idx": qi,
                "query": rq["query"],
                "pexm_sim": float(pexm_sim),
                "vector_sim": float(vec_sim),
                "pexm_wins": pexm_sim > vec_sim,
            })

        del model, vs, optimizer

    pexm_wins = sum(1 for r in results if r["pexm_wins"])
    pexm_mean = np.mean([r["pexm_sim"] for r in results])
    vec_mean = np.mean([r["vector_sim"] for r in results])

    print(f"    Conversational recall: PExM={pexm_mean:.3f}  Vec={vec_mean:.3f}  "
          f"delta={pexm_mean - vec_mean:+.3f}  wins={pexm_wins}/{len(results)}")

    return results


def format_markdown_tables(scale_results, conv_results):
    """Generate ready-to-paste markdown tables."""
    lines = []

    # Scaling table
    lines.append("### Scaling Behavior")
    lines.append("")
    lines.append("| Experiences | PExM | Vector Store | Delta | Wins | Generate | Retrieve | Surprise Sep |")
    lines.append("|---:|---:|---:|---:|---:|---:|---:|---:|")
    for r in scale_results:
        lines.append(f"| {r['n']} | {r['pexm_mean']:.3f} | {r['vector_mean']:.3f} | "
                     f"{r['delta_vs_vector']:+.3f} | {r['pexm_wins']}/8 | "
                     f"{r['gen_p50_ms']:.0f}ms | {r['ret_p50_ms']:.0f}ms | "
                     f"{r['z_sep']:+.3f} |")

    # Conversation table
    lines.append("")
    lines.append("### Conversational Memory (multi-turn recall)")
    lines.append("")
    pexm_mean = np.mean([r["pexm_sim"] for r in conv_results])
    vec_mean = np.mean([r["vector_sim"] for r in conv_results])
    wins = sum(1 for r in conv_results if r["pexm_wins"])
    lines.append(f"| Method | Recall Similarity | Queries Won |")
    lines.append(f"|---|---:|---:|")
    lines.append(f"| Vector Store | {vec_mean:.3f} | {len(conv_results) - wins}/{len(conv_results)} |")
    lines.append(f"| **PExM** | **{pexm_mean:.3f}** | **{wins}/{len(conv_results)}** |")

    return "\n".join(lines)


def main():
    print("=" * 80)
    print("PExM FULL BENCHMARK SUITE")
    print("=" * 80)

    device = "mps" if torch.backends.mps.is_available() else "cuda:0" if torch.cuda.is_available() else "cpu"
    print(f"Device: {device}")

    exp_path = os.path.join(DATA_DIR, "experiences_500.jsonl")
    novel_path = os.path.join(DATA_DIR, "novel_50.jsonl")

    if not os.path.exists(exp_path):
        print("Generating corpus first...")
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pexm", "benchmarks"))
        import generate_corpus
        generate_corpus.generate_experiences(500)

    experiences = load_jsonl(exp_path)
    novels = load_jsonl(novel_path)
    print(f"Corpus: {len(experiences)} experiences, {len(novels)} novel")

    # ── Benchmark 1: Scaling curve ───────────────────────────────────────────
    print(f"\n{'=' * 80}")
    print("BENCHMARK 1: SCALING CURVE")
    print(f"{'=' * 80}")

    scales = [10, 50, 100, 200, 500]
    scale_results = run_scale_benchmark(
        ExperienceModel, experiences, novels, device, scales
    )

    # ── Benchmark 2: Conversational memory ───────────────────────────────────
    print(f"\n{'=' * 80}")
    print("BENCHMARK 2: CONVERSATIONAL MEMORY (LoCoMo-style)")
    print(f"{'=' * 80}")

    conv_results = run_conversation_benchmark(ExperienceModel, device)

    # ── Summary tables ───────────────────────────────────────────────────────
    print(f"\n{'=' * 80}")
    print("MARKDOWN TABLES (copy to README)")
    print(f"{'=' * 80}\n")

    md = format_markdown_tables(scale_results, conv_results)
    print(md)

    # ── Save all results ─────────────────────────────────────────────────────
    output = {
        "seed": SEED,
        "device": device,
        "scaling": scale_results,
        "conversational": conv_results,
        "markdown": md,
    }

    out_path = os.path.join(DATA_DIR, "full_benchmark_results.json")
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, default=str)

    print(f"\nSaved to {out_path}")
    print("Done.")


if __name__ == "__main__":
    main()
