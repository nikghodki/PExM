//! CLI: memory bus operations.

use anyhow::Result;
use clap::Subcommand;

#[derive(Subcommand)]
pub enum BusAction {
    /// Subscribe to memory events
    Subscribe {
        #[arg(long)]
        agent_id: String,
        #[arg(long, value_delimiter = ',', default_values_t = vec!["all".to_owned()])]
        events: Vec<String>,
    },
    /// Publish a test memory event
    Publish {
        #[arg(long)]
        memory_id: String,
        #[arg(long)]
        agent_id: String,
        #[arg(long, default_value = "memory_created")]
        kind: String,
    },
}

pub async fn run(_server: &str, action: BusAction) -> Result<()> {
    match action {
        BusAction::Subscribe { agent_id, events } => {
            println!("→ bus subscribe: agent={agent_id}, events={events:?}");
        }
        BusAction::Publish {
            memory_id,
            agent_id,
            kind,
        } => {
            println!("→ bus publish: memory={memory_id}, agent={agent_id}, kind={kind}");
        }
    }
    println!("(gRPC call stubbed)");
    Ok(())
}
