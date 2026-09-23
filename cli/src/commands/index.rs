//! CLI: code indexing operations.

use anyhow::Result;
use clap::Subcommand;

#[derive(Subcommand)]
pub enum IndexAction {
    /// Index a local repository
    Repo {
        #[arg(long)]
        path: String,
        #[arg(long)]
        repo_id: String,
        #[arg(long, default_value = "rust")]
        lang: String,
        #[arg(long, default_value_t = false)]
        incremental: bool,
    },
    /// Query symbols in an indexed repo
    Symbols {
        #[arg(long)]
        repo_id: String,
        #[arg(long)]
        query: String,
        #[arg(long, default_value = "10")]
        top_k: i32,
    },
    /// Show commit diff
    Diff {
        #[arg(long)]
        repo_id: String,
        #[arg(long)]
        sha: String,
    },
}

pub async fn run(_server: &str, action: IndexAction) -> Result<()> {
    match action {
        IndexAction::Repo {
            path,
            repo_id,
            lang,
            incremental,
        } => {
            println!(
                "→ index repo: path={path}, repo={repo_id}, lang={lang}, incremental={incremental}"
            );
        }
        IndexAction::Symbols {
            repo_id,
            query,
            top_k,
        } => {
            println!("→ query symbols: repo={repo_id}, query='{query}', top_k={top_k}");
        }
        IndexAction::Diff { repo_id, sha } => {
            println!("→ diff: repo={repo_id}, sha={sha}");
        }
    }
    println!("(gRPC call stubbed)");
    Ok(())
}
