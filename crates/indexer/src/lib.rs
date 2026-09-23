//! ContextOS Code Memory Engine
//!
//! AST-based symbol indexing via tree-sitter, call graph construction,
//! and Git-aware diff/delta tracking.

pub mod ast;
pub mod git;
pub mod symbols;

pub use ast::parser::AstParser;
pub use git::tracker::{CommitDiff, FunctionDelta, GitTracker};
pub use symbols::graph::SymbolGraph;
pub use symbols::{SymbolKind, SymbolNode};
