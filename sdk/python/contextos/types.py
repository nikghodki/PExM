"""
ContextOS Python SDK — data classes mirroring the core proto types.

These are framework-independent Python types used by the SDK client.
They can be serialised to/from dicts for JSON logging, tests, and mocking.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from typing import Optional

# ─── Enums ────────────────────────────────────────────────────────────────────

class MemoryTier(IntEnum):
    L1_SESSION  = 1
    L2_TASK     = 2
    L3_SEMANTIC = 3
    L4_ARCHIVE  = 4


class Scope(IntEnum):
    PRIVATE   = 1
    TEAM      = 2
    ORG       = 3
    EPHEMERAL = 4


class SymbolKind(IntEnum):
    FUNCTION   = 1
    CLASS      = 2
    STRUCT     = 3
    TRAIT      = 4
    INTERFACE  = 5
    MODULE     = 6
    VARIABLE   = 7
    CONSTANT   = 8
    TYPE_ALIAS = 9


class MemoryEventKind(IntEnum):
    MEMORY_CREATED      = 1
    MEMORY_UPDATED      = 2
    MEMORY_PROMOTED     = 3
    MEMORY_ARCHIVED     = 4
    SCOPE_SHARED        = 5
    AGENT_SUBSCRIBED    = 6
    AGENT_UNSUBSCRIBED  = 7


class EvictionPolicy(IntEnum):
    LRU    = 1
    SCORE  = 2
    FIFO   = 3
    HYBRID = 4


class PermissionAction(IntEnum):
    READ   = 1
    WRITE  = 2
    DELETE = 3
    ADMIN  = 4


class Effect(IntEnum):
    ALLOW = 1
    DENY  = 2


# ─── Memory types ─────────────────────────────────────────────────────────────

@dataclass
class MemoryEntry:
    id:          str
    agent_id:    str
    content:     str
    tier:        MemoryTier
    scope:       Scope
    score:       float             = 0.5
    tags:        list[str]         = field(default_factory=list)
    metadata:    dict[str, str]    = field(default_factory=dict)
    embedding:   list[float]       = field(default_factory=list)
    created_at:  Optional[datetime] = None
    accessed_at: Optional[datetime] = None
    expires_at:  Optional[datetime] = None


# ─── Indexer types ────────────────────────────────────────────────────────────

@dataclass
class SymbolNode:
    id:             str
    repo_id:        str
    file_path:      str
    name:           str
    qualified_name: str
    kind:           SymbolKind
    start_line:     int
    end_line:       int
    signature:      str            = ""
    docstring:      str            = ""
    callers:        list[str]      = field(default_factory=list)
    callees:        list[str]      = field(default_factory=list)
    deps:           list[str]      = field(default_factory=list)
    metadata:       dict[str, str] = field(default_factory=dict)


@dataclass
class FileDiff:
    path:          str
    added_lines:   int = 0
    removed_lines: int = 0
    old_content:   str = ""
    new_content:   str = ""


@dataclass
class CommitDiff:
    repo_id:    str
    commit_sha: str
    author:     str
    message:    str
    timestamp:  Optional[datetime]
    files:      list[FileDiff] = field(default_factory=list)


# ─── Bus types ────────────────────────────────────────────────────────────────

@dataclass
class MemoryEvent:
    event_id:    str
    kind:        MemoryEventKind
    memory_id:   str
    agent_id:    str
    scope:       str
    payload:     dict[str, str]    = field(default_factory=dict)
    occurred_at: Optional[datetime] = None


# ─── Scheduler types ──────────────────────────────────────────────────────────

@dataclass
class ContextEntry:
    id:          str
    content:     str
    relevance:   float
    token_count: int
    source_tier: str
    source_id:   str


@dataclass
class ContextWindow:
    session_id:      str
    total_tokens:    int
    budget_tokens:   int
    entries:         list[ContextEntry] = field(default_factory=list)
    eviction_policy: str                = "LRU"


# ─── Policy / RBAC types ──────────────────────────────────────────────────────

@dataclass
class Role:
    id:          str
    name:        str
    permissions: list[str]  = field(default_factory=list)


@dataclass
class PermissionCheck:
    effect:  Effect
    rule_id: str   = ""
    reason:  str   = ""


@dataclass
class AuditEvent:
    id:           str
    principal_id: str
    resource:     str
    action:       PermissionAction
    outcome:      Effect
    details:      str = ""
    ip_address:   str = ""
    occurred_at:  Optional[datetime] = None


# ─── Optimizer types ──────────────────────────────────────────────────────────

@dataclass
class PromotionSuggestion:
    memory_id:   str
    reason:      str
    target_tier: str
    confidence:  float = 0.0


@dataclass
class CompressionResult:
    memory_id:     str
    compressed:    bool
    before_tokens: int
    after_tokens:  int
    summary:       str = ""
