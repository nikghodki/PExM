//! In-process broadcast channel pub/sub.
//! Production: replace broadcast channel with Kafka producer/consumer.

use anyhow::Result;
use tokio::sync::broadcast;
use tracing::{debug, warn};

use crate::events::{MemoryEvent, MemoryEventKind};

const CHANNEL_CAP: usize = 1024;

/// Distributed memory bus backed by a tokio broadcast channel.
#[derive(Clone)]
pub struct MemoryBus {
    tx: broadcast::Sender<MemoryEvent>,
}

impl MemoryBus {
    pub fn new() -> Self {
        let (tx, _) = broadcast::channel(CHANNEL_CAP);
        Self { tx }
    }

    /// Publish a memory event to all subscribers.
    pub fn publish(&self, event: MemoryEvent) -> Result<()> {
        debug!(event_id = %event.event_id, kind = ?event.kind, "publishing memory event");
        self.tx
            .send(event)
            .map_err(|e| anyhow::anyhow!("bus send failed: {e}"))?;
        Ok(())
    }

    /// Subscribe to all events, optionally filtered by kind.
    pub fn subscribe(&self) -> broadcast::Receiver<MemoryEvent> {
        self.tx.subscribe()
    }

    /// Subscribe and filter to specific event kinds.
    pub async fn subscribe_filtered(
        &self,
        kinds: Vec<MemoryEventKind>,
        mut handler: impl FnMut(MemoryEvent) + Send + 'static,
    ) {
        let mut rx = self.tx.subscribe();
        tokio::spawn(async move {
            loop {
                match rx.recv().await {
                    Ok(event) if kinds.contains(&event.kind) => handler(event),
                    Ok(_) => {} // filtered out
                    Err(broadcast::error::RecvError::Lagged(n)) => {
                        warn!("bus subscriber lagged by {n} messages");
                    }
                    Err(broadcast::error::RecvError::Closed) => break,
                }
            }
        });
    }

    pub fn subscriber_count(&self) -> usize {
        self.tx.receiver_count()
    }
}

impl Default for MemoryBus {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::events::{MemoryEvent, MemoryEventKind};
    use uuid::Uuid;

    #[tokio::test]
    async fn publish_and_receive_event() {
        let bus = MemoryBus::new();
        let mut rx = bus.subscribe();

        let ev = MemoryEvent::new(
            MemoryEventKind::MemoryCreated,
            Uuid::new_v4(),
            Uuid::new_v4(),
            "team",
        );
        let expected_id = ev.event_id;
        bus.publish(ev).unwrap();

        let received = rx.recv().await.unwrap();
        assert_eq!(received.event_id, expected_id);
        assert_eq!(received.kind, MemoryEventKind::MemoryCreated);
    }

    #[tokio::test]
    async fn subscriber_count_tracks_receivers() {
        let bus = MemoryBus::new();
        assert_eq!(bus.subscriber_count(), 0);
        let _rx1 = bus.subscribe();
        let _rx2 = bus.subscribe();
        assert_eq!(bus.subscriber_count(), 2);
    }
}
