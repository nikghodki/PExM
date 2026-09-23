//! ContextOS Context Scheduler
//!
//! Determines retrieval strategy, memory tier selection, token allocation,
//! and eviction policy for context windows delivered to AI agents.

pub mod eviction;
pub mod packer;

pub use eviction::EvictionPolicy;
pub use packer::{ContextEntry, ContextScheduler, ContextWindow};
