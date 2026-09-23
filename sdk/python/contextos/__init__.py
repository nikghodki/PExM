"""ContextOS Python SDK — gRPC client for the enterprise AI memory OS."""

from .client import ContextOSClient
from .types import (
    MemoryEntry,
    MemoryTier,
    Scope,
    SymbolNode,
    SymbolKind,
    CommitDiff,
    MemoryEvent,
    MemoryEventKind,
    ContextWindow,
    EvictionPolicy,
)

__version__ = "0.1.0"
__all__ = [
    "ContextOSClient",
    "MemoryEntry",
    "MemoryTier",
    "Scope",
    "SymbolNode",
    "SymbolKind",
    "CommitDiff",
    "MemoryEvent",
    "MemoryEventKind",
    "ContextWindow",
    "EvictionPolicy",
]
