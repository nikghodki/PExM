//! Last-Write-Wins (LWW) register CRDT.

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

/// A LWW register holds a value and a timestamp.
/// Merging two registers picks the one with the higher timestamp.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LwwRegister<T: Clone> {
    pub value: T,
    pub timestamp: DateTime<Utc>,
    pub node_id: String,
}

impl<T: Clone + PartialEq> LwwRegister<T> {
    pub fn new(value: T, node_id: impl Into<String>) -> Self {
        Self {
            value,
            timestamp: Utc::now(),
            node_id: node_id.into(),
        }
    }

    /// Update the register value with a new timestamp.
    pub fn set(&mut self, value: T) {
        self.value = value;
        self.timestamp = Utc::now();
    }

    /// Merge with another register, keeping the most recent.
    /// On timestamp ties, the lexicographically larger node_id wins (deterministic).
    pub fn merge(&mut self, other: &LwwRegister<T>) {
        if other.timestamp > self.timestamp
            || (other.timestamp == self.timestamp && other.node_id > self.node_id)
        {
            self.value = other.value.clone();
            self.timestamp = other.timestamp;
            self.node_id = other.node_id.clone();
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn merge_picks_newer_timestamp() {
        let mut a: LwwRegister<i32> = LwwRegister::new(1, "node-a");
        std::thread::sleep(std::time::Duration::from_millis(5));
        let b: LwwRegister<i32> = LwwRegister::new(2, "node-b");
        a.merge(&b);
        assert_eq!(a.value, 2);
    }

    #[test]
    fn merge_is_idempotent() {
        let mut a: LwwRegister<&str> = LwwRegister::new("hello", "node-a");
        let b = a.clone();
        a.merge(&b);
        assert_eq!(a.value, "hello");
    }
}
