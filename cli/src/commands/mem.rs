//! CLI: memory operations.

use anyhow::Result;
use clap::Subcommand;

#[derive(Subcommand)]
pub enum MemAction {
    /// Store a new memory entry
    Store {
        #[arg(long)]
        agent_id: String,
        #[arg(long)]
        content: String,
        #[arg(long, default_value = "1")]
        tier: i32,
        #[arg(long, default_value = "1")]
        scope: i32,
    },
    /// Retrieve a memory entry by ID
    Get {
        #[arg(long)]
        id: String,
    },
    /// Search memories by text query
    Search {
        #[arg(long)]
        agent_id: String,
        #[arg(long)]
        query: String,
        #[arg(long, default_value = "10")]
        top_k: i32,
    },
    /// Promote a memory to a higher tier
    Promote {
        #[arg(long)]
        id: String,
        #[arg(long)]
        target_tier: i32,
    },
    /// Delete a memory entry
    Delete {
        #[arg(long)]
        id: String,
    },
}

pub async fn run(_server: &str, action: MemAction) -> Result<()> {
    // TODO: connect to server via tonic gRPC channel + execute RPC
    match action {
        MemAction::Store {
            agent_id,
            content,
            tier,
            scope: _,
        } => {
            println!("→ store: agent={agent_id}, tier={tier}, content='{content}'");
        }
        MemAction::Get { id } => {
            println!("→ get: id={id}");
        }
        MemAction::Search {
            agent_id,
            query,
            top_k,
        } => {
            println!("→ search: agent={agent_id}, query='{query}', top_k={top_k}");
        }
        MemAction::Promote { id, target_tier } => {
            println!("→ promote: id={id} → tier={target_tier}");
        }
        MemAction::Delete { id } => {
            println!("→ delete: id={id}");
        }
    }
    println!("(gRPC call stubbed — run 'contextos-server' and wire tonic channel)");
    Ok(())
}
