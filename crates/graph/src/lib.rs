//! ContextOS Enterprise Memory Graph
//!
//! Graph model with typed nodes (CodeSymbol, AgentNote, DecisionRecord, …)
//! and typed edges (depends_on, references, modified_by, …).
//! Supports scope-filtered traversal (Private / Team / Org / Ephemeral).

pub mod edges;
pub mod nodes;
pub mod traversal;

pub use edges::EdgeType;
pub use nodes::{MemoryNode, NodeType, Scope};
pub use traversal::MemoryGraph;
