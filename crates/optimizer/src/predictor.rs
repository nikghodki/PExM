//! Access pattern predictor for memory promotion scheduling.

use std::collections::HashMap;
use uuid::Uuid;

/// Tracks access counts per memory ID and suggests promotion targets.
pub struct AccessPredictor {
    access_counts: HashMap<Uuid, u32>,
    /// Threshold: memories accessed more than this many times are promotion candidates.
    promotion_threshold: u32,
}

#[derive(Debug, Clone)]
pub struct PromotionSuggestion {
    pub memory_id: Uuid,
    pub reason: String,
    pub target_tier: String,
    pub confidence: f32,
}

impl AccessPredictor {
    pub fn new(promotion_threshold: u32) -> Self {
        Self {
            access_counts: HashMap::new(),
            promotion_threshold,
        }
    }

    /// Record an access event for a memory.
    pub fn record_access(&mut self, memory_id: Uuid) {
        *self.access_counts.entry(memory_id).or_insert(0) += 1;
    }

    /// Generate promotion suggestions based on access frequency.
    pub fn suggestions(&self, limit: usize) -> Vec<PromotionSuggestion> {
        let mut candidates: Vec<_> = self
            .access_counts
            .iter()
            .filter(|(_, &count)| count >= self.promotion_threshold)
            .map(|(&id, &count)| {
                let confidence = (count as f32 / (self.promotion_threshold * 5) as f32).min(1.0);
                PromotionSuggestion {
                    memory_id: id,
                    reason: format!(
                        "accessed {count} times (threshold: {})",
                        self.promotion_threshold
                    ),
                    target_tier: "L2Task".to_owned(),
                    confidence,
                }
            })
            .collect();

        candidates.sort_by(|a, b| b.confidence.partial_cmp(&a.confidence).unwrap());
        candidates.truncate(limit);
        candidates
    }

    pub fn reset(&mut self, memory_id: &Uuid) {
        self.access_counts.remove(memory_id);
    }
}

impl Default for AccessPredictor {
    fn default() -> Self {
        Self::new(10)
    }
}
