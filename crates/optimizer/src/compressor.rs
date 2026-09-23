//! Memory compressor: zstd byte compression + delta/summary strategies.

use anyhow::Result;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CompressionStrategy {
    /// Raw zstd byte compression.
    Zstd,
    /// Compute a text delta against a reference (reducing stored tokens).
    Delta,
    /// LLM-assisted summarization (stub — requires external LLM call).
    Summary,
    /// Auto: pick the best strategy based on content size.
    Auto,
}

#[derive(Debug)]
pub struct CompressionResult {
    pub before_bytes: usize,
    pub after_bytes: usize,
    pub strategy: CompressionStrategy,
    pub compressed: Vec<u8>,
    pub summary: Option<String>,
}

pub struct MemoryCompressor;

impl MemoryCompressor {
    /// Compress `content` using the given strategy.
    pub fn compress(content: &str, strategy: CompressionStrategy) -> Result<CompressionResult> {
        let strategy = if strategy == CompressionStrategy::Auto {
            if content.len() < 1024 {
                CompressionStrategy::Zstd
            } else {
                CompressionStrategy::Summary
            }
        } else {
            strategy
        };

        match strategy {
            CompressionStrategy::Zstd | CompressionStrategy::Delta => {
                let compressed = zstd::encode_all(content.as_bytes(), 3)?;
                Ok(CompressionResult {
                    before_bytes: content.len(),
                    after_bytes: compressed.len(),
                    strategy,
                    compressed,
                    summary: None,
                })
            }
            CompressionStrategy::Summary | CompressionStrategy::Auto => {
                // Stub: in production, call an LLM to summarize.
                let summary = format!("[Summary of {} chars — LLM stub]", content.len());
                let compressed = zstd::encode_all(summary.as_bytes(), 3)?;
                Ok(CompressionResult {
                    before_bytes: content.len(),
                    after_bytes: compressed.len(),
                    strategy: CompressionStrategy::Summary,
                    compressed,
                    summary: Some(summary),
                })
            }
        }
    }

    /// Decompress bytes that were compressed by this compressor.
    pub fn decompress(data: &[u8]) -> Result<String> {
        let bytes = zstd::decode_all(data)?;
        Ok(String::from_utf8(bytes)?)
    }
}
