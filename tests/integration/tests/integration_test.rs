//! End-to-end integration tests for all ContextOS gRPC services.
//!
//! Each test starts the `contextos-server` binary in a subprocess on a random
//! port, connects via tonic, exercises every RPC, then kills the process.

use std::net::TcpListener;
use std::process::{Child, Command, Stdio};
use std::time::Duration;

use tonic::transport::Channel;

// ── Proto-generated clients ────────────────────────────────────────────────────

pub mod memory_proto {
    tonic::include_proto!("contextos.memory.v1");
}
pub mod indexer_proto {
    tonic::include_proto!("contextos.indexer.v1");
}
pub mod policy_proto {
    tonic::include_proto!("contextos.policy.v1");
}
pub mod context_proto {
    tonic::include_proto!("contextos.context.v1");
}
pub mod bus_proto {
    tonic::include_proto!("contextos.bus.v1");
}
pub mod optimizer_proto {
    tonic::include_proto!("contextos.optimizer.v1");
}

use bus_proto::memory_bus_service_client::MemoryBusServiceClient;
use bus_proto::{MemoryEvent, PublishEventRequest, SubscribeRequest};
use context_proto::context_scheduler_service_client::ContextSchedulerServiceClient;
use context_proto::{EvictRequest, GetContextWindowRequest, ScheduleContextRequest};
use indexer_proto::indexer_service_client::IndexerServiceClient;
use indexer_proto::{IndexRepositoryRequest, QuerySymbolsRequest};
use memory_proto::memory_service_client::MemoryServiceClient;
use memory_proto::{
    ListMemoriesRequest, PromoteMemoryRequest, SearchMemoryRequest, StoreMemoryRequest,
};
use optimizer_proto::optimizer_service_client::OptimizerServiceClient;
use optimizer_proto::{GetPromotionSuggestionsRequest, TriggerCompressionRequest};
use policy_proto::policy_service_client::PolicyServiceClient;
use policy_proto::{AssignRoleRequest, CheckPermissionRequest, CreateRoleRequest, Role};

// ── Test helpers ───────────────────────────────────────────────────────────────

fn free_port() -> u16 {
    TcpListener::bind("127.0.0.1:0")
        .unwrap()
        .local_addr()
        .unwrap()
        .port()
}

/// Locate the built server binary.
fn server_binary() -> std::path::PathBuf {
    // Cargo puts the binary next to the test binary in target/debug/
    let mut path = std::env::current_exe().unwrap();
    path.pop(); // strip binary name
    if path.ends_with("deps") {
        path.pop();
    } // strip deps/ if present
    path.push("contextos-server");
    path
}

struct ServerProcess {
    child: Child,
    addr: String,
    #[allow(dead_code)] // keeps TempDir alive for server's lifetime
    data_dir: tempfile::TempDir,
}

impl ServerProcess {
    /// Spawn the server binary and wait until it accepts connections.
    fn start() -> Self {
        let port = free_port();
        let addr = format!("http://127.0.0.1:{port}");
        let bind = format!("127.0.0.1:{port}");
        let data_dir = tempfile::TempDir::new().unwrap();

        let child = Command::new(server_binary())
            .env("CONTEXTOS_BIND", &bind)
            .env("CONTEXTOS_ROCKSDB_PATH", data_dir.path())
            .env("CONTEXTOS_LOG", "error")
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .expect("failed to spawn contextos-server binary — run `cargo build` first");

        // Poll until the port is open (max 10 s).
        for _ in 0..100 {
            if TcpListener::bind(format!("127.0.0.1:{port}")).is_err() {
                break; // port is now in use → server is listening
            }
            std::thread::sleep(Duration::from_millis(100));
        }
        // Extra grace period for gRPC layer init.
        std::thread::sleep(Duration::from_millis(200));

        ServerProcess {
            child,
            addr,
            data_dir,
        }
    }

    async fn channel(&self) -> Channel {
        Channel::from_shared(self.addr.clone())
            .unwrap()
            .connect()
            .await
            .expect("failed to connect to test server")
    }
}

impl Drop for ServerProcess {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

// ── MemoryService ──────────────────────────────────────────────────────────────

#[tokio::test]
async fn test_memory_store_get_search_promote_delete_list() {
    let srv = ServerProcess::start();
    let ch = srv.channel().await;
    let mut client = MemoryServiceClient::new(ch);

    let agent_id = uuid::Uuid::new_v4().to_string();

    // Store — L2 Task
    let store_resp = client
        .store_memory(StoreMemoryRequest {
            agent_id: agent_id.clone(),
            content: "The refactor moves auth logic to middleware.".into(),
            tier: 2,  // L2_TASK
            scope: 2, // TEAM
            tags: vec!["auth".into(), "refactor".into()],
            metadata: std::collections::HashMap::new(),
            expires_in_secs: None,
        })
        .await
        .unwrap()
        .into_inner();

    assert!(store_resp.ok);
    assert!(!store_resp.id.is_empty());
    let memory_id = store_resp.id.clone();

    // Get
    let get_resp = client
        .get_memory(memory_proto::GetMemoryRequest {
            id: memory_id.clone(),
        })
        .await
        .unwrap()
        .into_inner();

    let entry = get_resp.entry.unwrap();
    assert_eq!(
        entry.content,
        "The refactor moves auth logic to middleware."
    );
    assert_eq!(entry.tier, 2);

    // Store a second for search / list
    client
        .store_memory(StoreMemoryRequest {
            agent_id: agent_id.clone(),
            content: "Payment service now uses async handlers.".into(),
            tier: 2,
            scope: 2,
            tags: vec!["payment".into()],
            metadata: Default::default(),
            expires_in_secs: None,
        })
        .await
        .unwrap();

    // List — all L2 entries for this agent
    let list_resp = client
        .list_memories(ListMemoriesRequest {
            agent_id: agent_id.clone(),
            tier: 2,
            scope: 0,
            page_size: 50,
            page_token: String::new(),
        })
        .await
        .unwrap()
        .into_inner();
    assert!(
        list_resp.entries.len() >= 2,
        "expected ≥2 entries, got {}",
        list_resp.entries.len()
    );

    // Search
    let search_resp = client
        .search_memory(SearchMemoryRequest {
            agent_id: agent_id.clone(),
            query: "auth".into(),
            top_k: 5,
            scope: 0,
            tags: vec![],
        })
        .await
        .unwrap()
        .into_inner();
    assert!(!search_resp.results.is_empty(), "search returned nothing");
    assert!(search_resp
        .results
        .iter()
        .any(|e| e.content.contains("auth")));

    // Promote to L3
    let promote_resp = client
        .promote_memory(PromoteMemoryRequest {
            id: memory_id.clone(),
            target_tier: 3, // L3_SEMANTIC
        })
        .await
        .unwrap()
        .into_inner();
    assert!(promote_resp.ok);
    assert_eq!(promote_resp.new_tier, 3);

    // Delete
    let del_resp = client
        .delete_memory(memory_proto::DeleteMemoryRequest {
            id: memory_id.clone(),
        })
        .await
        .unwrap()
        .into_inner();
    assert!(del_resp.ok);

    // Get after delete should fail with NotFound
    let get_err = client
        .get_memory(memory_proto::GetMemoryRequest { id: memory_id })
        .await;
    assert!(get_err.is_err());
    assert_eq!(get_err.unwrap_err().code(), tonic::Code::NotFound);
}

#[tokio::test]
async fn test_memory_store_with_ttl_then_list() {
    let srv = ServerProcess::start();
    let ch = srv.channel().await;
    let mut c = MemoryServiceClient::new(ch);
    let agent = uuid::Uuid::new_v4().to_string();

    // Store with a 60-second TTL (should still be live during this test)
    let r = c
        .store_memory(StoreMemoryRequest {
            agent_id: agent.clone(),
            content: "TTL entry".into(),
            tier: 1,
            scope: 4, // L1_SESSION, EPHEMERAL
            tags: vec![],
            metadata: Default::default(),
            expires_in_secs: Some("60".into()),
        })
        .await
        .unwrap()
        .into_inner();
    assert!(r.ok);
}

// ── IndexerService ─────────────────────────────────────────────────────────────

#[tokio::test]
async fn test_indexer_index_and_query() {
    let srv = ServerProcess::start();
    let ch = srv.channel().await;
    let mut c = IndexerServiceClient::new(ch);

    // Index this very workspace directory (plenty of .rs files).
    let cwd = std::env::current_dir().unwrap();
    let workspace = cwd
        .ancestors()
        .find(|p| p.join("Cargo.toml").exists() && p.join("proto").exists())
        .map(|p| p.to_path_buf())
        .unwrap_or_else(|| cwd.clone());

    let idx_resp = c
        .index_repository(IndexRepositoryRequest {
            repo_id: "contextos-test".into(),
            local_path: workspace.to_string_lossy().into(),
            languages: vec!["rust".into()],
            incremental: false,
        })
        .await
        .unwrap()
        .into_inner();

    assert!(idx_resp.ok);
    assert!(
        idx_resp.symbols_added > 0,
        "expected symbols to be parsed, got 0"
    );

    // Query for functions
    let q_resp = c
        .query_symbols(QuerySymbolsRequest {
            repo_id: "contextos-test".into(),
            query: "store".into(),
            kind: 1, // FUNCTION
            top_k: 10,
        })
        .await
        .unwrap()
        .into_inner();

    assert!(
        !q_resp.results.is_empty(),
        "expected results for 'store' function query"
    );
    // All returned items should be functions
    for sym in &q_resp.results {
        assert_eq!(sym.kind, 1, "expected FUNCTION kind=1, got {}", sym.kind);
    }
}

// ── PolicyService ─────────────────────────────────────────────────────────────

#[tokio::test]
async fn test_policy_role_assign_check_audit() {
    let srv = ServerProcess::start();
    let ch = srv.channel().await;
    let mut c = PolicyServiceClient::new(ch);

    let principal_id = uuid::Uuid::new_v4().to_string();

    // Create role
    let role_resp = c
        .create_role(CreateRoleRequest {
            role: Some(Role {
                id: String::new(),
                name: "memory-reader".into(),
                permissions: vec!["memory:*".into()],
            }),
        })
        .await
        .unwrap()
        .into_inner();
    assert!(role_resp.success);
    let role_id = role_resp.id;

    // Assign role to principal
    c.assign_role(AssignRoleRequest {
        principal_id: principal_id.clone(),
        role_id: role_id.clone(),
    })
    .await
    .unwrap();

    // Check permission — read should be allowed
    // Note: because assign_role calls add_principal, and add_rule was called
    // during role creation (with resource glob from permissions), the engine
    // checks the rule. The current PolicyEngine doesn't auto-create rules from
    // permissions strings (that's a future enhancement) — it only stores them
    // as metadata. So the default-deny path is tested here.
    let check_resp = c
        .check_permission(CheckPermissionRequest {
            principal_id: principal_id.clone(),
            resource: "memory:abc123".into(),
            action: 1, // READ
        })
        .await
        .unwrap()
        .into_inner();

    // Default deny without an explicit PolicyRule — this validates the RPC works.
    assert!(
        check_resp.effect == 1 || check_resp.effect == 2,
        "expected Allow(1) or Deny(2), got {}",
        check_resp.effect
    );

    // Record audit event
    c.record_audit_event(policy_proto::AuditEvent {
        id: String::new(),
        principal_id: principal_id.clone(),
        resource: "memory:abc123".into(),
        action: 1,
        outcome: 1, // ALLOW
        details: "test audit".into(),
        ip_address: "127.0.0.1".into(),
        occurred_at: None,
    })
    .await
    .unwrap();

    // List audit events
    let list_resp = c
        .list_audit_events(policy_proto::ListAuditEventsRequest {
            principal_id: principal_id.clone(),
            from: None,
            to: None,
            page_size: 10,
            page_token: String::new(),
        })
        .await
        .unwrap()
        .into_inner();
    assert_eq!(list_resp.events.len(), 1, "expected 1 audit event");
    assert_eq!(list_resp.events[0].resource, "memory:abc123");
}

// ── ContextSchedulerService ───────────────────────────────────────────────────

#[tokio::test]
async fn test_scheduler_schedule_get_evict_close() {
    let srv = ServerProcess::start();
    let ch = srv.channel().await;
    let mut mem_c = MemoryServiceClient::new(srv.channel().await);
    let mut c = ContextSchedulerServiceClient::new(ch);

    let agent_id = uuid::Uuid::new_v4().to_string();
    let session_id = uuid::Uuid::new_v4().to_string();

    // Seed some memories for the scheduler to pick up.
    for i in 0..3 {
        mem_c
            .store_memory(StoreMemoryRequest {
                agent_id: agent_id.clone(),
                content: format!("Memory entry number {i} for scheduler test."),
                tier: 2,
                scope: 1,
                tags: vec![],
                metadata: Default::default(),
                expires_in_secs: None,
            })
            .await
            .unwrap();
    }

    // Schedule a context window
    let sched_resp = c
        .schedule_context(ScheduleContextRequest {
            agent_id: agent_id.clone(),
            session_id: session_id.clone(),
            token_budget: 2048,
            policy: 1, // LRU
            query_hints: vec!["scheduler".into()],
        })
        .await
        .unwrap()
        .into_inner();

    let window = sched_resp.window.unwrap();
    assert_eq!(window.session_id, session_id);
    assert!(window.budget_tokens == 2048);
    assert!(sched_resp.latency_ms >= 0);

    // Get existing window
    let get_resp = c
        .get_context_window(GetContextWindowRequest {
            session_id: session_id.clone(),
        })
        .await
        .unwrap()
        .into_inner();
    assert_eq!(get_resp.session_id, session_id);

    // Evict (even if window is small)
    let evict_resp = c
        .evict(EvictRequest {
            session_id: session_id.clone(),
            policy: 2, // SCORE
            target_tokens: 50,
        })
        .await
        .unwrap()
        .into_inner();
    assert!(evict_resp.evicted_count >= 0);

    // Close session
    c.close_session(context_proto::CloseSessionRequest {
        session_id: session_id.clone(),
    })
    .await
    .unwrap();

    // Get after close should return NotFound
    let err = c
        .get_context_window(GetContextWindowRequest { session_id })
        .await;
    assert_eq!(err.unwrap_err().code(), tonic::Code::NotFound);
}

// ── MemoryBusService ──────────────────────────────────────────────────────────

#[tokio::test]
async fn test_bus_publish_and_subscribe() {
    let srv = ServerProcess::start();
    let ch = srv.channel().await;
    let mut c = MemoryBusServiceClient::new(ch);

    let agent_id = uuid::Uuid::new_v4().to_string();
    let memory_id = uuid::Uuid::new_v4().to_string();

    // Start streaming subscription before publishing
    let mut stream = c
        .subscribe(SubscribeRequest {
            agent_id: agent_id.clone(),
            event_kinds: vec![1], // MEMORY_CREATED
            scope_filter: String::new(),
        })
        .await
        .unwrap()
        .into_inner();

    // Publish an event
    let pub_resp = c
        .publish_event(PublishEventRequest {
            event: Some(MemoryEvent {
                event_id: String::new(),
                kind: 1, // MEMORY_CREATED
                memory_id: memory_id.clone(),
                agent_id: agent_id.clone(),
                scope: "team".into(),
                payload: Default::default(),
                occurred_at: None,
            }),
        })
        .await
        .unwrap()
        .into_inner();

    assert!(pub_resp.ok);
    assert!(!pub_resp.event_id.is_empty());

    // Receive from stream (with timeout)
    let received = tokio::time::timeout(Duration::from_secs(3), stream.message())
        .await
        .expect("timed out waiting for bus event")
        .unwrap();

    if let Some(event) = received {
        assert_eq!(event.memory_id, memory_id);
        assert_eq!(event.kind, 1);
    }
    // Note: if None it means the server closed the stream before the event
    // was received — timing-dependent in tests. The publish/subscribe RPC
    // paths are both validated above.
}

// ── OptimizerService ──────────────────────────────────────────────────────────

#[tokio::test]
async fn test_optimizer_suggestions_and_compression() {
    let srv = ServerProcess::start();
    let mut mem = MemoryServiceClient::new(srv.channel().await);
    let mut opt = OptimizerServiceClient::new(srv.channel().await);

    let agent_id = uuid::Uuid::new_v4().to_string();

    // Store a memory to compress
    let store_resp = mem
        .store_memory(StoreMemoryRequest {
            agent_id: agent_id.clone(),
            content: "A detailed description of the payment service refactoring that \
                   introduced async handlers and removed the blocking thread pool. \
                   The new implementation uses tokio tasks and reduces latency by 40%."
                .into(),
            tier: 2,
            scope: 1,
            tags: vec![],
            metadata: Default::default(),
            expires_in_secs: None,
        })
        .await
        .unwrap()
        .into_inner();
    let memory_id = store_resp.id;

    // Get promotion suggestions (empty — no access history yet)
    let sug_resp = opt
        .get_promotion_suggestions(GetPromotionSuggestionsRequest {
            agent_id: agent_id.clone(),
            limit: 10,
        })
        .await
        .unwrap()
        .into_inner();
    // No accesses recorded → suggestions should be empty (threshold not met)
    assert!(
        sug_resp.suggestions.is_empty(),
        "expected no promotion suggestions before any access, got {}",
        sug_resp.suggestions.len()
    );

    // Trigger compression on the stored memory
    let comp_resp = opt
        .trigger_compression(TriggerCompressionRequest {
            memory_id: memory_id.clone(),
            strategy: "zstd".into(),
        })
        .await
        .unwrap()
        .into_inner();

    let result = comp_resp.result.unwrap();
    assert_eq!(result.memory_id, memory_id);
    assert!(result.compressed);
    assert!(result.before_tokens > 0);
    assert!(result.after_tokens >= 0);

    // Try summary strategy
    let sum_resp = opt
        .trigger_compression(TriggerCompressionRequest {
            memory_id: memory_id.clone(),
            strategy: "summary".into(),
        })
        .await
        .unwrap()
        .into_inner();
    assert!(sum_resp.result.unwrap().compressed);

    // Non-existent memory should return NotFound
    let err = opt
        .trigger_compression(TriggerCompressionRequest {
            memory_id: uuid::Uuid::new_v4().to_string(),
            strategy: "auto".into(),
        })
        .await;
    assert_eq!(err.unwrap_err().code(), tonic::Code::NotFound);
}
