//! L2 Task Memory — persisted structured task memories backed by RocksDB.

use anyhow::Result;
use std::sync::Arc;
use uuid::Uuid;

use super::MemoryEntry;
use crate::storage::{RocksStore, CF_L2};

pub struct L2TaskMemory {
    store: Arc<RocksStore>,
}

impl L2TaskMemory {
    pub fn new(store: Arc<RocksStore>) -> Self {
        Self { store }
    }

    pub fn insert(&self, entry: MemoryEntry) -> Result<()> {
        let key = entry.id.as_bytes().to_vec();
        let value = serde_json::to_vec(&entry)?;
        self.store.put(CF_L2, &key, &value)?;
        Ok(())
    }

    pub fn get(&self, id: &Uuid) -> Option<MemoryEntry> {
        let bytes = self.store.get(CF_L2, id.as_bytes()).ok()??;
        serde_json::from_slice(&bytes).ok()
    }

    pub fn remove(&self, id: &Uuid) -> Result<()> {
        self.store.delete(CF_L2, id.as_bytes())
    }

    pub fn scan_all(&self) -> Result<Vec<MemoryEntry>> {
        let pairs = self.store.scan(CF_L2)?;
        Ok(pairs
            .into_iter()
            .filter_map(|(_, v)| serde_json::from_slice(&v).ok())
            .collect())
    }
}
