pub mod graph;
pub use graph::SymbolGraph;

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SymbolKind {
    Function,
    Class,
    Struct,
    Trait,
    Interface,
    Module,
    Variable,
    Constant,
    TypeAlias,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SymbolNode {
    pub id: String,
    pub repo_id: String,
    pub file_path: String,
    pub name: String,
    pub qualified_name: String,
    pub kind: SymbolKind,
    pub start_line: i32,
    pub end_line: i32,
    pub signature: String,
    pub docstring: String,
    pub callers: Vec<String>,
    pub callees: Vec<String>,
    pub deps: Vec<String>, // cross-repo dependency IDs
    pub metadata: HashMap<String, String>,
}
