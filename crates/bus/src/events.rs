//! Memory bus event definitions.

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use uuid::Uuid;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum MemoryEventKind {
    MemoryCreated,
    MemoryUpdated,
    MemoryPromoted,
    MemoryArchived,
    ScopeShared,
    AgentSubscribed,
    AgentUnsubscribed,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemoryEvent {
    pub event_id: Uuid,
    pub kind: MemoryEventKind,
    pub memory_id: Uuid,
    pub agent_id: Uuid,
    pub scope: String,
    pub payload: HashMap<String, String>,
    pub occurred_at: DateTime<Utc>,
}

impl MemoryEvent {
    pub fn new(
        kind: MemoryEventKind,
        memory_id: Uuid,
        agent_id: Uuid,
        scope: impl Into<String>,
    ) -> Self {
        Self {
            event_id: Uuid::new_v4(),
            kind,
            memory_id,
            agent_id,
            scope: scope.into(),
            payload: HashMap::new(),
            occurred_at: Utc::now(),
        }
    }
}
