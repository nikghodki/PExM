//! Memory scoring: combines recency, access frequency, and relevance signals.

use chrono::Utc;

use crate::memory::MemoryEntry;

/// Weights for the composite score.
const W_RECENCY: f32 = 0.40;
const W_FREQUENCY: f32 = 0.30;
const W_RELEVANCE: f32 = 0.30;

/// Half-life in seconds for the recency decay function.
const RECENCY_HALF_LIFE_SECS: f64 = 3600.0 * 24.0; // 24 h

pub struct MemoryScorer;

impl MemoryScorer {
    /// Compute a composite score in [0, 1] for a memory entry.
    ///
    /// - `relevance`: caller-supplied semantic relevance (e.g. cosine sim to query)
    /// - `access_count`: number of times the entry has been read
    pub fn score(entry: &MemoryEntry, relevance: f32, access_count: u32) -> f32 {
        let recency = Self::recency_score(entry);
        let frequency = Self::frequency_score(access_count);
        let composite =
            W_RECENCY * recency + W_FREQUENCY * frequency + W_RELEVANCE * relevance.clamp(0.0, 1.0);
        composite.clamp(0.0, 1.0)
    }

    /// Exponential decay based on time since last access.
    fn recency_score(entry: &MemoryEntry) -> f32 {
        let age_secs = (Utc::now() - entry.accessed_at).num_seconds().max(0) as f64;
        (-(age_secs / RECENCY_HALF_LIFE_SECS) * std::f64::consts::LN_2).exp() as f32
    }

    /// Logarithmic saturation on access count.
    fn frequency_score(count: u32) -> f32 {
        if count == 0 {
            return 0.0;
        }
        (1.0 + count as f32).ln() / (1.0 + 100_f32).ln()
    }

    /// Decide if a memory entry should be promoted to a higher tier.
    pub fn should_promote(score: f32, tier_threshold: f32) -> bool {
        score >= tier_threshold
    }

    /// Decide if a memory entry should be demoted to a lower tier.
    pub fn should_demote(score: f32, tier_floor: f32) -> bool {
        score < tier_floor
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::memory::{MemoryEntry, MemoryTier};
    use uuid::Uuid;

    #[test]
    fn score_is_in_range() {
        let entry = MemoryEntry::new(Uuid::new_v4(), "test", MemoryTier::L2Task);
        let score = MemoryScorer::score(&entry, 0.8, 5);
        assert!((0.0..=1.0).contains(&score));
    }
}

#[cfg(test)]
mod scoring_extra_tests {
    use super::*;
    use crate::memory::{MemoryEntry, MemoryTier};
    use uuid::Uuid;

    #[test]
    fn fresh_entry_has_high_recency() {
        let e = MemoryEntry::new(Uuid::new_v4(), "fresh", MemoryTier::L1Session);
        let s = MemoryScorer::score(&e, 1.0, 0);
        assert!(
            s > 0.35,
            "expected recency to push score above 0.35, got {s}"
        );
    }

    #[test]
    fn promote_threshold() {
        assert!(MemoryScorer::should_promote(0.8, 0.7));
        assert!(!MemoryScorer::should_promote(0.5, 0.7));
    }

    #[test]
    fn demote_threshold() {
        assert!(MemoryScorer::should_demote(0.1, 0.3));
        assert!(!MemoryScorer::should_demote(0.5, 0.3));
    }
}
