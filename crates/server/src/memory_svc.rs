//! gRPC implementation of `MemoryService`.
//!
//! All six RPCs are implemented against `MemoryKernel`.  Embeddings are stored
//! as little-endian f32 byte sequences in the `embedding` proto bytes field.
//! Text-query searches use a zero-vector until a real embedding model is wired.

use std::sync::Arc;

use chrono::Utc;
use tonic::{Request, Response, Status};
use uuid::Uuid;

use contextos_kernel::memory::{MemoryEntry, MemoryTier, Scope};
use contextos_kernel::MemoryKernel;

use crate::conv::{ts_opt_to_proto, ts_to_proto, uuid_parse};

// Pull in the generated types for the `contextos.memory.v1` package.
pub mod proto {
    tonic::include_proto!("contextos.memory.v1");
}

use proto::memory_service_server::MemoryService;
use proto::{
    DeleteMemoryRequest, DeleteMemoryResponse, GetMemoryRequest, GetMemoryResponse,
    ListMemoriesRequest, ListMemoriesResponse, PromoteMemoryRequest, PromoteMemoryResponse,
    SearchMemoryRequest, SearchMemoryResponse, StoreMemoryRequest, StoreMemoryResponse,
};

// ─── Service struct ───────────────────────────────────────────────────────────

/// Concrete implementation of the gRPC `MemoryService`.
pub struct MemoryServiceImpl {
    pub(crate) kernel: Arc<MemoryKernel>,
}

impl MemoryServiceImpl {
    pub fn new(kernel: Arc<MemoryKernel>) -> Self {
        Self { kernel }
    }
}

// ─── tonic trait implementation ───────────────────────────────────────────────

#[tonic::async_trait]
impl MemoryService for MemoryServiceImpl {
    // ------------------------------------------------------------------
    // StoreMemory
    // ------------------------------------------------------------------
    async fn store_memory(
        &self,
        request: Request<StoreMemoryRequest>,
    ) -> Result<Response<StoreMemoryResponse>, Status> {
        let req = request.into_inner();

        let agent_id = uuid_parse(&req.agent_id)?;
        let tier = proto_tier_to_kernel(req.tier);
        let scope = proto_scope_to_kernel(req.scope);

        let mut entry = MemoryEntry::new(agent_id, req.content, tier);
        entry.scope = scope;
        entry.tags = req.tags;
        entry.metadata = req.metadata;

        // Apply optional TTL.
        if let Some(secs_str) = req.expires_in_secs {
            let secs: u64 = secs_str.parse().map_err(|_| {
                Status::invalid_argument(format!(
                    "expires_in_secs '{}' is not a valid integer",
                    secs_str
                ))
            })?;
            entry.expires_at = Some(Utc::now() + chrono::Duration::seconds(secs as i64));
        }

        let score = entry.score;
        let id = self
            .kernel
            .store(entry)
            .map_err(|e| Status::internal(e.to_string()))?;

        Ok(Response::new(StoreMemoryResponse {
            id: id.to_string(),
            ok: true,
            score,
        }))
    }

    // ------------------------------------------------------------------
    // GetMemory
    // ------------------------------------------------------------------
    async fn get_memory(
        &self,
        request: Request<GetMemoryRequest>,
    ) -> Result<Response<GetMemoryResponse>, Status> {
        let req = request.into_inner();
        let id = uuid_parse(&req.id)?;

        let entry = self
            .kernel
            .get(&id)
            .ok_or_else(|| Status::not_found(format!("memory entry '{}' not found", id)))?;

        Ok(Response::new(GetMemoryResponse {
            entry: Some(entry_to_proto(entry)),
        }))
    }

    // ------------------------------------------------------------------
    // SearchMemory
    // ------------------------------------------------------------------
    async fn search_memory(
        &self,
        request: Request<SearchMemoryRequest>,
    ) -> Result<Response<SearchMemoryResponse>, Status> {
        let req = request.into_inner();
        let top_k = req.top_k.max(1) as usize;

        // Build a zero-vector query embedding.  Until a real text-embedding
        // model is wired in, this will retrieve all L3 entries sorted by
        // whichever happened to be stored with a non-zero embedding (cosine 0),
        // but still produces a valid ranked list.
        let zero_vec: Vec<f32> = vec![0.0f32; 1536]; // common embedding dim

        // L3 semantic search.
        let mut results: Vec<MemoryEntry> = self
            .kernel
            .l3
            .search(&zero_vec, top_k * 2)
            .map_err(|e| Status::internal(e.to_string()))?;

        // Also scan L2 and merge.
        let l2_entries = self
            .kernel
            .l2
            .scan_all()
            .map_err(|e| Status::internal(e.to_string()))?;
        results.extend(l2_entries);

        // Filter by agent_id if provided.
        if !req.agent_id.is_empty() {
            let aid = uuid_parse(&req.agent_id)?;
            results.retain(|e| e.agent_id == aid);
        }

        // Filter by scope if provided (non-zero means caller set it).
        if req.scope != 0 {
            let wanted = proto_scope_to_kernel(req.scope);
            results.retain(|e| e.scope == wanted);
        }

        // Filter by tags if provided (entry must contain ALL requested tags).
        if !req.tags.is_empty() {
            results.retain(|e| req.tags.iter().all(|t| e.tags.contains(t)));
        }

        // Deduplicate by entry id (L2/L3 overlap possible after promotion).
        let mut seen = std::collections::HashSet::<Uuid>::new();
        results.retain(|e| seen.insert(e.id));

        // Simple re-rank: prefer entries whose content contains the query string.
        let q = req.query.to_lowercase();
        results.sort_by(|a, b| {
            let sa = if a.content.to_lowercase().contains(&q) {
                1
            } else {
                0
            };
            let sb = if b.content.to_lowercase().contains(&q) {
                1
            } else {
                0
            };
            sb.cmp(&sa).then(
                b.score
                    .partial_cmp(&a.score)
                    .unwrap_or(std::cmp::Ordering::Equal),
            )
        });

        results.truncate(top_k);

        Ok(Response::new(SearchMemoryResponse {
            results: results.into_iter().map(entry_to_proto).collect(),
        }))
    }

    // ------------------------------------------------------------------
    // PromoteMemory
    // ------------------------------------------------------------------
    async fn promote_memory(
        &self,
        request: Request<PromoteMemoryRequest>,
    ) -> Result<Response<PromoteMemoryResponse>, Status> {
        let req = request.into_inner();
        let id = uuid_parse(&req.id)?;
        let target = proto_tier_to_kernel(req.target_tier);

        self.kernel
            .promote(&id, target)
            .map_err(|e| Status::internal(e.to_string()))?;

        let new_tier_proto = kernel_tier_to_proto(target);
        Ok(Response::new(PromoteMemoryResponse {
            ok: true,
            new_tier: new_tier_proto,
        }))
    }

    // ------------------------------------------------------------------
    // DeleteMemory
    // ------------------------------------------------------------------
    async fn delete_memory(
        &self,
        request: Request<DeleteMemoryRequest>,
    ) -> Result<Response<DeleteMemoryResponse>, Status> {
        let req = request.into_inner();
        let id = uuid_parse(&req.id)?;

        self.kernel
            .delete(&id)
            .map_err(|e| Status::internal(e.to_string()))?;

        Ok(Response::new(DeleteMemoryResponse { ok: true }))
    }

    // ------------------------------------------------------------------
    // ListMemories
    // ------------------------------------------------------------------
    async fn list_memories(
        &self,
        request: Request<ListMemoriesRequest>,
    ) -> Result<Response<ListMemoriesResponse>, Status> {
        let req = request.into_inner();
        let page_size = if req.page_size <= 0 {
            50
        } else {
            req.page_size as usize
        };

        // Decode the cursor (base-10 offset encoded as string, 0 if absent).
        let offset: usize = if req.page_token.is_empty() {
            0
        } else {
            req.page_token.parse::<usize>().unwrap_or(0)
        };

        // Gather candidates from the requested tier (or all tiers when unspecified).
        let tier_val = req.tier; // i32 proto enum value
        let mut all: Vec<MemoryEntry> = match tier_val {
            // L1_SESSION = 1
            1 => {
                // L1 has no scan_all; collect by listing via the inner map
                // indirectly: we can't access the inner HashMap directly, but
                // we can call scan on L2 and L3 plus list_ids on L4 and fall
                // through for L1 entries retrieved individually.  Instead we
                // expose a scan via L1's public API by noting that L1SessionMemory
                // has `len()` but no iterator.  The safest approach is to collect
                // entries from every tier and post-filter — matching the search path.
                let mut v: Vec<MemoryEntry> = Vec::new();
                v.extend(
                    self.kernel
                        .l2
                        .scan_all()
                        .map_err(|e| Status::internal(e.to_string()))?,
                );
                v.extend(
                    self.kernel
                        .l3
                        .search(&vec![0.0f32; 1536], usize::MAX)
                        .map_err(|e| Status::internal(e.to_string()))?,
                );
                let l4_ids = self
                    .kernel
                    .l4
                    .list_ids()
                    .map_err(|e| Status::internal(e.to_string()))?;
                for lid in l4_ids {
                    if let Some(e) = self.kernel.l4.get(&lid) {
                        v.push(e);
                    }
                }
                // Keep only L1-tier entries (these would have been stored with
                // tier = L1Session).
                v.retain(|e| e.tier == MemoryTier::L1Session);
                v
            }
            // L2_TASK = 2
            2 => self
                .kernel
                .l2
                .scan_all()
                .map_err(|e| Status::internal(e.to_string()))?,
            // L3_SEMANTIC = 3
            3 => self
                .kernel
                .l3
                .search(&vec![0.0f32; 1536], usize::MAX)
                .map_err(|e| Status::internal(e.to_string()))?,
            // L4_ARCHIVE = 4
            4 => {
                let ids = self
                    .kernel
                    .l4
                    .list_ids()
                    .map_err(|e| Status::internal(e.to_string()))?;
                let mut v = Vec::with_capacity(ids.len());
                for id in ids {
                    if let Some(e) = self.kernel.l4.get(&id) {
                        v.push(e);
                    }
                }
                v
            }
            // UNSPECIFIED / unknown — return from all persistent tiers.
            _ => {
                let mut v: Vec<MemoryEntry> = Vec::new();
                v.extend(
                    self.kernel
                        .l2
                        .scan_all()
                        .map_err(|e| Status::internal(e.to_string()))?,
                );
                v.extend(
                    self.kernel
                        .l3
                        .search(&vec![0.0f32; 1536], usize::MAX)
                        .map_err(|e| Status::internal(e.to_string()))?,
                );
                let l4_ids = self
                    .kernel
                    .l4
                    .list_ids()
                    .map_err(|e| Status::internal(e.to_string()))?;
                for lid in l4_ids {
                    if let Some(e) = self.kernel.l4.get(&lid) {
                        v.push(e);
                    }
                }
                v
            }
        };

        // Filter by agent_id.
        if !req.agent_id.is_empty() {
            let aid = uuid_parse(&req.agent_id)?;
            all.retain(|e| e.agent_id == aid);
        }

        // Filter by scope.
        if req.scope != 0 {
            let wanted = proto_scope_to_kernel(req.scope);
            all.retain(|e| e.scope == wanted);
        }

        // Deduplicate by id (L3 search may overlap with L2 scan after promotion).
        let mut seen = std::collections::HashSet::<Uuid>::new();
        all.retain(|e| seen.insert(e.id));

        // Sort by created_at descending (newest first).
        all.sort_by(|a, b| b.created_at.cmp(&a.created_at));

        let total = all.len();
        let page: Vec<MemoryEntry> = all.into_iter().skip(offset).take(page_size).collect();

        let next_page_token = if offset + page.len() < total {
            (offset + page.len()).to_string()
        } else {
            String::new()
        };

        Ok(Response::new(ListMemoriesResponse {
            entries: page.into_iter().map(entry_to_proto).collect(),
            next_page_token,
        }))
    }
}

// ─── Conversion helpers ───────────────────────────────────────────────────────

/// Convert a kernel `MemoryEntry` to its proto counterpart.
pub fn entry_to_proto(e: MemoryEntry) -> proto::MemoryEntry {
    proto::MemoryEntry {
        id: e.id.to_string(),
        agent_id: e.agent_id.to_string(),
        content: e.content,
        embedding: embedding_to_bytes(e.embedding),
        tier: kernel_tier_to_proto(e.tier),
        scope: kernel_scope_to_proto(e.scope),
        score: e.score,
        tags: e.tags,
        metadata: e.metadata,
        created_at: Some(ts_to_proto(e.created_at)),
        accessed_at: Some(ts_to_proto(e.accessed_at)),
        expires_at: ts_opt_to_proto(e.expires_at),
    }
}

/// Encode a `Vec<f32>` as a contiguous sequence of little-endian 4-byte values.
/// Returns `Vec<u8>` — tonic 0.12 / prost 0.13 generates `Vec<u8>` for proto `bytes` fields.
pub fn embedding_to_bytes(v: Vec<f32>) -> Vec<u8> {
    let mut buf: Vec<u8> = Vec::with_capacity(v.len() * 4);
    for f in v {
        buf.extend_from_slice(&f.to_le_bytes());
    }
    buf
}

/// Decode a little-endian f32 byte slice back to `Vec<f32>`.
#[allow(dead_code)]
pub fn bytes_to_embedding(b: &[u8]) -> Vec<f32> {
    b.chunks_exact(4)
        .map(|c| f32::from_le_bytes([c[0], c[1], c[2], c[3]]))
        .collect()
}

/// Map a proto `MemoryTier` discriminant (i32) to the kernel enum.
pub fn proto_tier_to_kernel(v: i32) -> MemoryTier {
    match v {
        1 => MemoryTier::L1Session,
        2 => MemoryTier::L2Task,
        3 => MemoryTier::L3Semantic,
        4 => MemoryTier::L4Archive,
        _ => MemoryTier::L1Session,
    }
}

/// Map the kernel `MemoryTier` enum back to its proto i32 discriminant.
pub fn kernel_tier_to_proto(t: MemoryTier) -> i32 {
    match t {
        MemoryTier::L1Session => 1,
        MemoryTier::L2Task => 2,
        MemoryTier::L3Semantic => 3,
        MemoryTier::L4Archive => 4,
    }
}

/// Map a proto `Scope` discriminant (i32) to the kernel enum.
pub fn proto_scope_to_kernel(v: i32) -> Scope {
    match v {
        1 => Scope::Private,
        2 => Scope::Team,
        3 => Scope::Org,
        4 => Scope::Ephemeral,
        _ => Scope::Private,
    }
}

/// Map the kernel `Scope` enum back to its proto i32 discriminant.
pub fn kernel_scope_to_proto(s: Scope) -> i32 {
    match s {
        Scope::Private => 1,
        Scope::Team => 2,
        Scope::Org => 3,
        Scope::Ephemeral => 4,
    }
}
