//! ContextOS Distributed Memory Bus
//!
//! Phase 2: event-driven architecture for real-time multi-agent memory
//! synchronization. Uses an in-process tokio broadcast channel for local
//! deployments, with a Kafka bridge stub for distributed deployments.

pub mod events;
pub mod pubsub;

pub use events::{MemoryEvent, MemoryEventKind};
pub use pubsub::MemoryBus;
