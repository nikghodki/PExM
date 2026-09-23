//! Memory tier routing and core types.

pub mod l1_session;
pub mod l2_task;
pub mod l3_semantic;
pub mod l4_archive;

use anyhow::Result;
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use uuid::Uuid;

use crate::storage::RocksStore;
use l1_session::L1SessionMemory;
use l2_task::L2TaskMemory;
use l3_semantic::L3SemanticMemory;
use l4_archive::L4ArchiveMemory;

// ─── Core types ───────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum MemoryTier {
    L1Session = 1,
    L2Task = 2,
    L3Semantic = 3,
    L4Archive = 4,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Scope {
    Private = 1,
    Team = 2,
    Org = 3,
    Ephemeral = 4,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemoryEntry {
    pub id: Uuid,
    pub agent_id: Uuid,
    pub content: String,
    pub embedding: Vec<f32>,
    pub tier: MemoryTier,
    pub scope: Scope,
    pub score: f32,
    pub tags: Vec<String>,
    pub metadata: HashMap<String, String>,
    pub created_at: DateTime<Utc>,
    pub accessed_at: DateTime<Utc>,
    pub expires_at: Option<DateTime<Utc>>,
}

impl MemoryEntry {
    pub fn new(agent_id: Uuid, content: impl Into<String>, tier: MemoryTier) -> Self {
        let now = Utc::now();
        Self {
            id: Uuid::new_v4(),
            agent_id,
            content: content.into(),
            embedding: Vec::new(),
            tier,
            scope: Scope::Private,
            score: 0.5,
            tags: Vec::new(),
            metadata: HashMap::new(),
            created_at: now,
            accessed_at: now,
            expires_at: None,
        }
    }

    pub fn is_expired(&self) -> bool {
        self.expires_at.map(|e| Utc::now() > e).unwrap_or(false)
    }
}

// ─── Memory Kernel ────────────────────────────────────────────────────────────

/// Unified facade over all four memory tiers.
pub struct MemoryKernel {
    pub l1: L1SessionMemory,
    pub l2: L2TaskMemory,
    pub l3: L3SemanticMemory,
    pub l4: L4ArchiveMemory,
}

impl MemoryKernel {
    pub fn new(store: RocksStore) -> Self {
        let store = std::sync::Arc::new(store);
        Self {
            l1: L1SessionMemory::new(),
            l2: L2TaskMemory::new(store.clone()),
            l3: L3SemanticMemory::new(store.clone()),
            l4: L4ArchiveMemory::new(store),
        }
    }

    /// Store a memory entry in the appropriate tier.
    pub fn store(&self, entry: MemoryEntry) -> Result<Uuid> {
        let id = entry.id;
        match entry.tier {
            MemoryTier::L1Session => self.l1.insert(entry),
            MemoryTier::L2Task => self.l2.insert(entry)?,
            MemoryTier::L3Semantic => self.l3.insert(entry)?,
            MemoryTier::L4Archive => self.l4.insert(entry)?,
        }
        Ok(id)
    }

    /// Retrieve a memory entry by ID, searching all tiers.
    pub fn get(&self, id: &Uuid) -> Option<MemoryEntry> {
        self.l1
            .get(id)
            .or_else(|| self.l2.get(id))
            .or_else(|| self.l3.get(id))
            .or_else(|| self.l4.get(id))
    }

    /// Promote a memory entry to a higher tier.
    pub fn promote(&self, id: &Uuid, target: MemoryTier) -> Result<()> {
        if let Some(mut entry) = self.get(id) {
            self.delete(id)?;
            entry.tier = target;
            self.store(entry)?;
        }
        Ok(())
    }

    /// Delete a memory entry from whichever tier holds it.
    pub fn delete(&self, id: &Uuid) -> Result<()> {
        self.l1.remove(id);
        self.l2.remove(id)?;
        self.l3.remove(id)?;
        self.l4.remove(id)?;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use uuid::Uuid;

    #[test]
    fn memory_entry_new_sets_defaults() {
        let agent = Uuid::new_v4();
        let e = MemoryEntry::new(agent, "hello", MemoryTier::L1Session);
        assert_eq!(e.agent_id, agent);
        assert_eq!(e.content, "hello");
        assert_eq!(e.tier, MemoryTier::L1Session);
        assert!(!e.is_expired());
    }

    #[test]
    fn memory_entry_expired_when_past() {
        let mut e = MemoryEntry::new(Uuid::new_v4(), "x", MemoryTier::L2Task);
        e.expires_at = Some(Utc::now() - chrono::Duration::seconds(1));
        assert!(e.is_expired());
    }

    #[test]
    fn l1_insert_get_remove() {
        use super::l1_session::L1SessionMemory;
        let l1 = L1SessionMemory::new();
        let e = MemoryEntry::new(Uuid::new_v4(), "test", MemoryTier::L1Session);
        let id = e.id;
        l1.insert(e);
        assert!(l1.get(&id).is_some());
        l1.remove(&id);
        assert!(l1.get(&id).is_none());
    }

    #[test]
    fn l1_evicts_expired() {
        use super::l1_session::L1SessionMemory;
        let l1 = L1SessionMemory::new();
        let mut e = MemoryEntry::new(Uuid::new_v4(), "old", MemoryTier::L1Session);
        e.expires_at = Some(Utc::now() - chrono::Duration::seconds(1));
        l1.insert(e);
        assert_eq!(l1.evict_expired(), 1);
        assert_eq!(l1.len(), 0);
    }
}
