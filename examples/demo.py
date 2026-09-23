#!/usr/bin/env python3
"""PExM demo — clean output for terminal recording."""

import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import torch
from pexm.core import ExperienceModel

def slow_print(text, delay=0.02):
    for char in text:
        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(delay)
    print()

def section(title):
    print()
    slow_print(f"{'=' * 60}", 0.005)
    slow_print(f"  {title}", 0.03)
    slow_print(f"{'=' * 60}", 0.005)
    print()

def main():
    section("PExM -- Predictive Experience Model")
    slow_print("  Memory that lives in the weights, not in a database.")
    time.sleep(0.5)

    print()
    slow_print("Loading model...", 0.03)
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    model = ExperienceModel(device=device)
    optimizer = model.get_optimizer()
    optimizer.zero_grad()
    slow_print(f"  Ready on {device}.", 0.03)
    time.sleep(0.3)

    section("Step 1: Absorb experiences")

    experiences = [
        ("reading the auth module",
         "JWT tokens with RS256 signing. Expire after 3600 seconds. Refresh tokens in Redis."),
        ("debugging login failure",
         "Email validator regex rejects plus signs. Fix in validators.py line 42."),
        ("running tests after auth changes",
         "3 tests failed in test_auth.py. Token expiry causes mid-suite failures."),
        ("reviewing payment webhook",
         "Stripe API v2023-10-16. Webhook validates HMAC signatures before processing."),
        ("debugging database pool",
         "Connection pool exhaustion at 50 users. Pool size is 10 in config.yaml."),
        ("investigating memory leak",
         "Unbounded LRU cache in search_service.py. Grows to 2GB in 24 hours."),
        ("reading rate limit config",
         "Sliding window counter in Redis. 100 requests per minute per API key."),
        ("checking git log",
         "alice: refactored auth to async. bob: added rate limiting to login."),
    ]

    for state, outcome in experiences:
        m = model.absorb(state, outcome)
        model.maybe_step(optimizer)
        bar = "#" * int(m["surprise"] * 20)
        slow_print(f"  absorb(\"{state}\")", 0.015)
        slow_print(f"    surprise: {m['surprise']:.3f} [{bar:<20}]", 0.01)
        time.sleep(0.15)

    optimizer.step()
    optimizer.zero_grad()
    print()
    slow_print(f"  {model.n_stored} experiences absorbed.", 0.03)
    time.sleep(0.5)

    section("Step 2: Query for context")

    queries = [
        "fixing auth token expiry in the test suite",
        "payment webhook is returning 400 errors",
        "investigating the production memory leak",
    ]

    for q in queries:
        slow_print(f'  query("{q}")', 0.02)
        time.sleep(0.2)
        result = model.query(q, top_k=3)
        slow_print(f"    confidence: {result['confidence']:.3f}  latency: {result['latency_ms']:.0f}ms", 0.015)
        print()
        for i, exp in enumerate(result["experiences"]):
            score = exp["score"]
            text = exp["outcome"][:65]
            slow_print(f"    [{score:.3f}] {text}...", 0.01)
        print()
        time.sleep(0.3)

    section("Step 3: Surprise -- is this novel?")

    pairs = [
        ("reading the auth module", "JWT tokens with RS256 signing", "known"),
        ("checking Kubernetes operator", "CRD reconciliation every 30 seconds", "novel"),
        ("debugging login failure", "Email regex rejects plus signs", "known"),
        ("setting up GraphQL federation", "Apollo Router with 4 subgraphs", "novel"),
    ]

    for state, outcome, expected in pairs:
        s = model.surprise(state, outcome)
        label = "NOVEL" if model.is_novel(state, outcome) else "known"
        bar = "#" * int(s * 30)
        slow_print(f"  surprise(\"{state[:35]}...\")  = {s:.3f} [{bar:<30}] {label}", 0.015)
        time.sleep(0.15)

    section("Step 4: Natural forgetting")

    slow_print("  Old knowledge:", 0.03)
    old_q = model.query("what auth does the system use", top_k=1)
    slow_print(f"    {old_q['experiences'][0]['outcome'][:60]}...", 0.015)
    time.sleep(0.3)

    print()
    slow_print("  Absorbing: 'auth rewritten to OAuth2 with PKCE'...", 0.03)
    for _ in range(3):
        model.absorb("auth module rewritten",
                      "Now uses OAuth2 with PKCE flow. JWT replaced with opaque tokens.")
        model.maybe_step(optimizer)
    optimizer.step()
    optimizer.zero_grad()
    time.sleep(0.3)

    slow_print("  After contradiction:", 0.03)
    new_q = model.query("what auth does the system use", top_k=2)
    for exp in new_q["experiences"]:
        slow_print(f"    [{exp['score']:.3f}] {exp['outcome'][:60]}...", 0.015)

    print()
    slow_print("  Old knowledge displaced. No eviction policy needed.", 0.03)

    section("Done.")
    slow_print(f"  {model.n_stored} experiences stored in model weights.", 0.03)
    slow_print("  No database. No vector store. No eviction.", 0.03)
    slow_print("  Just absorb and query.", 0.03)
    print()


if __name__ == "__main__":
    main()
