"""
Unit tests for the ContextOS Python SDK types module.
No server required — pure data class tests.
"""

import pytest
from datetime import datetime, timezone

from contextos.types import (
    MemoryEntry,
    MemoryTier,
    Scope,
    SymbolNode,
    SymbolKind,
    CommitDiff,
    FileDiff,
    MemoryEvent,
    MemoryEventKind,
    ContextWindow,
    ContextEntry,
    EvictionPolicy,
)


# ─── MemoryEntry ──────────────────────────────────────────────────────────────

def test_memory_entry_defaults():
    entry = MemoryEntry(
        id       = "mem-001",
        agent_id = "agent-001",
        content  = "The auth middleware logs all requests.",
        tier     = MemoryTier.L2_TASK,
        scope    = Scope.TEAM,
    )
    assert entry.score == 0.5
    assert entry.tags == []
    assert entry.metadata == {}
    assert entry.embedding == []


def test_memory_tier_values():
    assert MemoryTier.L1_SESSION  == 1
    assert MemoryTier.L2_TASK     == 2
    assert MemoryTier.L3_SEMANTIC == 3
    assert MemoryTier.L4_ARCHIVE  == 4


def test_scope_values():
    assert Scope.PRIVATE   == 1
    assert Scope.TEAM      == 2
    assert Scope.ORG       == 3
    assert Scope.EPHEMERAL == 4


def test_memory_entry_with_metadata():
    entry = MemoryEntry(
        id       = "mem-002",
        agent_id = "agent-002",
        content  = "refactored payment service",
        tier     = MemoryTier.L3_SEMANTIC,
        scope    = Scope.ORG,
        tags     = ["payment", "refactor"],
        metadata = {"pr": "123", "repo": "payment-svc"},
    )
    assert "payment" in entry.tags
    assert entry.metadata["pr"] == "123"


# ─── SymbolNode ───────────────────────────────────────────────────────────────

def test_symbol_node_defaults():
    sym = SymbolNode(
        id             = "sym-001",
        repo_id        = "repo:payment-svc",
        file_path      = "src/auth.rs",
        name           = "authenticate",
        qualified_name = "src/auth.rs::authenticate",
        kind           = SymbolKind.FUNCTION,
        start_line     = 42,
        end_line       = 67,
    )
    assert sym.kind == SymbolKind.FUNCTION
    assert sym.callers == []
    assert sym.callees == []
    assert sym.docstring == ""


def test_symbol_kind_values():
    assert SymbolKind.FUNCTION  == 1
    assert SymbolKind.CLASS     == 2
    assert SymbolKind.STRUCT    == 3
    assert SymbolKind.TRAIT     == 4


# ─── CommitDiff ───────────────────────────────────────────────────────────────

def test_commit_diff():
    diff = CommitDiff(
        repo_id    = "repo-001",
        commit_sha = "abc123",
        author     = "alice@example.com",
        message    = "fix: resolve deadlock in scheduler",
        timestamp  = datetime(2025, 1, 1, tzinfo=timezone.utc),
        files      = [
            FileDiff(path="src/scheduler.rs", added_lines=12, removed_lines=5),
        ],
    )
    assert diff.commit_sha == "abc123"
    assert len(diff.files) == 1
    assert diff.files[0].added_lines == 12


# ─── MemoryEvent ─────────────────────────────────────────────────────────────

def test_memory_event_kinds():
    event = MemoryEvent(
        event_id  = "evt-001",
        kind      = MemoryEventKind.MEMORY_CREATED,
        memory_id = "mem-001",
        agent_id  = "agent-001",
        scope     = "team",
    )
    assert event.kind == MemoryEventKind.MEMORY_CREATED
    assert event.payload == {}


# ─── ContextWindow ────────────────────────────────────────────────────────────

def test_context_window():
    window = ContextWindow(
        session_id    = "sess-001",
        total_tokens  = 500,
        budget_tokens = 4096,
        entries       = [
            ContextEntry(
                id          = "e1",
                content     = "some code context",
                relevance   = 0.9,
                token_count = 250,
                source_tier = "L2Task",
                source_id   = "mem-001",
            )
        ],
    )
    assert window.session_id == "sess-001"
    assert len(window.entries) == 1
    assert window.entries[0].relevance == 0.9


def test_eviction_policy_values():
    assert EvictionPolicy.LRU    == 1
    assert EvictionPolicy.SCORE  == 2
    assert EvictionPolicy.FIFO   == 3
    assert EvictionPolicy.HYBRID == 4
