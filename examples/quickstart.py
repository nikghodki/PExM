#!/usr/bin/env python3
"""PExM quickstart — absorb experiences, query for context, check surprise."""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import torch
from pexm.core import ExperienceModel

def main():
    device = "mps" if torch.backends.mps.is_available() else "cuda:0" if torch.cuda.is_available() else "cpu"
    print(f"Loading PExM on {device}...\n")

    model = ExperienceModel(device=device)
    optimizer = model.get_optimizer()
    optimizer.zero_grad()

    # Absorb coding experiences
    experiences = [
        ("reading the auth module",
         "Uses JWT with RS256 signing. Tokens expire after 3600 seconds. Refresh tokens stored in Redis with 7-day TTL."),
        ("debugging the login failure",
         "Email validator regex rejects plus signs. Fix is in validators.py line 42. Need to escape the + character."),
        ("running tests after auth changes",
         "3 tests failed in test_auth.py. Token expiry causes mid-suite failures. Tests assume tokens valid for full run."),
        ("checking git log on auth module",
         "alice refactored auth to async handlers in commit abc123. bob added rate limiting to login endpoint in def456."),
        ("reviewing the payment webhook",
         "Stripe API v2023-10-16. Webhook handler in payments/webhook.py validates HMAC signatures before processing events."),
        ("debugging database connection pool",
         "Pool exhaustion at 50 concurrent users. Pool size is 10 in config.yaml. Each request holds connection during full auth check."),
        ("investigating the memory leak",
         "Unbounded LRU cache in search_service.py. Missing max_size parameter. Grows to 2GB over 24 hours in production."),
        ("reading the rate limiting config",
         "Sliding window counter in Redis. Default 100 requests per minute per API key. Configured in middleware/ratelimit.py."),
    ]

    print(f"Absorbing {len(experiences)} experiences...")
    for state, outcome in experiences:
        m = model.absorb(state, outcome)
        model.maybe_step(optimizer)
        print(f"  surprise={m['surprise']:.3f}  loss={m['loss']:.4f}")
    optimizer.step()
    optimizer.zero_grad()

    # Query — returns readable text
    print("\n--- Query: 'fixing auth token expiry in tests' ---")
    result = model.query("fixing auth token expiry in tests", top_k=3)
    print(f"Confidence: {result['confidence']:.3f}  |  Latency: {result['latency_ms']:.0f}ms\n")
    print("Context (inject this into your agent's prompt):")
    print(result["context"])
    print()
    for exp in result["experiences"]:
        print(f"  [{exp['score']:.3f}] {exp['outcome'][:70]}...")

    # Another query
    print("\n--- Query: 'payment webhook is failing' ---")
    result2 = model.query("payment webhook is failing", top_k=3)
    print(f"Context:\n{result2['context']}\n")

    # Surprise: is this novel?
    print("--- Surprise ---")
    s1 = model.surprise("reading the auth module", "Uses JWT with RS256 signing")
    s2 = model.surprise("checking the Kubernetes operator", "CRD reconciliation every 30 seconds")
    print(f"Known (auth/JWT):     {s1:.3f}")
    print(f"Novel (k8s operator): {s2:.3f}")
    print(f"Is k8s info novel?    {model.is_novel('checking k8s', 'CRD reconciliation every 30s')}")

    print(f"\nStored: {model.n_stored} experiences")


if __name__ == "__main__":
    main()
