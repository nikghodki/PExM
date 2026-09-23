//! ContextOS gRPC Server — all phases wired.

mod bus_svc;
mod conv;
mod indexer_svc;
mod memory_svc;
mod optimizer_svc;
mod policy_svc;
mod scheduler_svc;

use std::net::SocketAddr;
use std::sync::Arc;

use anyhow::Result;
use tonic::transport::Server;
use tracing::info;
use tracing_subscriber::EnvFilter;

// Proto-generated server wrappers
use bus_svc::proto::memory_bus_service_server::MemoryBusServiceServer;
use indexer_svc::proto::indexer_service_server::IndexerServiceServer;
use memory_svc::proto::memory_service_server::MemoryServiceServer;
use optimizer_svc::proto::optimizer_service_server::OptimizerServiceServer;
use policy_svc::proto::policy_service_server::PolicyServiceServer;
use scheduler_svc::proto::context_scheduler_service_server::ContextSchedulerServiceServer;

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(
            EnvFilter::try_from_env("CONTEXTOS_LOG").unwrap_or_else(|_| EnvFilter::new("info")),
        )
        .init();

    let addr: SocketAddr = std::env::var("CONTEXTOS_BIND")
        .unwrap_or_else(|_| "[::1]:50051".to_owned())
        .parse()?;

    info!(%addr, "ContextOS server starting");

    // ── Persistent storage ──────────────────────────────────────────────────
    let rocksdb_path = std::env::var("CONTEXTOS_ROCKSDB_PATH")
        .unwrap_or_else(|_| "./contextos-data/rocksdb".to_owned());
    std::fs::create_dir_all(&rocksdb_path)?;
    let store = contextos_kernel::storage::RocksStore::open(&rocksdb_path)?;
    let kernel = Arc::new(contextos_kernel::MemoryKernel::new(store));

    // ── Service implementations ─────────────────────────────────────────────
    // Phase 1
    let memory_svc = memory_svc::MemoryServiceImpl::new(Arc::clone(&kernel));
    let indexer_svc = indexer_svc::IndexerServiceImpl::new();

    // Phase 2
    let policy_engine = contextos_policy::PolicyEngine::new();
    let audit_log = contextos_policy::AuditLog::new();
    let policy_svc = policy_svc::PolicyServiceImpl::new(policy_engine, audit_log);

    let bus = contextos_bus::MemoryBus::new();
    let bus_svc = bus_svc::BusServiceImpl::new(bus);

    let scheduler = contextos_scheduler::ContextScheduler::new();
    let scheduler_svc = scheduler_svc::SchedulerServiceImpl::new(scheduler, Arc::clone(&kernel));

    // Phase 3
    let optimizer_svc = optimizer_svc::OptimizerServiceImpl::new(Arc::clone(&kernel));

    // ── Health check ────────────────────────────────────────────────────────
    let (mut health_reporter, health_svc) = tonic_health::server::health_reporter();
    health_reporter
        .set_service_status("", tonic_health::ServingStatus::Serving)
        .await;

    info!("All services ready — listening on {addr}");

    Server::builder()
        .add_service(health_svc)
        .add_service(MemoryServiceServer::new(memory_svc))
        .add_service(IndexerServiceServer::new(indexer_svc))
        .add_service(PolicyServiceServer::new(policy_svc))
        .add_service(MemoryBusServiceServer::new(bus_svc))
        .add_service(ContextSchedulerServiceServer::new(scheduler_svc))
        .add_service(OptimizerServiceServer::new(optimizer_svc))
        .serve(addr)
        .await?;

    Ok(())
}
