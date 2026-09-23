//! Memory graph edge types.

use serde::{Deserialize, Serialize};

/// Typed relationship between two memory nodes.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum EdgeType {
    /// B depends on A (e.g. import, function call)
    DependsOn,
    /// B references A (looser coupling than DependsOn)
    References,
    /// A was modified by commit / agent B
    ModifiedBy,
    /// B was derived from A (e.g. summary, refactor)
    DerivedFrom,
    /// B supersedes A (newer version replaces older)
    Supersedes,
}

impl EdgeType {
    pub fn as_str(&self) -> &'static str {
        match self {
            EdgeType::DependsOn => "depends_on",
            EdgeType::References => "references",
            EdgeType::ModifiedBy => "modified_by",
            EdgeType::DerivedFrom => "derived_from",
            EdgeType::Supersedes => "supersedes",
        }
    }
}
