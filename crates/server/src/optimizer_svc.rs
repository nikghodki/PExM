//! Full gRPC implementation of OptimizerService (Phase 3).
//!
//! - GetPromotionSuggestions: access-pattern based promotion recommendations
//! - TriggerCompression: zstd / summary compression of a memory entry

use std::sync::Arc;

use tokio::sync::Mutex;
use tonic::{Request, Response, Status};
use uuid::Uuid;

use contextos_kernel::MemoryKernel;
use contextos_optimizer::{compressor::CompressionStrategy, AccessPredictor, MemoryCompressor};

use crate::conv::uuid_parse;

pub mod proto {
    tonic::include_proto!("contextos.optimizer.v1");
}

use proto::optimizer_service_server::OptimizerService;
use proto::{
    CompressionResult as ProtoCompressionResult, GetPromotionSuggestionsRequest,
    GetPromotionSuggestionsResponse, PromotionSuggestion as ProtoSuggestion,
    TriggerCompressionRequest, TriggerCompressionResponse,
};

// ─── Service struct ───────────────────────────────────────────────────────────

pub struct OptimizerServiceImpl {
    pub(crate) kernel: Arc<MemoryKernel>,
    pub(crate) predictor: Arc<Mutex<AccessPredictor>>,
}

impl OptimizerServiceImpl {
    pub fn new(kernel: Arc<MemoryKernel>) -> Self {
        Self {
            kernel,
            predictor: Arc::new(Mutex::new(AccessPredictor::new(10))),
        }
    }

    /// Record an access event — called internally when memories are retrieved.
    #[allow(dead_code)]
    pub async fn record_access(&self, memory_id: Uuid) {
        self.predictor.lock().await.record_access(memory_id);
    }
}

// ─── tonic trait implementation ───────────────────────────────────────────────

#[tonic::async_trait]
impl OptimizerService for OptimizerServiceImpl {
    // ------------------------------------------------------------------
    // GetPromotionSuggestions
    // ------------------------------------------------------------------
    async fn get_promotion_suggestions(
        &self,
        request: Request<GetPromotionSuggestionsRequest>,
    ) -> Result<Response<GetPromotionSuggestionsResponse>, Status> {
        let req = request.into_inner();
        let limit = if req.limit <= 0 {
            20
        } else {
            req.limit as usize
        };

        let predictor = self.predictor.lock().await;
        let suggestions = predictor.suggestions(limit);

        let proto_suggestions: Vec<ProtoSuggestion> = suggestions
            .into_iter()
            .map(|s| ProtoSuggestion {
                memory_id: s.memory_id.to_string(),
                reason: s.reason,
                target_tier: s.target_tier,
                confidence: s.confidence,
            })
            .collect();

        Ok(Response::new(GetPromotionSuggestionsResponse {
            suggestions: proto_suggestions,
        }))
    }

    // ------------------------------------------------------------------
    // TriggerCompression
    // ------------------------------------------------------------------
    async fn trigger_compression(
        &self,
        request: Request<TriggerCompressionRequest>,
    ) -> Result<Response<TriggerCompressionResponse>, Status> {
        let req = request.into_inner();
        let memory_id = uuid_parse(&req.memory_id)?;

        // Retrieve the memory entry from the kernel.
        let entry = self
            .kernel
            .get(&memory_id)
            .ok_or_else(|| Status::not_found(format!("memory '{}' not found", memory_id)))?;

        let strategy = match req.strategy.as_str() {
            "delta" => CompressionStrategy::Delta,
            "summary" => CompressionStrategy::Summary,
            "zstd" => CompressionStrategy::Zstd,
            _ => CompressionStrategy::Auto,
        };

        let result = MemoryCompressor::compress(&entry.content, strategy)
            .map_err(|e| Status::internal(e.to_string()))?;

        Ok(Response::new(TriggerCompressionResponse {
            result: Some(ProtoCompressionResult {
                memory_id: memory_id.to_string(),
                compressed: true,
                before_tokens: (result.before_bytes / 4) as i32,
                after_tokens: (result.after_bytes / 4) as i32,
                summary: result.summary.unwrap_or_default(),
            }),
        }))
    }
}
