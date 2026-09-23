//! Graph traversal with scope filtering.

use petgraph::graph::{DiGraph, NodeIndex};
use petgraph::visit::Bfs;
use std::collections::HashMap;
use uuid::Uuid;

use crate::edges::EdgeType;
use crate::nodes::{MemoryNode, Scope};

pub struct MemoryGraph {
    inner: DiGraph<MemoryNode, EdgeType>,
    index: HashMap<Uuid, NodeIndex>,
}

impl MemoryGraph {
    pub fn new() -> Self {
        Self {
            inner: DiGraph::new(),
            index: HashMap::new(),
        }
    }

    pub fn add_node(&mut self, node: MemoryNode) -> NodeIndex {
        if let Some(&idx) = self.index.get(&node.id) {
            return idx;
        }
        let id = node.id;
        let idx = self.inner.add_node(node);
        self.index.insert(id, idx);
        idx
    }

    pub fn add_edge(&mut self, from: Uuid, to: Uuid, kind: EdgeType) {
        if let (Some(&a), Some(&b)) = (self.index.get(&from), self.index.get(&to)) {
            self.inner.add_edge(a, b, kind);
        }
    }

    pub fn get(&self, id: &Uuid) -> Option<&MemoryNode> {
        self.index
            .get(id)
            .and_then(|&idx| self.inner.node_weight(idx))
    }

    /// BFS from a start node, filtered to the given scope (and broader scopes).
    pub fn bfs(&self, start: &Uuid, viewer_scope: Scope) -> Vec<&MemoryNode> {
        let Some(&start_idx) = self.index.get(start) else {
            return Vec::new();
        };
        let mut bfs = Bfs::new(&self.inner, start_idx);
        let mut results = Vec::new();
        while let Some(idx) = bfs.next(&self.inner) {
            let node = &self.inner[idx];
            if is_visible(node.scope, viewer_scope) {
                results.push(node);
            }
        }
        results
    }

    pub fn node_count(&self) -> usize {
        self.inner.node_count()
    }
    pub fn edge_count(&self) -> usize {
        self.inner.edge_count()
    }
}

/// A viewer at `viewer_scope` can see nodes at their scope and at Org level.
fn is_visible(node_scope: Scope, viewer_scope: Scope) -> bool {
    matches!(
        (node_scope, viewer_scope),
        (Scope::Org, _)
            | (Scope::Team, Scope::Team)
            | (Scope::Team, Scope::Org)
            | (Scope::Private, Scope::Private)
            | (Scope::Ephemeral, _)
    )
}

impl Default for MemoryGraph {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::edges::EdgeType;
    use crate::nodes::{MemoryNode, NodeType, Scope};

    fn node(nt: NodeType, scope: Scope) -> MemoryNode {
        MemoryNode::new(nt, scope, "label", "content")
    }

    #[test]
    fn add_node_and_get() {
        let mut g = MemoryGraph::new();
        let n = node(NodeType::AgentNote, Scope::Private);
        let id = n.id;
        g.add_node(n);
        assert!(g.get(&id).is_some());
    }

    #[test]
    fn bfs_returns_connected_nodes() {
        let mut g = MemoryGraph::new();
        let a = node(NodeType::AgentNote, Scope::Org);
        let b = node(NodeType::CodeSymbol, Scope::Org);
        let a_id = a.id;
        let b_id = b.id;
        g.add_node(a);
        g.add_node(b);
        g.add_edge(a_id, b_id, EdgeType::References);

        let results = g.bfs(&a_id, Scope::Org);
        assert_eq!(results.len(), 2);
    }

    #[test]
    fn bfs_scope_filter_excludes_private() {
        let mut g = MemoryGraph::new();
        let a = node(NodeType::AgentNote, Scope::Org);
        let b = node(NodeType::AgentNote, Scope::Private);
        let a_id = a.id;
        let b_id = b.id;
        g.add_node(a);
        g.add_node(b);
        g.add_edge(a_id, b_id, EdgeType::References);

        // Team viewer cannot see Private nodes
        let results = g.bfs(&a_id, Scope::Team);
        assert!(!results.iter().any(|n| n.id == b_id));
    }
}
