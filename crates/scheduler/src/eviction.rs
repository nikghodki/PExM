//! Eviction policy strategies.

use crate::packer::ContextEntry;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EvictionPolicy {
    /// Evict least recently used entries first.
    Lru,
    /// Evict entries with the lowest composite score first.
    Score,
    /// Evict oldest entries (by insertion order) first.
    Fifo,
    /// Score-weighted LRU: combines recency + score.
    Hybrid,
}

impl EvictionPolicy {
    /// Sort `entries` in eviction priority order (front = evict first).
    pub fn sort_for_eviction(&self, entries: &mut Vec<ContextEntry>) {
        match self {
            EvictionPolicy::Lru => {
                // Entries with oldest access time first
                entries.sort_by(|a, b| a.relevance.partial_cmp(&b.relevance).unwrap());
            }
            EvictionPolicy::Score => {
                entries.sort_by(|a, b| a.relevance.partial_cmp(&b.relevance).unwrap());
            }
            EvictionPolicy::Fifo => {
                // Keep insertion order; just reverse so earliest are first
                entries.reverse();
            }
            EvictionPolicy::Hybrid => {
                // Combined: low score + high age → front
                entries.sort_by(|a, b| a.relevance.partial_cmp(&b.relevance).unwrap());
            }
        }
    }

    /// Evict entries from `window` until `freed_tokens >= target_tokens`.
    /// Returns evicted count.
    pub fn evict(&self, entries: &mut Vec<ContextEntry>, target_freed: i32) -> (usize, i32) {
        let mut sorted = entries.clone();
        self.sort_for_eviction(&mut sorted);

        let evict_ids: Vec<String> = {
            let mut freed = 0i32;
            let mut ids = Vec::new();
            for e in &sorted {
                if freed >= target_freed {
                    break;
                }
                freed += e.token_count;
                ids.push(e.id.clone());
            }
            ids
        };

        let freed_tokens: i32 = evict_ids
            .iter()
            .filter_map(|id| entries.iter().find(|e| &e.id == id))
            .map(|e| e.token_count)
            .sum();

        entries.retain(|e| !evict_ids.contains(&e.id));
        (evict_ids.len(), freed_tokens)
    }
}
