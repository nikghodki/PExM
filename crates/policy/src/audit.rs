//! Append-only audit log for all memory access events.

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::sync::{Arc, RwLock};
use uuid::Uuid;

use crate::rbac::{Action, Effect};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AuditEvent {
    pub id: Uuid,
    pub principal_id: Uuid,
    pub resource: String,
    pub action: Action,
    pub outcome: Effect,
    pub details: String,
    pub ip_address: String,
    pub occurred_at: DateTime<Utc>,
}

impl AuditEvent {
    pub fn new(principal_id: Uuid, resource: String, action: Action, outcome: Effect) -> Self {
        Self {
            id: Uuid::new_v4(),
            principal_id,
            resource,
            action,
            outcome,
            details: String::new(),
            ip_address: String::new(),
            occurred_at: Utc::now(),
        }
    }
}

/// Thread-safe append-only audit log.
/// Production: persist to RocksDB or external SIEM system.
#[derive(Clone)]
pub struct AuditLog {
    entries: Arc<RwLock<Vec<AuditEvent>>>,
}

impl AuditLog {
    pub fn new() -> Self {
        Self {
            entries: Arc::new(RwLock::new(Vec::new())),
        }
    }

    pub fn record(&self, event: AuditEvent) {
        let mut entries = self.entries.write().expect("audit write");
        entries.push(event);
    }

    /// Query events for a principal within a time range.
    pub fn events_for_principal(
        &self,
        principal_id: &Uuid,
        from: DateTime<Utc>,
        to: DateTime<Utc>,
    ) -> Vec<AuditEvent> {
        let entries = self.entries.read().expect("audit read");
        entries
            .iter()
            .filter(|e| e.principal_id == *principal_id)
            .filter(|e| e.occurred_at >= from && e.occurred_at <= to)
            .cloned()
            .collect()
    }

    pub fn all(&self) -> Vec<AuditEvent> {
        self.entries.read().expect("audit read").clone()
    }

    pub fn len(&self) -> usize {
        self.entries.read().expect("audit read").len()
    }
}

impl Default for AuditLog {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn record_and_query_events() {
        let log = AuditLog::new();
        let pid = uuid::Uuid::new_v4();
        let from = Utc::now() - chrono::Duration::seconds(1);

        log.record(AuditEvent::new(
            pid,
            "memory:x".into(),
            Action::Read,
            Effect::Allow,
        ));
        log.record(AuditEvent::new(
            pid,
            "memory:y".into(),
            Action::Write,
            Effect::Deny,
        ));

        let to = Utc::now() + chrono::Duration::seconds(1);
        let events = log.events_for_principal(&pid, from, to);
        assert_eq!(events.len(), 2);
        assert_eq!(log.len(), 2);
    }

    #[test]
    fn query_excludes_other_principals() {
        let log = AuditLog::new();
        let pid1 = uuid::Uuid::new_v4();
        let pid2 = uuid::Uuid::new_v4();
        let from = Utc::now() - chrono::Duration::seconds(1);
        let to = Utc::now() + chrono::Duration::seconds(1);

        log.record(AuditEvent::new(
            pid1,
            "r".into(),
            Action::Read,
            Effect::Allow,
        ));
        log.record(AuditEvent::new(
            pid2,
            "r".into(),
            Action::Read,
            Effect::Allow,
        ));

        assert_eq!(log.events_for_principal(&pid1, from, to).len(), 1);
    }
}
