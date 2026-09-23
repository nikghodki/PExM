//! ContextOS Self-Optimizing Memory (Phase 3)
//!
//! Predicts which memories should be promoted/demoted based on access patterns
//! and applies LLM-assisted or delta compression to reduce token footprint.

pub mod compressor;
pub mod predictor;

pub use compressor::MemoryCompressor;
pub use predictor::AccessPredictor;
