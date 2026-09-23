#!/usr/bin/env python3
"""Side-by-side comparison: Engram vs naive vector store retrieval.

Absorbs the same experiences into both systems, then measures which
produces better context for 5 test queries.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import torch
import torch.nn.functional as F
from engram.core import ExperienceModel


EXPERIENCES = [
    ("reading auth.py", "JWT tokens with RS256. Expire after 3600s. Refresh in Redis, 7-day TTL."),
    ("debugging login failure", "Email validator regex rejects plus signs. validators.py line 42."),
    ("running tests after auth changes", "3 tests failed. Token expiry causes mid-suite failures."),
    ("checking git log", "alice: refactored auth to async. bob: added rate limiting to login."),
    ("reviewing payment service", "Stripe API v2023-10-16. Webhook validates signatures."),
    ("debugging connection pool", "Pool exhaustion at 50 users. Pool size 10. Holds during auth check."),
    ("reading deployment config", "Kubernetes, 3 replicas. HPA 3-10 on CPU. Rolling update."),
    ("reviewing rate limiting", "Sliding window in Redis. 100 req/min per API key."),
    ("investigating memory spike", "Unbounded LRU cache in search_service.py. Grows to 2GB."),
    ("checking error handling", "Auth: custom exceptions. Payment: HTTP codes. Search: silences all."),
]

QUERIES = [
    ("fixing auth token expiry in tests",
     "JWT tokens expire after 3600s. Tests expect valid tokens for full run. Auth refactored to async."),
    ("optimizing database performance",
     "Connection pool size 10 exhausts at 50 users. Holds during auth check."),
    ("setting up rate limiting",
     "Sliding window in Redis. 100 req/min per API key. Rate limiting added to login."),
    ("debugging memory leak",
     "Unbounded LRU cache in search_service.py. Grows to 2GB over 24 hours."),
    ("improving error handling",
     "Auth uses custom exceptions. Payment uses HTTP codes. Search silences all."),
]


class SimpleVectorStore:
    def __init__(self, encode_fn):
        self._encode = encode_fn
        self.texts = []
        self.embs = []

    def store(self, text):
        self.texts.append(text)
        self.embs.append(self._encode(text))

    def retrieve(self, query, top_k=3):
        q = self._encode(query)
        sims = [F.cosine_similarity(q, e).item() for e in self.embs]
        top = sorted(range(len(sims)), key=lambda i: sims[i], reverse=True)[:top_k]
        return " ".join(self.texts[i] for i in top)


def main():
    device = "mps" if torch.backends.mps.is_available() else "cuda:0" if torch.cuda.is_available() else "cpu"
    print(f"Device: {device}\n")

    model = ExperienceModel(device=device)
    optimizer = model.get_optimizer()
    optimizer.zero_grad()

    vs = SimpleVectorStore(model._encode)

    print(f"Absorbing {len(EXPERIENCES)} experiences into both systems...\n")
    for state, outcome in EXPERIENCES:
        model.absorb(state, outcome)
        model.maybe_optimizer_step(optimizer)
        vs.store(outcome)
    optimizer.step()
    optimizer.zero_grad()

    engram_wins = 0
    print(f"{'Query':<40} {'No Mem':>7} {'Vector':>7} {'Engram':>7} {'Winner'}")
    print("-" * 75)

    for query, ideal in QUERIES:
        with torch.no_grad():
            q_emb = model._encode(query)
            ideal_emb = model._encode(ideal)

        none_sim = F.cosine_similarity(q_emb, ideal_emb).item()

        retrieved = vs.retrieve(query, top_k=3)
        vec_sim = F.cosine_similarity(model._encode(retrieved), ideal_emb).item()

        eng_sim = model.context_similarity(query, ideal)

        winner = "ENGRAM" if eng_sim > vec_sim else "VECTOR"
        if eng_sim > vec_sim:
            engram_wins += 1

        print(f"{query:<40} {none_sim:>7.3f} {vec_sim:>7.3f} {eng_sim:>7.3f}   {winner}")

    print(f"\nEngram wins: {engram_wins}/{len(QUERIES)}")


if __name__ == "__main__":
    main()
