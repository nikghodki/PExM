//! L3 Semantic Memory — graph-linked semantic memories with embedding storage.

use anyhow::Result;
use std::sync::Arc;
use uuid::Uuid;

use super::MemoryEntry;
use crate::storage::{RocksStore, CF_L3};

pub struct L3SemanticMemory {
    store: Arc<RocksStore>,
}

impl L3SemanticMemory {
    pub fn new(store: Arc<RocksStore>) -> Self {
        Self { store }
    }

    pub fn insert(&self, entry: MemoryEntry) -> Result<()> {
        let key = entry.id.as_bytes().to_vec();
        let value = serde_json::to_vec(&entry)?;
        self.store.put(CF_L3, &key, &value)?;
        Ok(())
    }

    pub fn get(&self, id: &Uuid) -> Option<MemoryEntry> {
        let bytes = self.store.get(CF_L3, id.as_bytes()).ok()??;
        serde_json::from_slice(&bytes).ok()
    }

    pub fn remove(&self, id: &Uuid) -> Result<()> {
        self.store.delete(CF_L3, id.as_bytes())
    }

    /// Approximate nearest-neighbour search by cosine similarity.
    /// For production, replace this with a proper ANN index (e.g. HNSW).
    pub fn search(&self, query_embedding: &[f32], top_k: usize) -> Result<Vec<MemoryEntry>> {
        let pairs = self.store.scan(CF_L3)?;
        let mut scored: Vec<(f32, MemoryEntry)> = pairs
            .into_iter()
            .filter_map(|(_, v)| serde_json::from_slice::<MemoryEntry>(&v).ok())
            .filter(|e| !e.embedding.is_empty())
            .map(|e| (cosine_similarity(&e.embedding, query_embedding), e))
            .collect();
        scored.sort_by(|a, b| b.0.partial_cmp(&a.0).unwrap());
        Ok(scored.into_iter().take(top_k).map(|(_, e)| e).collect())
    }
}

fn cosine_similarity(a: &[f32], b: &[f32]) -> f32 {
    if a.len() != b.len() {
        return 0.0;
    }
    let dot: f32 = a.iter().zip(b).map(|(x, y)| x * y).sum();
    let na: f32 = a.iter().map(|x| x * x).sum::<f32>().sqrt();
    let nb: f32 = b.iter().map(|x| x * x).sum::<f32>().sqrt();
    if na == 0.0 || nb == 0.0 {
        0.0
    } else {
        dot / (na * nb)
    }
}
