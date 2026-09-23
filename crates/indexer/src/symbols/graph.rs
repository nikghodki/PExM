//! Symbol graph: petgraph DAG of SymbolNodes with call-edge tracking.

use std::collections::HashMap;

use petgraph::graph::{DiGraph, NodeIndex};

use super::SymbolNode;

pub struct SymbolGraph {
    graph: DiGraph<SymbolNode, EdgeKind>,
    id_index: HashMap<String, NodeIndex>,
}

#[derive(Debug, Clone, Copy)]
pub enum EdgeKind {
    Calls,
    DependsOn,
    DefinedIn,
}

impl SymbolGraph {
    pub fn new() -> Self {
        Self {
            graph: DiGraph::new(),
            id_index: HashMap::new(),
        }
    }

    /// Add a symbol node to the graph (idempotent on id).
    pub fn add_symbol(&mut self, symbol: SymbolNode) -> NodeIndex {
        if let Some(&idx) = self.id_index.get(&symbol.id) {
            return idx;
        }
        let id = symbol.id.clone();
        let idx = self.graph.add_node(symbol);
        self.id_index.insert(id, idx);
        idx
    }

    /// Add a call edge from `caller_id` → `callee_id`.
    pub fn add_call_edge(&mut self, caller_id: &str, callee_id: &str) {
        if let (Some(&a), Some(&b)) = (self.id_index.get(caller_id), self.id_index.get(callee_id)) {
            self.graph.add_edge(a, b, EdgeKind::Calls);
        }
    }

    /// Add a cross-repo dependency edge.
    pub fn add_dep_edge(&mut self, from_id: &str, to_id: &str) {
        if let (Some(&a), Some(&b)) = (self.id_index.get(from_id), self.id_index.get(to_id)) {
            self.graph.add_edge(a, b, EdgeKind::DependsOn);
        }
    }

    pub fn get(&self, id: &str) -> Option<&SymbolNode> {
        self.id_index
            .get(id)
            .and_then(|&idx| self.graph.node_weight(idx))
    }

    pub fn node_count(&self) -> usize {
        self.graph.node_count()
    }
    pub fn edge_count(&self) -> usize {
        self.graph.edge_count()
    }

    /// Return all symbols in the graph.
    pub fn all_symbols(&self) -> Vec<&SymbolNode> {
        self.graph.node_weights().collect()
    }
}

impl Default for SymbolGraph {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::symbols::{SymbolKind, SymbolNode};

    fn sym(id: &str, name: &str) -> SymbolNode {
        SymbolNode {
            id: id.into(),
            repo_id: "r".into(),
            file_path: "f.rs".into(),
            name: name.into(),
            qualified_name: format!("f::{name}"),
            kind: SymbolKind::Function,
            start_line: 1,
            end_line: 5,
            signature: String::new(),
            docstring: String::new(),
            callers: vec![],
            callees: vec![],
            deps: vec![],
            metadata: Default::default(),
        }
    }

    #[test]
    fn add_and_get_symbol() {
        let mut g = SymbolGraph::new();
        g.add_symbol(sym("1", "foo"));
        assert!(g.get("1").is_some());
        assert_eq!(g.get("1").unwrap().name, "foo");
    }

    #[test]
    fn idempotent_add() {
        let mut g = SymbolGraph::new();
        g.add_symbol(sym("1", "foo"));
        g.add_symbol(sym("1", "foo"));
        assert_eq!(g.node_count(), 1);
    }

    #[test]
    fn add_call_edge() {
        let mut g = SymbolGraph::new();
        g.add_symbol(sym("a", "caller"));
        g.add_symbol(sym("b", "callee"));
        g.add_call_edge("a", "b");
        assert_eq!(g.edge_count(), 1);
    }

    #[test]
    fn all_symbols_returns_all() {
        let mut g = SymbolGraph::new();
        g.add_symbol(sym("1", "a"));
        g.add_symbol(sym("2", "b"));
        assert_eq!(g.all_symbols().len(), 2);
    }
}
