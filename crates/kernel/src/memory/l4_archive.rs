//! L4 Archive Memory — compressed long-term storage using zstd.

use anyhow::Result;
use std::sync::Arc;
use uuid::Uuid;

use super::MemoryEntry;
use crate::storage::{RocksStore, CF_L4};

pub struct L4ArchiveMemory {
    store: Arc<RocksStore>,
}

impl L4ArchiveMemory {
    pub fn new(store: Arc<RocksStore>) -> Self {
        Self { store }
    }

    pub fn insert(&self, entry: MemoryEntry) -> Result<()> {
        let key = entry.id.as_bytes().to_vec();
        let json = serde_json::to_vec(&entry)?;
        let compressed = zstd::encode_all(json.as_slice(), 3)?;
        self.store.put(CF_L4, &key, &compressed)?;
        Ok(())
    }

    pub fn get(&self, id: &Uuid) -> Option<MemoryEntry> {
        let compressed = self.store.get(CF_L4, id.as_bytes()).ok()??;
        let json = zstd::decode_all(compressed.as_slice()).ok()?;
        serde_json::from_slice(&json).ok()
    }

    pub fn remove(&self, id: &Uuid) -> Result<()> {
        self.store.delete(CF_L4, id.as_bytes())
    }

    /// List all archived entry IDs (for inventory or bulk restore).
    pub fn list_ids(&self) -> Result<Vec<Uuid>> {
        let pairs = self.store.scan(CF_L4)?;
        Ok(pairs
            .into_iter()
            .filter_map(|(k, _)| {
                let arr: [u8; 16] = k.try_into().ok()?;
                Some(Uuid::from_bytes(arr))
            })
            .collect())
    }
}
