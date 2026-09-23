//! Shared conversion helpers used by multiple gRPC service implementations.
//!
//! Centralises `Timestamp` ↔ `DateTime<Utc>` round-trips and UUID parsing so
//! that individual service modules stay lean.

use chrono::{DateTime, TimeZone, Utc};
use tonic::Status;
use uuid::Uuid;

// ─── Timestamp helpers ────────────────────────────────────────────────────────

/// Convert a `DateTime<Utc>` to a `prost_types::Timestamp`.
pub fn ts_to_proto(dt: DateTime<Utc>) -> prost_types::Timestamp {
    prost_types::Timestamp {
        seconds: dt.timestamp(),
        nanos: dt.timestamp_subsec_nanos() as i32,
    }
}

/// Convert an `Option<DateTime<Utc>>` to an `Option<prost_types::Timestamp>`.
pub fn ts_opt_to_proto(dt: Option<DateTime<Utc>>) -> Option<prost_types::Timestamp> {
    dt.map(ts_to_proto)
}

/// Convert a `prost_types::Timestamp` back to a `DateTime<Utc>`.
/// Returns `Utc::now()` as a fallback if the timestamp is out of range.
#[allow(dead_code)]
pub fn ts_from_proto(ts: prost_types::Timestamp) -> DateTime<Utc> {
    Utc.timestamp_opt(ts.seconds, ts.nanos as u32)
        .single()
        .unwrap_or_else(Utc::now)
}

// ─── UUID helper ──────────────────────────────────────────────────────────────

/// Parse a UUID string, mapping parse errors to `Status::invalid_argument`.
pub fn uuid_parse(s: &str) -> Result<Uuid, Status> {
    Uuid::parse_str(s).map_err(|e| Status::invalid_argument(format!("invalid UUID '{}': {}", s, e)))
}
