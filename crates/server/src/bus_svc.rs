//! Full gRPC implementation of MemoryBusService (Phase 2).
//!
//! - PublishEvent: converts proto event → domain event, publishes to bus
//! - Subscribe: server-streaming; filters by event_kinds and scope_filter

use tokio_stream::wrappers::BroadcastStream;
use tokio_stream::StreamExt as _;
use tonic::{Request, Response, Status};

use contextos_bus::{
    events::{MemoryEvent, MemoryEventKind},
    MemoryBus,
};

use crate::conv::uuid_parse;

pub mod proto {
    tonic::include_proto!("contextos.bus.v1");
}

use proto::memory_bus_service_server::MemoryBusService;
use proto::{
    MemoryEvent as ProtoEvent, PublishEventRequest, PublishEventResponse, SubscribeRequest,
};

// ─── Service struct ───────────────────────────────────────────────────────────

pub struct BusServiceImpl {
    pub(crate) bus: MemoryBus,
}

impl BusServiceImpl {
    pub fn new(bus: MemoryBus) -> Self {
        Self { bus }
    }
}

// ─── tonic trait implementation ───────────────────────────────────────────────

#[tonic::async_trait]
impl MemoryBusService for BusServiceImpl {
    // ------------------------------------------------------------------
    // PublishEvent
    // ------------------------------------------------------------------
    async fn publish_event(
        &self,
        request: Request<PublishEventRequest>,
    ) -> Result<Response<PublishEventResponse>, Status> {
        let req = request.into_inner();
        let proto = req
            .event
            .ok_or_else(|| Status::invalid_argument("missing event"))?;

        let memory_id = uuid_parse(&proto.memory_id)?;
        let agent_id = uuid_parse(&proto.agent_id)?;
        let kind = proto_kind_to_kernel(proto.kind);

        let mut event = MemoryEvent::new(kind, memory_id, agent_id, proto.scope.clone());
        event.payload = proto.payload;

        let event_id = event.event_id.to_string();

        self.bus
            .publish(event)
            .map_err(|e| Status::internal(e.to_string()))?;

        Ok(Response::new(PublishEventResponse { ok: true, event_id }))
    }

    // ------------------------------------------------------------------
    // Subscribe  (server-streaming)
    // ------------------------------------------------------------------
    type SubscribeStream =
        std::pin::Pin<Box<dyn futures_core::Stream<Item = Result<ProtoEvent, Status>> + Send>>;

    async fn subscribe(
        &self,
        request: Request<SubscribeRequest>,
    ) -> Result<Response<Self::SubscribeStream>, Status> {
        let req = request.into_inner();
        let filter_kinds: Vec<MemoryEventKind> = req
            .event_kinds
            .iter()
            .map(|&k| proto_kind_to_kernel(k))
            .collect();
        let scope_filter = req.scope_filter.clone();

        let rx = self.bus.subscribe();

        let stream = BroadcastStream::new(rx).filter_map(move |r| {
            let fk = filter_kinds.clone();
            let scope = scope_filter.clone();
            match r {
                Ok(event) => {
                    // Apply kind filter (empty = accept all).
                    if !fk.is_empty() && !fk.contains(&event.kind) {
                        return None;
                    }
                    // Apply scope filter.
                    if !scope.is_empty() && event.scope != scope {
                        return None;
                    }
                    Some(Ok(domain_event_to_proto(event)))
                }
                Err(_) => None, // lagged subscriber — skip
            }
        });

        Ok(Response::new(Box::pin(stream)))
    }
}

// ─── Conversion helpers ───────────────────────────────────────────────────────

fn domain_event_to_proto(e: MemoryEvent) -> ProtoEvent {
    ProtoEvent {
        event_id: e.event_id.to_string(),
        kind: kernel_kind_to_proto(&e.kind),
        memory_id: e.memory_id.to_string(),
        agent_id: e.agent_id.to_string(),
        scope: e.scope,
        payload: e.payload,
        occurred_at: Some(crate::conv::ts_to_proto(e.occurred_at)),
    }
}

fn proto_kind_to_kernel(v: i32) -> MemoryEventKind {
    match v {
        1 => MemoryEventKind::MemoryCreated,
        2 => MemoryEventKind::MemoryUpdated,
        3 => MemoryEventKind::MemoryPromoted,
        4 => MemoryEventKind::MemoryArchived,
        5 => MemoryEventKind::ScopeShared,
        6 => MemoryEventKind::AgentSubscribed,
        7 => MemoryEventKind::AgentUnsubscribed,
        _ => MemoryEventKind::MemoryCreated,
    }
}

fn kernel_kind_to_proto(k: &MemoryEventKind) -> i32 {
    match k {
        MemoryEventKind::MemoryCreated => 1,
        MemoryEventKind::MemoryUpdated => 2,
        MemoryEventKind::MemoryPromoted => 3,
        MemoryEventKind::MemoryArchived => 4,
        MemoryEventKind::ScopeShared => 5,
        MemoryEventKind::AgentSubscribed => 6,
        MemoryEventKind::AgentUnsubscribed => 7,
    }
}
