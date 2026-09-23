//! CLI: audit log operations.

use anyhow::Result;
use clap::Subcommand;

#[derive(Subcommand)]
pub enum AuditAction {
    /// Tail audit events for a principal
    Tail {
        #[arg(long)]
        principal_id: String,
        #[arg(long, default_value = "50")]
        limit: i32,
    },
    /// Stream live audit events
    Stream {
        #[arg(long)]
        principal_id: String,
    },
}

pub async fn run(_server: &str, action: AuditAction) -> Result<()> {
    match action {
        AuditAction::Tail {
            principal_id,
            limit,
        } => {
            println!("→ audit tail: principal={principal_id}, limit={limit}");
        }
        AuditAction::Stream { principal_id } => {
            println!("→ audit stream: principal={principal_id}");
        }
    }
    println!("(gRPC call stubbed)");
    Ok(())
}
