"""Multi-timescale adaptation streams.

Each stream is a lightweight learnable projection that captures patterns
at a different time horizon. Fast streams adapt quickly (session-level),
slow streams persist (project-level). They compose additively on top of
frozen backbone embeddings.

This replaces explicit L1/L2/L3/L4 memory tiers -- tiers EMERGE from
the learning rate differences.
"""

import torch
import torch.nn as nn


class AdaptationStream(nn.Module):
    def __init__(self, hidden_size: int, bottleneck: int):
        super().__init__()
        self.down = nn.Linear(hidden_size, bottleneck, bias=False)
        self.up = nn.Linear(bottleneck, hidden_size, bias=False)
        nn.init.zeros_(self.up.weight)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.up(torch.tanh(self.down(x)))


class MultiTimescaleStreams(nn.Module):
    STREAM_CONFIG = {
        "fast":   {"bottleneck_ratio": 8,  "lr": 1e-3},
        "medium": {"bottleneck_ratio": 16, "lr": 1e-4},
        "slow":   {"bottleneck_ratio": 32, "lr": 1e-5},
    }

    def __init__(self, hidden_size: int):
        super().__init__()
        self.hidden_size = hidden_size
        self.streams = nn.ModuleDict()
        for name, cfg in self.STREAM_CONFIG.items():
            bn = hidden_size // cfg["bottleneck_ratio"]
            self.streams[name] = AdaptationStream(hidden_size, bn)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        correction = torch.zeros_like(x)
        for stream in self.streams.values():
            correction = correction + stream(x)
        return x + correction

    def optimizer_param_groups(self):
        groups = []
        for name, cfg in self.STREAM_CONFIG.items():
            groups.append({
                "params": list(self.streams[name].parameters()),
                "lr": cfg["lr"],
                "name": name,
            })
        return groups

    def stream_norms(self) -> dict:
        norms = {}
        for name in self.streams:
            w = self.streams[name].up.weight
            norms[name] = w.norm().item()
        return norms
