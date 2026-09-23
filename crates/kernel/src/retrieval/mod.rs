//! Retrieval orchestration: fan-out across tiers, merge, and rerank.

use anyhow::Result;
use uuid::Uuid;

use crate::memory::{MemoryEntry, MemoryKernel, MemoryTier};
use crate::scoring::MemoryScorer;

pub struct RetrievalQuery {
    pub agent_id: Uuid,
    pub text: String,
    pub embedding: Vec<f32>,
    pub top_k: usize,
    pub tiers: Vec<MemoryTier>,
}

pub struct RetrievalOrchestrator<'a> {
    kernel: &'a MemoryKernel,
}

impl<'a> RetrievalOrchestrator<'a> {
    pub fn new(kernel: &'a MemoryKernel) -> Self {
        Self { kernel }
    }

    /// Execute a retrieval query across the requested tiers, rerank by score.
    pub fn retrieve(&self, query: &RetrievalQuery) -> Result<Vec<MemoryEntry>> {
        let mut candidates: Vec<MemoryEntry> = Vec::new();

        // L1: linear scan (small set)
        if query.tiers.contains(&MemoryTier::L1Session) {
            // L1 doesn't expose a bulk search yet; future: ANN index
        }

        // L3: embedding similarity search
        if query.tiers.contains(&MemoryTier::L3Semantic) {
            let hits = self.kernel.l3.search(&query.embedding, query.top_k * 2)?;
            candidates.extend(hits);
        }

        // L2 & L4: full scan (suitable for smaller corpora; production uses indexing)
        if query.tiers.contains(&MemoryTier::L2Task) {
            let all = self.kernel.l2.scan_all()?;
            candidates.extend(all.into_iter().filter(|e| !e.is_expired()));
        }

        // Deduplicate by ID
        let mut seen = std::collections::HashSet::new();
        candidates.retain(|e| seen.insert(e.id));

        // Score and rank
        let mut scored: Vec<(f32, MemoryEntry)> = candidates
            .into_iter()
            .map(|e| {
                let sim = cosine_sim(&e.embedding, &query.embedding);
                let s = MemoryScorer::score(&e, sim, 0);
                (s, e)
            })
            .collect();
        scored.sort_by(|a, b| b.0.partial_cmp(&a.0).unwrap());

        Ok(scored
            .into_iter()
            .take(query.top_k)
            .map(|(_, e)| e)
            .collect())
    }
}

fn cosine_sim(a: &[f32], b: &[f32]) -> f32 {
    if a.len() != b.len() || a.is_empty() {
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
