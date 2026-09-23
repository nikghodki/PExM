"""Predictive Experience Model v5 (PExM).

v5 fix: surprise calibration via prediction error statistics.

v4 failure: FamiliarityHead on [state_emb; outcome_emb] collapsed to 0.44
for everything because the frozen backbone puts all coding text in similar
embedding regions. The concatenated vector is indistinguishable.

v5 approach — two parallel surprise signals:

  1. Z-score surprise (no neural head, just statistics):
     Track running mean/std of prediction error norms.
     z = (error_norm - mean) / std
     Known experiences cluster near 0, novel ones are positive outliers.

  2. Error-based familiarity head (learns from prediction error):
     Instead of raw embeddings, feeds [prediction_error, error_norm, gate_values]
     to the head. These signals genuinely differ between known and novel.

We keep both and report which one works better.
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
    def __init__(self, hidden_size: int):
        super().__init__()
        self.proj = nn.Sequential(
            nn.Linear(hidden_size, hidden_size),
            nn.GELU(),
            nn.Linear(hidden_size, hidden_size),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.proj(x)


class ContextGenerator(nn.Module):
    def __init__(self, hidden_size: int):
        super().__init__()
        self.proj = nn.Sequential(
            nn.Linear(hidden_size, hidden_size * 2),
            nn.GELU(),
            nn.Linear(hidden_size * 2, hidden_size),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.proj(x)


class SurpriseGate(nn.Module):
    def __init__(self, hidden_size: int):
        super().__init__()
        self.gate = nn.Sequential(
            nn.Linear(hidden_size, hidden_size // 4),
            nn.GELU(),
            nn.Linear(hidden_size // 4, hidden_size),
            nn.Sigmoid(),
        )

    def forward(self, prediction_error: torch.Tensor) -> torch.Tensor:
        return self.gate(prediction_error)


class RunningStats:
    """Welford's online algorithm for running mean and variance."""

    def __init__(self):
        self.n = 0
        self.mean = 0.0
        self.m2 = 0.0

    def update(self, x: float):
        self.n += 1
        delta = x - self.mean
        self.mean += delta / self.n
        delta2 = x - self.mean
        self.m2 += delta * delta2

    def std(self) -> float:
        if self.n < 2:
            return 1.0
        return math.sqrt(self.m2 / (self.n - 1))

    def z_score(self, x: float) -> float:
        s = self.std()
        if s < 1e-6:
            return 0.0
        return (x - self.mean) / s

    def percentile_surprise(self, x: float) -> float:
        """Convert z-score to 0-1 range via sigmoid. 0=familiar, 1=novel."""
        z = self.z_score(x)
        return 1.0 / (1.0 + math.exp(-z))


class ErrorFamiliarityHead(nn.Module):
    """Familiarity head that operates on prediction error features.

    v4 failed because [state_emb; outcome_emb] was indistinguishable.
    This head instead takes:
      - prediction error vector (hidden_size)
      - scalar error norm
      - gate values from SurpriseGate (hidden_size)

    These signals genuinely differ: low error + low gate = familiar,
    high error + high gate = novel.
    """

    def __init__(self, hidden_size: int):
        super().__init__()
        input_size = hidden_size * 2 + 1  # error + gate + norm
        self.head = nn.Sequential(
            nn.Linear(input_size, hidden_size // 2),
            nn.GELU(),
            nn.LayerNorm(hidden_size // 2),
            nn.Linear(hidden_size // 2, hidden_size // 8),
            nn.GELU(),
            nn.Linear(hidden_size // 8, 1),
        )

    def forward(self, error: torch.Tensor, error_norm: torch.Tensor,
                gate_values: torch.Tensor) -> torch.Tensor:
        norm_expanded = error_norm.unsqueeze(-1) if error_norm.dim() == 0 else error_norm
        if norm_expanded.dim() == 1:
            norm_expanded = norm_expanded.unsqueeze(-1)
        combined = torch.cat([error, norm_expanded, gate_values], dim=-1)
        return torch.sigmoid(self.head(combined)).squeeze(-1)


class ExperienceBuffer:
    def __init__(self, maxlen: int = 2048):
        self.buffer = deque(maxlen=maxlen)

    def add(self, state: str, outcome: str, state_emb: torch.Tensor,
            outcome_emb: torch.Tensor, error_norm: float):
        self.buffer.append({
            "state": state, "outcome": outcome,
            "state_emb": state_emb.detach().cpu(),
            "outcome_emb": outcome_emb.detach().cpu(),
            "error_norm": error_norm,
        })

    def sample_negatives(self, exclude_idx: int, n: int = 4) -> list:
        if len(self.buffer) < 2:
            return []
        indices = list(range(len(self.buffer)))
        if exclude_idx < len(indices):
            indices.remove(exclude_idx)
        n = min(n, len(indices))
        return [self.buffer[i] for i in random.sample(indices, n)]

    def sample_batch(self, n: int) -> list:
        n = min(n, len(self.buffer))
        return random.sample(list(self.buffer), n)

    def __len__(self):
        return len(self.buffer)


class ExperienceModel(nn.Module):
    """Predictive Experience Model v5.

    Two surprise mechanisms:
      A. Z-score: running mean/std of error norms → percentile surprise
      B. ErrorFamiliarityHead: neural head on [error, norm, gate] features

    Both reported; experiment determines which calibrates better.
    """

    def __init__(self, backbone_name: str = "answerdotai/ModernBERT-base",
                 device: str = "mps", max_length: int = 256):
        super().__init__()
        self.device = device
        self.backbone_name = backbone_name
        self.max_length = max_length

        self.tokenizer = AutoTokenizer.from_pretrained(backbone_name)
        self.backbone = AutoModel.from_pretrained(backbone_name)
        for p in self.backbone.parameters():
            p.requires_grad = False

        hidden = self.backbone.config.hidden_size

        self.streams = MultiTimescaleStreams(hidden)
        self.prediction_head = PredictionHead(hidden)
        self.context_generator = ContextGenerator(hidden)
        self.surprise_gate = SurpriseGate(hidden)
        self.error_familiarity = ErrorFamiliarityHead(hidden)

        self.error_stats = RunningStats()
        self.replay_buffer = ExperienceBuffer(maxlen=2048)
        self._grad_accum_count = 0
        self._accum_steps = 4

        self.to(device)

        self._experience_count = 0
        self._total_context_loss = 0.0

    @torch.no_grad()
    def _encode(self, text: str) -> torch.Tensor:
        enc = self.tokenizer(text, truncation=True, max_length=self.max_length,
                             padding="max_length", return_tensors="pt")
        enc = {k: v.to(self.device) for k, v in enc.items()}
        return self.backbone(**enc).last_hidden_state[:, 0, :]

    @torch.no_grad()
    def _encode_batch(self, texts: list) -> torch.Tensor:
        enc = self.tokenizer(texts, truncation=True, max_length=self.max_length,
                             padding=True, return_tensors="pt")
        enc = {k: v.to(self.device) for k, v in enc.items()}
        return self.backbone(**enc).last_hidden_state[:, 0, :]

    def _adapted(self, emb: torch.Tensor) -> torch.Tensor:
        return self.streams(emb)

    def _compute_error_features(self, adapted: torch.Tensor, outcome_emb: torch.Tensor):
        """Compute prediction error, norm, and gate — the signals that differ."""
        predicted = self.prediction_head(adapted)
        error = outcome_emb - predicted
        error_norm = error.norm(dim=-1)
        gate = self.surprise_gate(error.detach())
        return predicted, error, error_norm, gate

    def absorb(self, state: str, actual_outcome: str) -> dict:
        state_emb = self._encode(state)
        actual_emb = self._encode(actual_outcome)
        adapted = self._adapted(state_emb)

        predicted, error, error_norm, gate = self._compute_error_features(adapted, actual_emb)
        norm_val = error_norm.item()

        # 1. Prediction loss (gated)
        prediction_loss = F.mse_loss(predicted, actual_emb) * gate.mean()

        # 2. Context loss
        context_emb = self.context_generator(adapted)
        context_loss = 1.0 - F.cosine_similarity(context_emb, actual_emb).mean()

        # 3. Contrastive context loss
        contrastive_loss = torch.tensor(0.0, device=self.device)
        negatives = self.replay_buffer.sample_negatives(len(self.replay_buffer) - 1, n=4)
        if negatives:
            pos_sim = F.cosine_similarity(context_emb, actual_emb)
            neg_sims = [F.cosine_similarity(context_emb, n["outcome_emb"].to(self.device))
                        for n in negatives]
            contrastive_loss = F.relu(torch.stack(neg_sims).mean() - pos_sim + 0.3)

        # 4. Error familiarity loss: this is a KNOWN pair → high familiarity
        fam_score = self.error_familiarity(error.detach(), error_norm.detach(), gate.detach())
        fam_loss_pos = F.binary_cross_entropy(fam_score, torch.ones_like(fam_score))

        # Negative: use a RANDOM outcome with this state → low familiarity
        fam_loss_neg = torch.tensor(0.0, device=self.device)
        if len(self.replay_buffer) >= 4:
            neg_samples = self.replay_buffer.sample_negatives(len(self.replay_buffer) - 1, n=2)
            for neg in neg_samples:
                neg_out = neg["outcome_emb"].to(self.device)
                _, neg_error, neg_norm, neg_gate = self._compute_error_features(adapted, neg_out)
                neg_fam = self.error_familiarity(neg_error.detach(), neg_norm.detach(), neg_gate.detach())
                fam_loss_neg = fam_loss_neg + F.binary_cross_entropy(neg_fam, torch.zeros_like(neg_fam))
            fam_loss_neg = fam_loss_neg / len(neg_samples)

        fam_loss = fam_loss_pos + fam_loss_neg

        total = prediction_loss + 2.0 * context_loss + contrastive_loss + 1.0 * fam_loss
        (total / self._accum_steps).backward()
        self._grad_accum_count += 1

        # Update running stats for z-score
        self.error_stats.update(norm_val)
        z_surprise = self.error_stats.percentile_surprise(norm_val)

        # Error-head familiarity
        with torch.no_grad():
            efam = fam_score.item()

        self.replay_buffer.add(state, actual_outcome, state_emb, actual_emb, norm_val)
        self._experience_count += 1
        self._total_context_loss += context_loss.item()

        return {
            "error_norm": norm_val,
            "z_surprise": z_surprise,
            "error_fam": efam,
            "gate_mean": gate.mean().item(),
            "prediction_loss": prediction_loss.item(),
            "context_loss": context_loss.item(),
            "fam_loss": fam_loss.item(),
            "total_loss": total.item(),
            "experience_count": self._experience_count,
            "buffer_size": len(self.replay_buffer),
            "should_step": self._grad_accum_count >= self._accum_steps,
        }

    def maybe_optimizer_step(self, optimizer) -> bool:
        if self._grad_accum_count >= self._accum_steps:
            optimizer.step()
            optimizer.zero_grad()
            self._grad_accum_count = 0
            return True
        return False

    def replay_step(self, batch_size: int = 8) -> dict:
        if len(self.replay_buffer) < batch_size:
            return {"replayed": 0}

        batch = self.replay_buffer.sample_batch(batch_size)
        states = [b["state"] for b in batch]
        outcomes = [b["outcome"] for b in batch]
        s_embs = self._encode_batch(states)
        o_embs = self._encode_batch(outcomes)

        total_ctx = torch.tensor(0.0, device=self.device)
        total_fam = torch.tensor(0.0, device=self.device)

        for i in range(batch_size):
            adapted = self._adapted(s_embs[i:i+1])
            ctx = self.context_generator(adapted)
            total_ctx = total_ctx + (1.0 - F.cosine_similarity(ctx, o_embs[i:i+1]).mean())

            # Positive familiarity from error features
            _, err, enorm, gate = self._compute_error_features(adapted, o_embs[i:i+1])
            fam = self.error_familiarity(err.detach(), enorm.detach(), gate.detach())
            total_fam = total_fam + F.binary_cross_entropy(fam, torch.ones_like(fam))

            # Negative: mismatched pair
            j = (i + random.randint(1, batch_size - 1)) % batch_size
            _, nerr, nnorm, ngate = self._compute_error_features(adapted, o_embs[j:j+1])
            nfam = self.error_familiarity(nerr.detach(), nnorm.detach(), ngate.detach())
            total_fam = total_fam + F.binary_cross_entropy(nfam, torch.zeros_like(nfam))

        loss = (total_ctx + total_fam) / (batch_size * 2)
        (loss / self._accum_steps).backward()

        return {"replayed": batch_size, "replay_loss": loss.item()}

    @torch.no_grad()
    def generate(self, agent_state: str) -> dict:
        t0 = time.perf_counter()
        s = self._encode(agent_state)
        adapted = self._adapted(s)
        ctx = self.context_generator(adapted)
        pred = self.prediction_head(adapted)
        consistency = F.cosine_similarity(ctx, pred).item()
        confidence = max(0.0, min(1.0, (consistency + 1.0) / 2.0))
        return {
            "context_embedding": ctx,
            "confidence": confidence,
            "latency_ms": (time.perf_counter() - t0) * 1000,
        }

    @torch.no_grad()
    def surprise_z(self, state: str, outcome: str) -> float:
        """Z-score based surprise: 0=familiar, 1=novel."""
        s = self._encode(state)
        o = self._encode(outcome)
        adapted = self._adapted(s)
        pred = self.prediction_head(adapted)
        norm = (o - pred).norm().item()
        return self.error_stats.percentile_surprise(norm)

    @torch.no_grad()
    def surprise_head(self, state: str, outcome: str) -> float:
        """Error-familiarity-head based surprise: 0=novel, 1=familiar."""
        s = self._encode(state)
        o = self._encode(outcome)
        adapted = self._adapted(s)
        _, err, enorm, gate = self._compute_error_features(adapted, o)
        fam = self.error_familiarity(err, enorm, gate).item()
        return 1.0 - fam  # invert: high fam = low surprise

    @torch.no_grad()
    def raw_error_norm(self, state: str, outcome: str) -> float:
        s = self._encode(state)
        o = self._encode(outcome)
        adapted = self._adapted(s)
        pred = self.prediction_head(adapted)
        return (o - pred).norm().item()

    @torch.no_grad()
    def context_similarity(self, state: str, target: str) -> float:
        s = self._encode(state)
        adapted = self._adapted(s)
        ctx = self.context_generator(adapted)
        t = self._encode(target)
        return F.cosine_similarity(ctx, t).item()

    def stream_saturation(self) -> dict:
        norms = self.streams.stream_norms()
        n = self._experience_count
        return {"norms": norms, "experience_count": n,
                "norm_per_exp": {k: v / max(n, 1) for k, v in norms.items()}}

    def get_optimizer(self) -> torch.optim.Optimizer:
        pg = self.streams.optimizer_param_groups()
        pg.append({"params": list(self.prediction_head.parameters()), "lr": 5e-4, "name": "pred"})
        pg.append({"params": list(self.context_generator.parameters()), "lr": 1e-3, "name": "ctx"})
        pg.append({"params": list(self.surprise_gate.parameters()), "lr": 1e-4, "name": "gate"})
        pg.append({"params": list(self.error_familiarity.parameters()), "lr": 2e-3, "name": "efam"})
        return torch.optim.AdamW(pg)

    def diagnostics(self) -> dict:
        return {
            "experience_count": self._experience_count,
            "avg_ctx_loss": self._total_context_loss / max(self._experience_count, 1),
            "error_stats": {"mean": self.error_stats.mean, "std": self.error_stats.std(),
                            "n": self.error_stats.n},
            "buffer_size": len(self.replay_buffer),
            "stream_norms": self.streams.stream_norms(),
            "device": str(self.device),
        }
