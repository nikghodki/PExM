//! Memory graph node types.

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use uuid::Uuid;

/// Visibility / sharing scope for a node.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Scope {
    Private,
    Team,
    Org,
    Ephemeral,
}

/// Discriminant for the node payload.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum NodeType {
    CodeSymbol,
    AgentNote,
    DecisionRecord,
    CommitDiff,
    TestFailure,
    Documentation,
}

/// A node in the enterprise memory graph.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemoryNode {
    pub id: Uuid,
    pub node_type: NodeType,
    pub scope: Scope,
    pub label: String,
    pub content: String,
    pub agent_id: Option<Uuid>,
    pub repo_id: Option<String>,
    pub metadata: HashMap<String, String>,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

impl MemoryNode {
    pub fn new(
        node_type: NodeType,
        scope: Scope,
        label: impl Into<String>,
        content: impl Into<String>,
    ) -> Self {
        let now = Utc::now();
        Self {
            id: Uuid::new_v4(),
            node_type,
            scope,
            label: label.into(),
            content: content.into(),
            agent_id: None,
            repo_id: None,
            metadata: HashMap::new(),
            created_at: now,
            updated_at: now,
        }
    }
}
