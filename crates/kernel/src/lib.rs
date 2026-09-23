//! ContextOS Memory Kernel
//!
//! Provides tiered memory storage (L1–L4), memory scoring & promotion,
//! and retrieval orchestration backed by RocksDB.

pub mod memory;
pub mod retrieval;
pub mod scoring;
pub mod storage;

// Re-export the primary public API
pub use memory::{MemoryEntry, MemoryKernel, MemoryTier, Scope};
pub use retrieval::RetrievalOrchestrator;
pub use scoring::MemoryScorer;

/// Default token budget for a single context window (approx. 128k tokens).
pub const DEFAULT_TOKEN_BUDGET: usize = 128_000;
