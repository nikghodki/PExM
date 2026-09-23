//! ContextOS CLI (`ctx`)
//!
//! Usage:
//!   ctx mem store --agent-id <UUID> --content "..."
//!   ctx mem get   --id <UUID>
//!   ctx index repo --path ./my-repo --lang rust
//!   ctx audit tail --principal-id <UUID>
//!   ctx bus subscribe --agent-id <UUID>

use anyhow::Result;
use clap::{Parser, Subcommand};

mod commands;

#[derive(Parser)]
#[command(
    name = "ctx",
    about = "ContextOS CLI — enterprise AI memory management",
    version,
    propagate_version = true
)]
struct Cli {
    /// gRPC server address
    #[arg(long, env = "CONTEXTOS_SERVER", default_value = "http://[::1]:50051")]
    server: String,

    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Memory operations (store, get, search, promote, delete)
    Mem {
        #[command(subcommand)]
        action: commands::mem::MemAction,
    },

    /// Code indexing operations
    Index {
        #[command(subcommand)]
        action: commands::index::IndexAction,
    },

    /// Audit log operations
    Audit {
        #[command(subcommand)]
        action: commands::audit::AuditAction,
    },

    /// Memory bus operations
    Bus {
        #[command(subcommand)]
        action: commands::bus::BusAction,
    },
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(tracing_subscriber::EnvFilter::from_default_env())
        .init();

    let cli = Cli::parse();

    match cli.command {
        Commands::Mem { action } => commands::mem::run(&cli.server, action).await?,
        Commands::Index { action } => commands::index::run(&cli.server, action).await?,
        Commands::Audit { action } => commands::audit::run(&cli.server, action).await?,
        Commands::Bus { action } => commands::bus::run(&cli.server, action).await?,
    }

    Ok(())
}
