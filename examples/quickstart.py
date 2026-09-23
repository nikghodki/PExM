#!/usr/bin/env python3
"""PExM quickstart — absorb coding experiences, generate context, measure surprise."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import torch
from pexm.core import ExperienceModel

def main():
    device = "mps" if torch.backends.mps.is_available() else "cuda:0" if torch.cuda.is_available() else "cpu"
    print(f"Loading PExM on {device}...")

    model = ExperienceModel(device=device)
    optimizer = model.get_optimizer()
    optimizer.zero_grad()

    # -- Absorb some coding experiences --
    experiences = [
        ("reading the auth module",
         "Uses JWT with RS256 signing. Tokens expire after 3600 seconds. Refresh tokens in Redis."),
        ("debugging the login failure",
         "Email validator regex rejects plus signs. Fix in validators.py line 42."),
        ("running tests after auth changes",
         "3 tests failed in test_auth.py. Token expiry causes mid-suite failures."),
        ("checking git log on auth module",
         "alice refactored auth to async handlers. bob added rate limiting to login."),
        ("reviewing the payment webhook",
         "Stripe API v2023-10-16. Webhook validates signatures before processing."),
    ]

    print(f"\nAbsorbing {len(experiences)} experiences...")
    for state, outcome in experiences:
        model.absorb(state, outcome)
        model.maybe_optimizer_step(optimizer)
    optimizer.step()
    optimizer.zero_grad()

    # -- Generate context for a new task --
    query = "fixing auth token expiry in the test suite"
    result = model.generate(query)
    print(f"\nGenerate('{query}'):")
    print(f"  Confidence: {result['confidence']:.3f}")
    print(f"  Latency:    {result['latency_ms']:.0f}ms")

    # -- Measure surprise: known vs novel --
    known = model.surprise_z(
        "reading the auth module",
        "Uses JWT with RS256 signing. Tokens expire after 3600 seconds.")
    novel = model.surprise_z(
        "checking the Kubernetes operator",
        "CRD reconciliation loop runs every 30 seconds. Uses leader election.")

    print(f"\nSurprise scores:")
    print(f"  Known experience: {known:.3f}  (low = familiar)")
    print(f"  Novel experience: {novel:.3f}  (high = never seen)")

    # -- Absorb a contradiction --
    print(f"\nAbsorbing contradiction: 'auth rewritten to OAuth2'...")
    for _ in range(3):
        model.absorb(
            "auth module rewritten",
            "Now uses OAuth2 with PKCE. JWT replaced with opaque tokens.")
        model.maybe_optimizer_step(optimizer)
    optimizer.step()
    optimizer.zero_grad()

    old_surprise = model.surprise_z(
        "checking auth tokens",
        "JWT with RS256 signing and 3600 second expiry")
    new_surprise = model.surprise_z(
        "checking auth tokens",
        "OAuth2 with PKCE flow and opaque tokens")
    print(f"  Old JWT knowledge surprise:  {old_surprise:.3f}  (higher = fading)")
    print(f"  New OAuth2 knowledge surprise: {new_surprise:.3f}  (lower = absorbed)")

    print(f"\nDiagnostics: {model.diagnostics()}")


if __name__ == "__main__":
    main()
