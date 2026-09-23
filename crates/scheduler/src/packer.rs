//! Token-aware context tree builder.

use std::collections::HashMap;
use std::sync::{Arc, RwLock};
use uuid::Uuid;

use crate::eviction::EvictionPolicy;

/// A single entry within a context window.
#[derive(Debug, Clone)]
pub struct ContextEntry {
    pub id: String,
    pub content: String,
    pub relevance: f32,
    pub token_count: i32,
    pub source_tier: String,
    pub source_id: String,
}

/// A scheduled context window for one agent session.
#[derive(Debug, Clone)]
pub struct ContextWindow {
    pub session_id: String,
    pub total_tokens: i32,
    pub budget_tokens: i32,
    pub entries: Vec<ContextEntry>,
    pub eviction_policy: EvictionPolicy,
}

impl ContextWindow {
    pub fn used_tokens(&self) -> i32 {
        self.entries.iter().map(|e| e.token_count).sum()
    }

    pub fn remaining_tokens(&self) -> i32 {
        self.budget_tokens - self.used_tokens()
    }

    /// Try to add an entry if budget allows; returns false if insufficient budget.
    pub fn try_add(&mut self, entry: ContextEntry) -> bool {
        if self.used_tokens() + entry.token_count > self.budget_tokens {
            return false;
        }
        self.entries.push(entry);
        true
    }
}

/// Schedules and manages context windows across agent sessions.
pub struct ContextScheduler {
    sessions: Arc<RwLock<HashMap<String, ContextWindow>>>,
}

impl ContextScheduler {
    pub fn new() -> Self {
        Self {
            sessions: Arc::new(RwLock::new(HashMap::new())),
        }
    }

    /// Create or refresh a context window for the given session.
    pub fn schedule(
        &self,
        _agent_id: &Uuid,
        session_id: &str,
        token_budget: i32,
        policy: EvictionPolicy,
        candidates: Vec<ContextEntry>,
    ) -> ContextWindow {
        let mut window = ContextWindow {
            session_id: session_id.to_owned(),
            total_tokens: 0,
            budget_tokens: token_budget,
            entries: Vec::new(),
            eviction_policy: policy,
        };

        // Greedy packing: highest relevance first
        let mut sorted = candidates;
        sorted.sort_by(|a, b| b.relevance.partial_cmp(&a.relevance).unwrap());

        for entry in sorted {
            window.try_add(entry);
        }
        window.total_tokens = window.used_tokens();

        let mut sessions = self.sessions.write().expect("sessions write");
        sessions.insert(session_id.to_owned(), window.clone());
        window
    }

    pub fn get(&self, session_id: &str) -> Option<ContextWindow> {
        self.sessions
            .read()
            .expect("sessions read")
            .get(session_id)
            .cloned()
    }

    pub fn close(&self, session_id: &str) {
        let mut sessions = self.sessions.write().expect("sessions write");
        sessions.remove(session_id);
    }

    pub fn evict(
        &self,
        session_id: &str,
        policy: EvictionPolicy,
        target_tokens: i32,
    ) -> (usize, i32) {
        let mut sessions = self.sessions.write().expect("sessions write");
        if let Some(window) = sessions.get_mut(session_id) {
            policy.evict(&mut window.entries, target_tokens)
        } else {
            (0, 0)
        }
    }
}

impl Default for ContextScheduler {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::eviction::EvictionPolicy;
    use uuid::Uuid;

    fn make_entry(id: &str, tokens: i32, relevance: f32) -> ContextEntry {
        ContextEntry {
            id: id.into(),
            content: "x".into(),
            relevance,
            token_count: tokens,
            source_tier: "L2".into(),
            source_id: id.into(),
        }
    }

    #[test]
    fn schedule_respects_token_budget() {
        let sched = ContextScheduler::new();
        let agent = Uuid::new_v4();
        let entries = vec![
            make_entry("a", 100, 0.9),
            make_entry("b", 100, 0.8),
            make_entry("c", 100, 0.7),
        ];
        let w = sched.schedule(&agent, "s1", 250, EvictionPolicy::Lru, entries);
        assert!(w.used_tokens() <= 250);
        assert_eq!(w.entries.len(), 2); // 100+100=200 ≤ 250; third would exceed
    }

    #[test]
    fn evict_lru_reduces_token_count() {
        let sched = ContextScheduler::new();
        let agent = Uuid::new_v4();
        let entries = vec![make_entry("a", 50, 0.9), make_entry("b", 50, 0.1)];
        sched.schedule(&agent, "s2", 200, EvictionPolicy::Score, entries);
        let (count, freed) = sched.evict("s2", EvictionPolicy::Score, 40);
        assert_eq!(count, 1);
        assert_eq!(freed, 50);
    }

    #[test]
    fn close_session_removes_window() {
        let sched = ContextScheduler::new();
        let agent = Uuid::new_v4();
        sched.schedule(&agent, "s3", 1000, EvictionPolicy::Fifo, vec![]);
        sched.close("s3");
        assert!(sched.get("s3").is_none());
    }
}
