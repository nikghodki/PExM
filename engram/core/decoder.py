"""Context decoder: converts embeddings back to readable text.

The ExperienceModel generates context as embeddings. This module
decodes those embeddings into text that an agent can actually use.
Uses a small projection + the backbone's token embeddings to find
the closest tokens, then assembles them into readable context.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from transformers import AutoTokenizer, AutoModel


class ContextDecoder(nn.Module):
    """Decodes a context embedding back into a token sequence.

    Approach: project the context embedding into a sequence of
    pseudo-token embeddings, then find nearest real tokens via
    cosine similarity against the backbone's embedding table.
    """

    def __init__(self, hidden_size: int, max_tokens: int = 64):
        super().__init__()
        self.max_tokens = max_tokens
        self.unfold = nn.Sequential(
            nn.Linear(hidden_size, hidden_size * 2),
            nn.GELU(),
            nn.Linear(hidden_size * 2, hidden_size * max_tokens),
        )

    def forward(self, context_emb: torch.Tensor, token_embeddings: torch.Tensor) -> list:
        """Convert a context embedding to token IDs.

        Args:
            context_emb: [1, hidden_size] from ContextGenerator
            token_embeddings: [vocab_size, hidden_size] from backbone

        Returns:
            list of token IDs
        """
        seq = self.unfold(context_emb).view(1, self.max_tokens, -1)
        seq_norm = F.normalize(seq, dim=-1)
        emb_norm = F.normalize(token_embeddings, dim=-1)
        sims = torch.matmul(seq_norm, emb_norm.T)
        token_ids = sims.argmax(dim=-1).squeeze(0).tolist()
        return token_ids


class TextContextDecoder:
    """End-to-end: embedding -> readable text."""

    def __init__(self, backbone_name: str, hidden_size: int, device: str = "mps", max_tokens: int = 64):
        self.tokenizer = AutoTokenizer.from_pretrained(backbone_name)
        self.backbone = AutoModel.from_pretrained(backbone_name)
        self.backbone.eval()
        for p in self.backbone.parameters():
            p.requires_grad = False

        self.decoder = ContextDecoder(hidden_size, max_tokens)
        self.device = device
        self.decoder.to(device)
        self.backbone.to(device)

        self._token_embeddings = None

    @property
    def token_embeddings(self) -> torch.Tensor:
        if self._token_embeddings is None:
            self._token_embeddings = self.backbone.get_input_embeddings().weight.detach()
        return self._token_embeddings

    def decode(self, context_emb: torch.Tensor) -> str:
        with torch.no_grad():
            ids = self.decoder(context_emb, self.token_embeddings)
        text = self.tokenizer.decode(ids, skip_special_tokens=True)
        # Clean up repetition artifacts
        words = text.split()
        cleaned = []
        for w in words:
            if not cleaned or w != cleaned[-1]:
                cleaned.append(w)
        return " ".join(cleaned)
