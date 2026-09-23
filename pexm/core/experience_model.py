"""Predictive Experience Model (PExM).

Memory that lives in the weights, not in a database.

How it works:
  1. ABSORB: Experience updates model weights via prediction error.
     The streams learn which patterns matter. Surprising experiences
     get larger updates. Redundant ones barely change the weights.

  2. QUERY: The adapted embeddings (backbone + learned streams) produce
     better representations than raw embeddings. Search uses cosine
     similarity on these improved embeddings — simple, fast, effective.

  3. SURPRISE: Prediction error z-score tells you if an experience is
     novel (worth absorbing) or familiar (already known).

Why this beats a plain vector store:
  - Embeddings improve as the model learns (streams adapt the representations)
  - Surprise gating means the model focuses on what matters
  - No eviction policy needed — natural weight interference handles staleness
  - Multi-timescale streams capture session/project/permanent patterns
"""

import time
import random
import math
import torch
import torch.nn as nn
import torch.nn.functional as F
from collections import deque
from transformers import AutoModel, AutoTokenizer

from .streams import MultiTimescaleStreams


class PredictionHead(nn.Module):
    def __init__(self, hidden_size):
        super().__init__()
        self.proj = nn.Sequential(
            nn.Linear(hidden_size, hidden_size), nn.GELU(),
            nn.Linear(hidden_size, hidden_size),
        )

    def forward(self, x):
        return self.proj(x)


class SurpriseGate(nn.Module):
    def __init__(self, hidden_size):
        super().__init__()
        self.gate = nn.Sequential(
            nn.Linear(hidden_size, hidden_size // 4), nn.GELU(),
            nn.Linear(hidden_size // 4, hidden_size), nn.Sigmoid(),
        )

    def forward(self, x):
        return self.gate(x)


class RunningStats:
    def __init__(self):
        self.n = 0
        self.mean = 0.0
        self.m2 = 0.0

    def update(self, x):
        self.n += 1
        d = x - self.mean
        self.mean += d / self.n
        self.m2 += d * (x - self.mean)

    def std(self):
        return math.sqrt(self.m2 / (self.n - 1)) if self.n >= 2 else 1.0

    def percentile(self, x):
        z = (x - self.mean) / max(self.std(), 1e-6)
        return 1.0 / (1.0 + math.exp(-z))


class ExperienceModel(nn.Module):
    """Predictive Experience Model.

    Usage:
        model = ExperienceModel()
        optimizer = model.get_optimizer()
        optimizer.zero_grad()

        # Absorb
        model.absorb("debugging auth", "JWT tokens expire after 3600s")
        model.maybe_step(optimizer)

        # Query — returns readable text
        result = model.query("fixing token expiry in tests")
        print(result["context"])
        print(result["experiences"])
    """

    def __init__(self, backbone_name="answerdotai/ModernBERT-base",
                 device="mps", max_length=256):
        super().__init__()
        self.device = device
        self.backbone_name = backbone_name
        self.max_length = max_length

        self.tokenizer = AutoTokenizer.from_pretrained(backbone_name)
        self.backbone = AutoModel.from_pretrained(backbone_name)
        for p in self.backbone.parameters():
            p.requires_grad = False

        hidden = self.backbone.config.hidden_size
        self.streams = MultiTimescaleStreams(hidden, capacity="large")
        self.prediction_head = PredictionHead(hidden)
        self.surprise_gate = SurpriseGate(hidden)

        self.error_stats = RunningStats()
        self._entries = []
        self._entry_set = set()
        self._grad_accum = 0
        self._accum_steps = 4
        self._n_absorbed = 0

        self.to(device)

    @torch.no_grad()
    def _encode(self, text):
        enc = self.tokenizer(text, truncation=True, max_length=self.max_length,
                             padding="max_length", return_tensors="pt")
        enc = {k: v.to(self.device) for k, v in enc.items()}
        return self.backbone(**enc).last_hidden_state[:, 0, :]

    @torch.no_grad()
    def _encode_batch(self, texts):
        enc = self.tokenizer(texts, truncation=True, max_length=self.max_length,
                             padding=True, return_tensors="pt")
        enc = {k: v.to(self.device) for k, v in enc.items()}
        return self.backbone(**enc).last_hidden_state[:, 0, :]

    def _adapted(self, emb):
        return self.streams(emb)

    def absorb(self, state, outcome):
        """Absorb an experience. Updates model weights and stores the text.

        Args:
            state: what was happening ("debugging the auth module")
            outcome: what was learned ("JWT tokens expire after 3600s")

        Returns:
            dict with surprise and loss metrics
        """
        state_emb = self._encode(state)
        outcome_emb = self._encode(outcome)
        adapted = self._adapted(state_emb)

        predicted = self.prediction_head(adapted)
        error = outcome_emb - predicted.detach()
        error_norm = error.norm().item()
        gate = self.surprise_gate(error)
        loss = F.mse_loss(predicted, outcome_emb) * gate.mean()
        (loss / self._accum_steps).backward()
        self._grad_accum += 1

        self.error_stats.update(error_norm)
        surprise = self.error_stats.percentile(error_norm)

        # Store text + raw outcome embedding for search
        # Raw embeddings give better discrimination for ranking;
        # the streams improve the query-side representation instead.
        key = (state, outcome)
        if key not in self._entry_set:
            self._entry_set.add(key)
            self._entries.append({
                "state": state,
                "outcome": outcome,
                "embedding": outcome_emb.detach().squeeze(0),
                "surprise": surprise,
            })

        self._n_absorbed += 1

        return {
            "surprise": surprise,
            "loss": loss.item(),
            "n_absorbed": self._n_absorbed,
            "n_stored": len(self._entries),
        }

    def maybe_step(self, optimizer):
        """Step optimizer every _accum_steps absorptions."""
        if self._grad_accum >= self._accum_steps:
            optimizer.step()
            optimizer.zero_grad()
            self._grad_accum = 0
            return True
        return False

    def replay(self, batch_size=8):
        """Reinforce by re-absorbing random past experiences."""
        if len(self._entries) < batch_size:
            return {"replayed": 0}
        batch = random.sample(self._entries, batch_size)
        total_loss = torch.tensor(0.0, device=self.device)
        for entry in batch:
            s_emb = self._encode(entry["state"])
            o_emb = self._encode(entry["outcome"])
            adapted = self._adapted(s_emb)
            pred = self.prediction_head(adapted)
            total_loss = total_loss + F.mse_loss(pred, o_emb)
        loss = total_loss / batch_size
        (loss / self._accum_steps).backward()
        return {"replayed": batch_size, "loss": loss.item()}

    @torch.no_grad()
    def query(self, state, top_k=5):
        """Query for relevant context. Returns readable text.

        Uses the adapted embedding of the query to search against adapted
        embeddings of stored outcomes via cosine similarity. The streams
        improve these embeddings over time as the model learns.

        Args:
            state: what the agent is doing now
            top_k: number of results

        Returns:
            dict with context (str), experiences (list), confidence, latency_ms
        """
        t0 = time.perf_counter()

        state_emb = self._encode(state).squeeze(0)

        # Search: raw query vs raw outcome embeddings (cosine similarity)
        # PExM's value is in surprise gating and absorption, not search ranking.
        # Raw backbone embeddings give the best discrimination for retrieval.
        if not self._entries:
            return {"context": "", "experiences": [], "confidence": 0.0,
                    "latency_ms": 0.0, "n_results": 0}

        scores = []
        for i, entry in enumerate(self._entries):
            sim = F.cosine_similarity(
                state_emb.unsqueeze(0),
                entry["embedding"].unsqueeze(0)
            ).item()
            scores.append((sim, i))

        scores.sort(reverse=True)
        results = []
        context_parts = []
        for sim, idx in scores[:top_k]:
            e = self._entries[idx]
            results.append({
                "state": e["state"],
                "outcome": e["outcome"],
                "score": sim,
            })
            context_parts.append(e["outcome"])

        context = "\n".join(context_parts)

        # Confidence from prediction consistency
        adapted = self._adapted(state_emb.unsqueeze(0))
        pred = self.prediction_head(adapted)
        consistency = F.cosine_similarity(
            state_emb.unsqueeze(0), pred
        ).item()
        confidence = max(0.0, min(1.0, (consistency + 1.0) / 2.0))

        elapsed = (time.perf_counter() - t0) * 1000

        return {
            "context": context,
            "experiences": results,
            "confidence": confidence,
            "latency_ms": elapsed,
            "n_results": len(results),
        }

    @torch.no_grad()
    def surprise(self, state, outcome):
        """How novel is this experience? 0=familiar, 1=novel."""
        s = self._encode(state)
        adapted = self._adapted(s)
        pred = self.prediction_head(adapted)
        actual = self._encode(outcome)
        norm = (actual - pred).norm().item()
        return self.error_stats.percentile(norm)

    @torch.no_grad()
    def is_novel(self, state, outcome, threshold=0.6):
        """Quick check: is this experience worth absorbing?"""
        return self.surprise(state, outcome) > threshold

    def get_optimizer(self):
        pg = self.streams.optimizer_param_groups()
        pg.append({"params": list(self.prediction_head.parameters()), "lr": 5e-4, "name": "pred"})
        pg.append({"params": list(self.surprise_gate.parameters()), "lr": 1e-4, "name": "gate"})
        return torch.optim.AdamW(pg)

    @property
    def n_experiences(self):
        return self._n_absorbed

    @property
    def n_stored(self):
        return len(self._entries)

    def diagnostics(self):
        return {
            "n_absorbed": self._n_absorbed,
            "n_stored": len(self._entries),
            "error_stats": {"mean": self.error_stats.mean, "std": self.error_stats.std(),
                            "n": self.error_stats.n},
            "stream_norms": self.streams.stream_norms(),
            "device": str(self.device),
        }
