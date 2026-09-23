//! L1 Session Memory — hot in-process cache with TTL eviction.

use std::collections::HashMap;
use std::sync::{Arc, RwLock};
use uuid::Uuid;

use super::MemoryEntry;

/// In-process hash map with TTL-based eviction.
/// Thread-safe via RwLock so it can be shared across async tasks.
pub struct L1SessionMemory {
    inner: Arc<RwLock<HashMap<Uuid, MemoryEntry>>>,
}

impl L1SessionMemory {
    pub fn new() -> Self {
        Self {
            inner: Arc::new(RwLock::new(HashMap::new())),
        }
    }

    pub fn insert(&self, entry: MemoryEntry) {
        let mut map = self.inner.write().expect("l1 write lock");
        map.insert(entry.id, entry);
    }

    pub fn get(&self, id: &Uuid) -> Option<MemoryEntry> {
        let map = self.inner.read().expect("l1 read lock");
        let entry = map.get(id)?;
        if entry.is_expired() {
            return None;
        }
        Some(entry.clone())
    }

    pub fn remove(&self, id: &Uuid) {
        let mut map = self.inner.write().expect("l1 write lock");
        map.remove(id);
    }

    /// Evict all expired entries and return count removed.
    pub fn evict_expired(&self) -> usize {
        let mut map = self.inner.write().expect("l1 write lock");
        let before = map.len();
        map.retain(|_, v| !v.is_expired());
        before - map.len()
    }

    pub fn len(&self) -> usize {
        self.inner.read().expect("l1 read lock").len()
    }

    pub fn is_empty(&self) -> bool {
        self.inner.read().expect("l1 read lock").is_empty()
    }
}

impl Default for L1SessionMemory {
    fn default() -> Self {
        Self::new()
    }
}
