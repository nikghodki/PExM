"""ContextOS Python SDK — gRPC client for the enterprise AI memory OS."""

from .client import ContextOSClient
from .types import (
    AuditEvent,
    CommitDiff,
    CompressionResult,
    ContextEntry,
    ContextWindow,
    Effect,
    EvictionPolicy,
    FileDiff,
    MemoryEntry,
    MemoryEvent,
    MemoryEventKind,
    MemoryTier,
    PermissionAction,
    PermissionCheck,
    PromotionSuggestion,
    Role,
    Scope,
    SymbolKind,
    SymbolNode,
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
    "FileDiff",
    "MemoryEvent",
    "MemoryEventKind",
    "ContextWindow",
    "ContextEntry",
    "EvictionPolicy",
    "Role",
    "PermissionCheck",
    "AuditEvent",
    "PermissionAction",
    "Effect",
    "PromotionSuggestion",
    "CompressionResult",
]
