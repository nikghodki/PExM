//! ContextOS Policy Engine
//!
//! Role-Based Access Control (RBAC) and append-only audit logging.

pub mod audit;
pub mod rbac;

pub use audit::AuditLog;
pub use rbac::{Action, Effect, PolicyEngine, PolicyRule, Principal, Role};
