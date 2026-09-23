//! Full gRPC implementation of PolicyService (Phase 2).
//!
//! - CheckPermission: glob-pattern RBAC rule evaluation
//! - CreateRole / AssignRole: role management
//! - RecordAuditEvent: append to audit log + broadcast to live subscribers
//! - ListAuditEvents: paginated audit query
//! - StreamAuditEvents: server-streaming live audit feed via tokio broadcast

use std::sync::Arc;

use chrono::{TimeZone, Utc};
use tokio::sync::broadcast;
use tokio_stream::wrappers::BroadcastStream;
use tokio_stream::StreamExt as _;
use tonic::{Request, Response, Status};
use uuid::Uuid;

use contextos_policy::{
    audit::AuditEvent,
    rbac::{Action, Effect, Principal, Role},
    AuditLog, PolicyEngine,
};

use crate::conv::{ts_from_proto, ts_to_proto, uuid_parse};

pub mod proto {
    tonic::include_proto!("contextos.policy.v1");
}

use proto::policy_service_server::PolicyService;
use proto::{
    AssignRoleRequest, AuditEvent as ProtoAuditEvent, CheckPermissionRequest,
    CheckPermissionResponse, CreateRoleRequest, CreateRoleResponse, ListAuditEventsRequest,
    ListAuditEventsResponse, StreamAuditRequest,
};

// ─── Service struct ───────────────────────────────────────────────────────────

pub struct PolicyServiceImpl {
    pub(crate) engine: PolicyEngine,
    pub(crate) audit: AuditLog,
    /// Broadcast channel for live audit streaming.
    tx: Arc<broadcast::Sender<AuditEvent>>,
}

impl PolicyServiceImpl {
    pub fn new(engine: PolicyEngine, audit: AuditLog) -> Self {
        let (tx, _) = broadcast::channel(512);
        Self {
            engine,
            audit,
            tx: Arc::new(tx),
        }
    }
}

// ─── tonic trait implementation ───────────────────────────────────────────────

#[tonic::async_trait]
impl PolicyService for PolicyServiceImpl {
    // ------------------------------------------------------------------
    // CheckPermission
    // ------------------------------------------------------------------
    async fn check_permission(
        &self,
        request: Request<CheckPermissionRequest>,
    ) -> Result<Response<CheckPermissionResponse>, Status> {
        let req = request.into_inner();
        let principal = uuid_parse(&req.principal_id)?;
        let action = proto_action_to_kernel(req.action);

        let (effect, rule_id) = self.engine.check(&principal, &req.resource, action);

        Ok(Response::new(CheckPermissionResponse {
            effect: kernel_effect_to_proto(effect),
            rule_id: rule_id.map(|r| r.to_string()).unwrap_or_default(),
            reason: String::new(),
        }))
    }

    // ------------------------------------------------------------------
    // CreateRole
    // ------------------------------------------------------------------
    async fn create_role(
        &self,
        request: Request<CreateRoleRequest>,
    ) -> Result<Response<CreateRoleResponse>, Status> {
        let req = request.into_inner();
        let role = req
            .role
            .ok_or_else(|| Status::invalid_argument("missing role"))?;
        let id = Uuid::new_v4();

        self.engine.add_role(Role {
            id,
            name: role.name,
            permissions: role.permissions,
        });

        Ok(Response::new(CreateRoleResponse {
            id: id.to_string(),
            success: true,
        }))
    }

    // ------------------------------------------------------------------
    // AssignRole
    // ------------------------------------------------------------------
    async fn assign_role(
        &self,
        request: Request<AssignRoleRequest>,
    ) -> Result<Response<()>, Status> {
        let req = request.into_inner();
        let principal_id = uuid_parse(&req.principal_id)?;
        let role_id = uuid_parse(&req.role_id)?;

        // Add or update the principal with the new role.
        // Upsert: add_principal overwrites any existing entry with the same id.
        self.engine.add_principal(Principal {
            id: principal_id,
            name: req.principal_id.clone(),
            role_ids: vec![role_id],
        });

        Ok(Response::new(()))
    }

    // ------------------------------------------------------------------
    // RecordAuditEvent
    // ------------------------------------------------------------------
    async fn record_audit_event(
        &self,
        request: Request<ProtoAuditEvent>,
    ) -> Result<Response<()>, Status> {
        let proto = request.into_inner();
        let principal_id = uuid_parse(&proto.principal_id)?;
        let action = proto_action_to_kernel(proto.action);
        let outcome = proto_effect_to_kernel(proto.outcome);

        let mut event = AuditEvent::new(principal_id, proto.resource, action, outcome);
        event.details = proto.details;
        event.ip_address = proto.ip_address;

        // Broadcast to live subscribers (ignore send error if no listeners).
        let _ = self.tx.send(event.clone());
        self.audit.record(event);

        Ok(Response::new(()))
    }

    // ------------------------------------------------------------------
    // ListAuditEvents
    // ------------------------------------------------------------------
    async fn list_audit_events(
        &self,
        request: Request<ListAuditEventsRequest>,
    ) -> Result<Response<ListAuditEventsResponse>, Status> {
        let req = request.into_inner();
        let principal_id = uuid_parse(&req.principal_id)?;
        let page_size = if req.page_size <= 0 {
            50
        } else {
            req.page_size as usize
        };

        let from = req
            .from
            .map(ts_from_proto)
            .unwrap_or_else(|| Utc.timestamp_opt(0, 0).single().unwrap_or_else(Utc::now));
        let to = req.to.map(ts_from_proto).unwrap_or_else(Utc::now);

        // Decode cursor (offset as string).
        let offset: usize = req.page_token.parse().unwrap_or(0);

        let events = self.audit.events_for_principal(&principal_id, from, to);
        let total = events.len();

        let page: Vec<AuditEvent> = events.into_iter().skip(offset).take(page_size).collect();

        let next_page_token = if offset + page.len() < total {
            (offset + page.len()).to_string()
        } else {
            String::new()
        };

        Ok(Response::new(ListAuditEventsResponse {
            events: page.into_iter().map(audit_event_to_proto).collect(),
            next_page_token,
        }))
    }

    // ------------------------------------------------------------------
    // StreamAuditEvents  (server-streaming)
    // ------------------------------------------------------------------
    type StreamAuditEventsStream =
        std::pin::Pin<Box<dyn futures_core::Stream<Item = Result<ProtoAuditEvent, Status>> + Send>>;

    async fn stream_audit_events(
        &self,
        request: Request<StreamAuditRequest>,
    ) -> Result<Response<Self::StreamAuditEventsStream>, Status> {
        let req = request.into_inner();
        let principal_id = if req.principal_id.is_empty() {
            None
        } else {
            Some(uuid_parse(&req.principal_id)?)
        };

        let rx = self.tx.subscribe();

        let stream = BroadcastStream::new(rx).filter_map(move |r| {
            let pid = principal_id;
            match r {
                Ok(event) => {
                    // Filter to principal if specified.
                    if let Some(p) = pid {
                        if event.principal_id != p {
                            return None;
                        }
                    }
                    Some(Ok(audit_event_to_proto(event)))
                }
                Err(_) => None, // lagged — skip
            }
        });

        Ok(Response::new(Box::pin(stream)))
    }
}

// ─── Conversion helpers ───────────────────────────────────────────────────────

fn audit_event_to_proto(e: AuditEvent) -> ProtoAuditEvent {
    ProtoAuditEvent {
        id: e.id.to_string(),
        principal_id: e.principal_id.to_string(),
        resource: e.resource,
        action: kernel_action_to_proto(e.action),
        outcome: kernel_effect_to_proto(e.outcome),
        details: e.details,
        ip_address: e.ip_address,
        occurred_at: Some(ts_to_proto(e.occurred_at)),
    }
}

fn proto_action_to_kernel(v: i32) -> Action {
    match v {
        1 => Action::Read,
        2 => Action::Write,
        3 => Action::Delete,
        4 => Action::Admin,
        _ => Action::Read,
    }
}

fn kernel_action_to_proto(a: Action) -> i32 {
    match a {
        Action::Read => 1,
        Action::Write => 2,
        Action::Delete => 3,
        Action::Admin => 4,
    }
}

fn proto_effect_to_kernel(v: i32) -> Effect {
    match v {
        1 => Effect::Allow,
        _ => Effect::Deny,
    }
}

fn kernel_effect_to_proto(e: Effect) -> i32 {
    match e {
        Effect::Allow => 1,
        Effect::Deny => 2,
    }
}
