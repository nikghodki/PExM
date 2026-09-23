//! Observed-Remove Set (OR-Set) CRDT.
//!
//! Elements are tagged with unique tokens on add. Removal only removes
//! observed tokens, so concurrent add/remove is add-biased.

use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};
use uuid::Uuid;

/// OR-Set: each element carries a set of unique add-tokens.
/// To remove an element, all currently observed tokens are tombstoned.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OrSet<T: Clone + Eq + std::hash::Hash> {
    /// element → set of add-tokens
    entries: HashMap<T, HashSet<Uuid>>,
    /// tombstoned tokens
    tombstones: HashSet<Uuid>,
}

impl<T: Clone + Eq + std::hash::Hash> OrSet<T> {
    pub fn new() -> Self {
        Self {
            entries: HashMap::new(),
            tombstones: HashSet::new(),
        }
    }

    /// Add an element, returns the token assigned.
    pub fn add(&mut self, element: T) -> Uuid {
        let token = Uuid::new_v4();
        self.entries.entry(element).or_default().insert(token);
        token
    }

    /// Remove an element by tombstoning all observed tokens.
    pub fn remove(&mut self, element: &T) {
        if let Some(tokens) = self.entries.get(element) {
            self.tombstones.extend(tokens.iter().copied());
        }
    }

    /// Check whether an element is currently in the set.
    pub fn contains(&self, element: &T) -> bool {
        match self.entries.get(element) {
            None => false,
            Some(tokens) => tokens.iter().any(|t| !self.tombstones.contains(t)),
        }
    }

    /// Merge two OR-Sets (union of entries and tombstones).
    pub fn merge(&mut self, other: &OrSet<T>) {
        for (elem, tokens) in &other.entries {
            self.entries.entry(elem.clone()).or_default().extend(tokens);
        }
        self.tombstones.extend(&other.tombstones);
    }

    /// Snapshot of all live elements.
    pub fn elements(&self) -> Vec<&T> {
        self.entries
            .iter()
            .filter(|(_elem, tokens)| tokens.iter().any(|t| !self.tombstones.contains(t)))
            .map(|(elem, _)| elem)
            .collect()
    }
}

impl<T: Clone + Eq + std::hash::Hash> Default for OrSet<T> {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn add_and_contains() {
        let mut s: OrSet<String> = OrSet::new();
        s.add("alpha".to_string());
        assert!(s.contains(&"alpha".to_string()));
        assert!(!s.contains(&"beta".to_string()));
    }

    #[test]
    fn remove_observed_tokens() {
        let mut s: OrSet<&str> = OrSet::new();
        s.add("x");
        s.remove(&"x");
        assert!(!s.contains(&"x"));
    }

    #[test]
    fn merge_union() {
        let mut a: OrSet<u32> = OrSet::new();
        let mut b: OrSet<u32> = OrSet::new();
        a.add(1);
        b.add(2);
        a.merge(&b);
        assert!(a.contains(&1));
        assert!(a.contains(&2));
    }

    #[test]
    fn concurrent_add_remove_is_add_biased() {
        // After a.remove(x), if b concurrently adds x and we merge, x should remain
        let mut a: OrSet<&str> = OrSet::new();
        let mut b = a.clone();
        // a and b diverge
        a.add("x"); // a observes the add
        a.remove(&"x"); // a also removes it
        b.add("x"); // b concurrently adds x (new token)
        a.merge(&b); // merge: b's token is not tombstoned → x lives
        assert!(a.contains(&"x"));
    }
}
