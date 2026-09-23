//! Multi-language AST parser that converts source files into SymbolNodes.

use anyhow::{bail, Result};
use tree_sitter::{Language, Node, Parser};

use crate::symbols::{SymbolKind, SymbolNode};

pub struct AstParser {
    parser: Parser,
}

impl AstParser {
    pub fn new() -> Self {
        Self {
            parser: Parser::new(),
        }
    }

    /// Parse `source` written in `lang` (e.g. "rust", "python") and extract symbols.
    pub fn parse(
        &mut self,
        repo_id: &str,
        file_path: &str,
        lang: &str,
        source: &str,
    ) -> Result<Vec<SymbolNode>> {
        let language: Language = match lang {
            "rust" => tree_sitter_rust::language(),
            "python" => tree_sitter_python::language(),
            other => bail!("unsupported language: {other}"),
        };
        self.parser.set_language(&language)?;

        let tree = self
            .parser
            .parse(source, None)
            .ok_or_else(|| anyhow::anyhow!("failed to parse {file_path}"))?;

        let mut symbols = Vec::new();
        let root = tree.root_node();
        self.walk(root, source, repo_id, file_path, lang, &mut symbols);
        Ok(symbols)
    }

    fn walk(
        &self,
        node: Node<'_>,
        source: &str,
        repo_id: &str,
        file_path: &str,
        lang: &str,
        out: &mut Vec<SymbolNode>,
    ) {
        let kind = match (lang, node.kind()) {
            ("rust", "function_item") => Some(SymbolKind::Function),
            ("rust", "struct_item") => Some(SymbolKind::Struct),
            ("rust", "trait_item") => Some(SymbolKind::Trait),
            ("rust", "impl_item") => None, // drill into impls
            ("python", "function_definition") => Some(SymbolKind::Function),
            ("python", "class_definition") => Some(SymbolKind::Class),
            _ => None,
        };

        if let Some(symbol_kind) = kind {
            let name = Self::extract_name(node, source).unwrap_or_default();
            if !name.is_empty() {
                out.push(SymbolNode {
                    id: uuid::Uuid::new_v4().to_string(),
                    repo_id: repo_id.to_owned(),
                    file_path: file_path.to_owned(),
                    name: name.clone(),
                    qualified_name: format!("{}::{}", file_path, name),
                    kind: symbol_kind,
                    start_line: node.start_position().row as i32 + 1,
                    end_line: node.end_position().row as i32 + 1,
                    signature: Self::extract_signature(node, source),
                    docstring: String::new(),
                    callers: Vec::new(),
                    callees: Vec::new(),
                    deps: Vec::new(),
                    metadata: std::collections::HashMap::new(),
                });
            }
        }

        let mut cursor = node.walk();
        for child in node.children(&mut cursor) {
            self.walk(child, source, repo_id, file_path, lang, out);
        }
    }

    fn extract_name(node: Node<'_>, source: &str) -> Option<String> {
        let mut cursor = node.walk();
        for child in node.children(&mut cursor) {
            if child.kind() == "identifier" || child.kind() == "name" {
                return Some(source[child.byte_range()].to_owned());
            }
        }
        None
    }

    fn extract_signature(node: Node<'_>, source: &str) -> String {
        // Take up to the opening brace as the signature
        let full = &source[node.byte_range()];
        full.lines().next().unwrap_or("").trim().to_owned()
    }
}

impl Default for AstParser {
    fn default() -> Self {
        Self::new()
    }
}
