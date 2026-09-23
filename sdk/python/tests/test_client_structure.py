"""
Tests for the ContextOS client structure.

No live server is required: the gRPC channel is opened lazily, so the client
can be instantiated and inspected to confirm every gRPC subsystem is exposed.
"""

from contextos import ContextOSClient
from contextos.client import (
    _BusClient,
    _ContextClient,
    _IndexerClient,
    _MemoryClient,
    _OptimizerClient,
    _PolicyClient,
)


def test_client_exposes_all_six_services():
    client = ContextOSClient("localhost:50051")
    try:
        assert isinstance(client.memory, _MemoryClient)
        assert isinstance(client.indexer, _IndexerClient)
        assert isinstance(client.policy, _PolicyClient)
        assert isinstance(client.context, _ContextClient)
        assert isinstance(client.bus, _BusClient)
        assert isinstance(client.optimizer, _OptimizerClient)
    finally:
        client.close()


def test_memory_service_method_surface():
    client = ContextOSClient("localhost:50051")
    try:
        for method in ("store", "get", "search", "promote", "delete", "list"):
            assert callable(getattr(client.memory, method)), f"memory.{method} missing"
    finally:
        client.close()


def test_indexer_service_method_surface():
    client = ContextOSClient("localhost:50051")
    try:
        for method in (
            "index_repo",
            "query_symbols",
            "get_symbol",
            "get_commit_diff",
            "query_function_deltas",
        ):
            assert callable(getattr(client.indexer, method)), f"indexer.{method} missing"
    finally:
        client.close()


def test_policy_service_method_surface():
    client = ContextOSClient("localhost:50051")
    try:
        for method in (
            "check_permission",
            "create_role",
            "assign_role",
            "list_audit_events",
            "stream_audit_events",
        ):
            assert callable(getattr(client.policy, method)), f"policy.{method} missing"
    finally:
        client.close()


def test_context_service_method_surface():
    client = ContextOSClient("localhost:50051")
    try:
        for method in ("schedule_context", "get_window", "close_session", "evict"):
            assert callable(getattr(client.context, method)), f"context.{method} missing"
    finally:
        client.close()


def test_bus_service_method_surface():
    client = ContextOSClient("localhost:50051")
    try:
        for method in ("publish", "subscribe"):
            assert callable(getattr(client.bus, method)), f"bus.{method} missing"
    finally:
        client.close()


def test_optimizer_service_method_surface():
    client = ContextOSClient("localhost:50051")
    try:
        for method in ("promotion_suggestions", "trigger_compression"):
            assert callable(getattr(client.optimizer, method)), f"optimizer.{method} missing"
    finally:
        client.close()


def test_context_manager_protocol():
    with ContextOSClient("localhost:50051") as client:
        assert client.memory is not None
    # exiting the with-block closes the channel
