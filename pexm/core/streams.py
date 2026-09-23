"""Multi-timescale adaptation streams.

v6: Added 'large' capacity mode for token-level memorization (~15M params)
and forward_sequence() for applying streams to full sequence hidden states
(not just the CLS token).
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
    CAPACITY_CONFIGS = {
        "default": {
            "fast":   {"bottleneck_ratio": 8,  "lr": 1e-3},
            "medium": {"bottleneck_ratio": 16, "lr": 1e-4},
            "slow":   {"bottleneck_ratio": 32, "lr": 1e-5},
        },
        "large": {
            "fast":   {"bottleneck_ratio": 4,  "lr": 1e-3},
            "medium": {"bottleneck_ratio": 8,  "lr": 1e-4},
            "slow":   {"bottleneck_ratio": 16, "lr": 1e-5},
        },
    }

    def __init__(self, hidden_size: int, capacity: str = "default"):
        super().__init__()
        self.hidden_size = hidden_size
        config = self.CAPACITY_CONFIGS.get(capacity, self.CAPACITY_CONFIGS["default"])
        self._config = config
        self.streams = nn.ModuleDict()
        for name, cfg in config.items():
            bn = hidden_size // cfg["bottleneck_ratio"]
            self.streams[name] = AdaptationStream(hidden_size, bn)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Apply streams to a single embedding [batch, hidden]."""
        correction = torch.zeros_like(x)
        for stream in self.streams.values():
            correction = correction + stream(x)
        return x + correction

    def forward_sequence(self, hidden_states: torch.Tensor) -> torch.Tensor:
        """Apply streams to full sequence [batch, seq_len, hidden].

        Returns the CORRECTION only (caller adds to original).
        """
        correction = torch.zeros_like(hidden_states)
        for stream in self.streams.values():
            correction = correction + stream(hidden_states)
        return correction

    def optimizer_param_groups(self):
        groups = []
        for name, cfg in self._config.items():
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
