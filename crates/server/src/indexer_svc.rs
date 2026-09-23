//! gRPC implementation of `IndexerService`.
//!
//! State:
//!   - `Arc<tokio::sync::Mutex<SymbolGraph>>`  — shared mutable symbol DAG.
//!   - `Arc<tokio::sync::Mutex<AstParser>>`    — tree-sitter parser (not `Send + Sync`).
//!   - `Arc<tokio::sync::Mutex<HashMap<String, GitTracker>>>` — per-repo git handles.
//!
//! `walkdir` is used for directory traversal during `IndexRepository`.
//! Add `walkdir = "2"` to `crates/server/Cargo.toml` under `[dependencies]`.

use std::collections::HashMap;
use std::sync::Arc;
use std::time::Instant;

use tonic::{Request, Response, Status};
use walkdir::WalkDir;

use contextos_indexer::git::tracker::{CommitDiff, FileDiff, FunctionDelta};
use contextos_indexer::symbols::SymbolKind;
use contextos_indexer::symbols::SymbolNode;
use contextos_indexer::{AstParser, GitTracker, SymbolGraph};

// Pull in generated types for the `contextos.indexer.v1` package.
pub mod proto {
    tonic::include_proto!("contextos.indexer.v1");
}

use proto::indexer_service_server::IndexerService;
use proto::{
    GetCommitDiffRequest, GetCommitDiffResponse, GetSymbolRequest, GetSymbolResponse,
    IndexRepositoryRequest, IndexRepositoryResponse, QueryFunctionDeltasRequest,
    QueryFunctionDeltasResponse, QuerySymbolsRequest, QuerySymbolsResponse,
};

// ─── Service struct ───────────────────────────────────────────────────────────

/// Concrete implementation of the gRPC `IndexerService`.
pub struct IndexerServiceImpl {
    pub(crate) graph: Arc<tokio::sync::Mutex<SymbolGraph>>,
    pub(crate) parser: Arc<tokio::sync::Mutex<AstParser>>,
    /// Maps `repo_id` → `GitTracker`.  Entries are created lazily on first use.
    pub(crate) trackers: Arc<tokio::sync::Mutex<HashMap<String, GitTracker>>>,
}

impl IndexerServiceImpl {
    pub fn new() -> Self {
        Self {
            graph: Arc::new(tokio::sync::Mutex::new(SymbolGraph::new())),
            parser: Arc::new(tokio::sync::Mutex::new(AstParser::new())),
            trackers: Arc::new(tokio::sync::Mutex::new(HashMap::new())),
        }
    }
}

impl Default for IndexerServiceImpl {
    fn default() -> Self {
        Self::new()
    }
}

// ─── tonic trait implementation ───────────────────────────────────────────────

#[tonic::async_trait]
impl IndexerService for IndexerServiceImpl {
    // ------------------------------------------------------------------
    // IndexRepository
    // ------------------------------------------------------------------
    async fn index_repository(
        &self,
        request: Request<IndexRepositoryRequest>,
    ) -> Result<Response<IndexRepositoryResponse>, Status> {
        let req = request.into_inner();
        let repo_id = req.repo_id.clone();
        let local_path = req.local_path.clone();
        let incremental = req.incremental;

        // Determine which languages to index.  Default to Rust + Python.
        let languages: Vec<String> = if req.languages.is_empty() {
            vec!["rust".to_owned(), "python".to_owned()]
        } else {
            req.languages
        };

        // Build extension → language map.
        let ext_to_lang: HashMap<&str, &str> = {
            let mut m = HashMap::new();
            for lang in &languages {
                match lang.as_str() {
                    "rust" => {
                        m.insert("rs", "rust");
                    }
                    "python" => {
                        m.insert("py", "python");
                    }
                    _ => {}
                }
            }
            m
        };

        // For incremental mode, record the time we started so that we can
        // compare against file mtime.  We do not persist a "last indexed at"
        // timestamp in this implementation — instead we consider files modified
        // in the last 24 hours as "recently changed" when incremental=true.
        // A production implementation would persist the last-indexed time.
        let incremental_cutoff: Option<std::time::SystemTime> = if incremental {
            Some(std::time::SystemTime::now() - std::time::Duration::from_secs(86_400))
        } else {
            None
        };

        let start = Instant::now();
        let mut symbols_added: i64 = 0;

        // Walk the directory tree.
        for entry in WalkDir::new(&local_path)
            .into_iter()
            .filter_map(|e| e.ok())
            .filter(|e| e.file_type().is_file())
        {
            let path = entry.path();

            // Determine language from file extension.
            let ext = path.extension().and_then(|e| e.to_str()).unwrap_or("");
            let lang = match ext_to_lang.get(ext) {
                Some(l) => *l,
                None => continue,
            };

            // For incremental indexing, skip files not recently modified.
            // `entry.metadata()` returns `walkdir::Result<Metadata>` and
            // `Metadata::modified()` returns `io::Result<SystemTime>`, so we
            // resolve them separately rather than chaining `and_then`.
            if let Some(cutoff) = incremental_cutoff {
                let mtime_result: Option<std::time::SystemTime> =
                    entry.metadata().ok().and_then(|m| m.modified().ok());
                match mtime_result {
                    Some(mtime) if mtime < cutoff => continue,
                    None => continue,
                    _ => {}
                }
            }

            // Read source.
            let source = match std::fs::read_to_string(path) {
                Ok(s) => s,
                Err(_) => continue,
            };

            let file_path_str = path.to_string_lossy().to_string();

            // Parse symbols — hold the parser lock only for the duration of parsing.
            let symbols: Vec<SymbolNode> = {
                let mut parser = self.parser.lock().await;
                parser
                    .parse(&repo_id, &file_path_str, lang, &source)
                    .unwrap_or_default()
            };

            // Add symbols to the graph.
            {
                let mut graph = self.graph.lock().await;
                for sym in symbols {
                    graph.add_symbol(sym);
                    symbols_added += 1;
                }
            }
        }

        let duration_ms = start.elapsed().as_millis() as i64;

        Ok(Response::new(IndexRepositoryResponse {
            ok: true,
            symbols_added,
            duration_ms,
        }))
    }

    // ------------------------------------------------------------------
    // GetSymbol
    // ------------------------------------------------------------------
    async fn get_symbol(
        &self,
        request: Request<GetSymbolRequest>,
    ) -> Result<Response<GetSymbolResponse>, Status> {
        let req = request.into_inner();
        let graph = self.graph.lock().await;

        let node = graph
            .get(&req.id)
            .ok_or_else(|| Status::not_found(format!("symbol '{}' not found", req.id)))?;

        Ok(Response::new(GetSymbolResponse {
            symbol: Some(symbol_to_proto(node.clone())),
        }))
    }

    // ------------------------------------------------------------------
    // QuerySymbols
    // ------------------------------------------------------------------
    async fn query_symbols(
        &self,
        request: Request<QuerySymbolsRequest>,
    ) -> Result<Response<QuerySymbolsResponse>, Status> {
        let req = request.into_inner();
        let top_k = if req.top_k <= 0 {
            20
        } else {
            req.top_k as usize
        };
        let query = req.query.to_lowercase();

        let graph = self.graph.lock().await;
        let all = graph.all_symbols();
        let want_kind: Option<SymbolKind> = if req.kind == 0 {
            None
        } else {
            Some(proto_kind_to_kernel(req.kind))
        };

        // Filter pass.
        let mut matches: Vec<(&SymbolNode, u32)> = all
            .into_iter()
            .filter(|s| {
                // repo_id filter
                if !req.repo_id.is_empty() && s.repo_id != req.repo_id {
                    return false;
                }
                // kind filter
                if let Some(k) = want_kind {
                    if s.kind != k {
                        return false;
                    }
                }
                // query substring match
                if !query.is_empty() {
                    let name_lower = s.name.to_lowercase();
                    let qname_lower = s.qualified_name.to_lowercase();
                    if !name_lower.contains(&query) && !qname_lower.contains(&query) {
                        return false;
                    }
                }
                true
            })
            .map(|s| {
                // Score: exact name match > name prefix match > substring match.
                let name_lower = s.name.to_lowercase();
                let score: u32 = if name_lower == query {
                    3
                } else if name_lower.starts_with(&query) {
                    2
                } else {
                    1
                };
                (s, score)
            })
            .collect();

        // Sort descending by match quality.
        matches.sort_by(|a, b| b.1.cmp(&a.1));
        matches.truncate(top_k);

        Ok(Response::new(QuerySymbolsResponse {
            results: matches
                .into_iter()
                .map(|(s, _)| symbol_to_proto(s.clone()))
                .collect(),
        }))
    }

    // ------------------------------------------------------------------
    // GetCommitDiff
    // ------------------------------------------------------------------
    async fn get_commit_diff(
        &self,
        request: Request<GetCommitDiffRequest>,
    ) -> Result<Response<GetCommitDiffResponse>, Status> {
        let req = request.into_inner();

        // Look up or open the GitTracker for this repo.
        let diff: CommitDiff = {
            let mut trackers = self.trackers.lock().await;

            // If we already have a tracker, use it.  Otherwise, we need a path
            // to open a new one.  We use `repo_id` as the path when no explicit
            // local_path is available (callers should have indexed first so the
            // tracker exists, otherwise they receive a clear error).
            if !trackers.contains_key(&req.repo_id) {
                // Attempt to open the tracker using repo_id as the fs path.
                let tracker = GitTracker::open(&req.repo_id, &req.repo_id).map_err(|e| {
                    Status::not_found(format!(
                        "git repo '{}' not found or not yet indexed: {}",
                        req.repo_id, e
                    ))
                })?;
                trackers.insert(req.repo_id.clone(), tracker);
            }

            let tracker = trackers.get(&req.repo_id).expect("just inserted");
            tracker
                .diff_for_commit(&req.commit_sha)
                .map_err(|e| Status::internal(e.to_string()))?
        };

        Ok(Response::new(GetCommitDiffResponse {
            diff: Some(commit_diff_to_proto(diff)),
        }))
    }

    // ------------------------------------------------------------------
    // QueryFunctionDeltas
    //
    // Returns an empty list until persistent delta storage is implemented.
    // ------------------------------------------------------------------
    #[allow(unused_variables)]
    async fn query_function_deltas(
        &self,
        request: Request<QueryFunctionDeltasRequest>,
    ) -> Result<Response<QueryFunctionDeltasResponse>, Status> {
        Ok(Response::new(QueryFunctionDeltasResponse {
            deltas: Vec::new(),
        }))
    }
}

// ─── Conversion helpers ───────────────────────────────────────────────────────

/// Convert a kernel `SymbolNode` to its proto counterpart.
pub fn symbol_to_proto(s: SymbolNode) -> proto::SymbolNode {
    proto::SymbolNode {
        id: s.id,
        repo_id: s.repo_id,
        file_path: s.file_path,
        name: s.name,
        qualified_name: s.qualified_name,
        kind: kernel_kind_to_proto(s.kind),
        start_line: s.start_line,
        end_line: s.end_line,
        signature: s.signature,
        docstring: s.docstring,
        callers: s.callers,
        callees: s.callees,
        deps: s.deps,
        metadata: s.metadata,
    }
}

/// Convert a kernel `CommitDiff` to its proto counterpart.
pub fn commit_diff_to_proto(d: CommitDiff) -> proto::CommitDiff {
    proto::CommitDiff {
        commit_sha: d.commit_sha,
        repo_id: d.repo_id,
        author: d.author,
        message: d.message,
        timestamp: d.timestamp.timestamp(),
        files: d.files.into_iter().map(file_diff_to_proto).collect(),
    }
}

/// Convert a kernel `FileDiff` to its proto counterpart.
pub fn file_diff_to_proto(f: FileDiff) -> proto::FileDiff {
    proto::FileDiff {
        path: f.path,
        old_content: f.old_content,
        new_content: f.new_content,
        added_lines: f.added_lines,
        removed_lines: f.removed_lines,
    }
}

/// Convert a kernel `FunctionDelta` to its proto counterpart.
#[allow(dead_code)]
pub fn function_delta_to_proto(d: FunctionDelta) -> proto::FunctionDelta {
    proto::FunctionDelta {
        function_id: d.function_id,
        commit_sha: d.commit_sha,
        old_body: d.old_body,
        new_body: d.new_body,
        linked_test_ids: d.linked_test_ids,
    }
}

/// Map a proto `SymbolKind` discriminant (i32) to the kernel enum.
pub fn proto_kind_to_kernel(v: i32) -> SymbolKind {
    match v {
        1 => SymbolKind::Function,
        2 => SymbolKind::Class,
        3 => SymbolKind::Struct,
        4 => SymbolKind::Trait,
        5 => SymbolKind::Interface,
        6 => SymbolKind::Module,
        7 => SymbolKind::Variable,
        8 => SymbolKind::Constant,
        9 => SymbolKind::TypeAlias,
        _ => SymbolKind::Function,
    }
}

/// Map the kernel `SymbolKind` enum back to its proto i32 discriminant.
pub fn kernel_kind_to_proto(k: SymbolKind) -> i32 {
    match k {
        SymbolKind::Function => 1,
        SymbolKind::Class => 2,
        SymbolKind::Struct => 3,
        SymbolKind::Trait => 4,
        SymbolKind::Interface => 5,
        SymbolKind::Module => 6,
        SymbolKind::Variable => 7,
        SymbolKind::Constant => 8,
        SymbolKind::TypeAlias => 9,
    }
}
