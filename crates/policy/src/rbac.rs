//! Role-Based Access Control implementation.

use std::collections::HashMap;
use std::sync::{Arc, RwLock};

use serde::{Deserialize, Serialize};
use uuid::Uuid;

// ─── Types ─────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Action {
    Read,
    Write,
    Delete,
    Admin,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Effect {
    Allow,
    Deny,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Role {
    pub id: Uuid,
    pub name: String,
    pub permissions: Vec<String>, // resource glob patterns
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PolicyRule {
    pub id: Uuid,
    pub role_id: Uuid,
    pub resource: String, // glob pattern, e.g. "memory:*"
    pub action: Action,
    pub effect: Effect,
    pub priority: i32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Principal {
    pub id: Uuid,
    pub name: String,
    pub role_ids: Vec<Uuid>,
}

// ─── Engine ────────────────────────────────────────────────────────────────────

#[derive(Clone)]
pub struct PolicyEngine {
    rules: Arc<RwLock<Vec<PolicyRule>>>,
    roles: Arc<RwLock<HashMap<Uuid, Role>>>,
    principals: Arc<RwLock<HashMap<Uuid, Principal>>>,
}

impl PolicyEngine {
    pub fn new() -> Self {
        Self {
            rules: Arc::new(RwLock::new(Vec::new())),
            roles: Arc::new(RwLock::new(HashMap::new())),
            principals: Arc::new(RwLock::new(HashMap::new())),
        }
    }

    pub fn add_role(&self, role: Role) {
        let mut roles = self.roles.write().expect("roles write");
        roles.insert(role.id, role);
    }

    pub fn add_rule(&self, rule: PolicyRule) {
        let mut rules = self.rules.write().expect("rules write");
        rules.push(rule);
        rules.sort_by_key(|r| std::cmp::Reverse(r.priority));
        let _ = &rules; // satisfy borrow checker
    }

    pub fn add_principal(&self, principal: Principal) {
        let mut principals = self.principals.write().expect("principals write");
        principals.insert(principal.id, principal);
    }

    /// Evaluate the policy for (principal, resource, action).
    /// Returns (Effect, Option<matching_rule_id>).
    pub fn check(
        &self,
        principal_id: &Uuid,
        resource: &str,
        action: Action,
    ) -> (Effect, Option<Uuid>) {
        let principals = self.principals.read().expect("principals read");
        let rules = self.rules.read().expect("rules read");

        let role_ids: Vec<Uuid> = principals
            .get(principal_id)
            .map(|p| p.role_ids.clone())
            .unwrap_or_default();

        for rule in rules.iter() {
            if !role_ids.contains(&rule.role_id) {
                continue;
            }
            if rule.action != action {
                continue;
            }
            if !glob_match(&rule.resource, resource) {
                continue;
            }
            return (rule.effect, Some(rule.id));
        }

        // Default deny
        (Effect::Deny, None)
    }
}

impl Default for PolicyEngine {
    fn default() -> Self {
        Self::new()
    }
}

/// Simple glob matching supporting `*` and `?` wildcards.
fn glob_match(pattern: &str, value: &str) -> bool {
    if pattern == "*" {
        return true;
    }
    if !pattern.contains('*') && !pattern.contains('?') {
        return pattern == value;
    }
    let mut p = pattern.chars().peekable();
    let mut v = value.chars().peekable();
    glob_match_inner(&mut p, &mut v)
}

fn glob_match_inner(
    p: &mut std::iter::Peekable<std::str::Chars<'_>>,
    v: &mut std::iter::Peekable<std::str::Chars<'_>>,
) -> bool {
    loop {
        match (p.peek().copied(), v.peek().copied()) {
            (None, None) => return true,
            (Some('*'), _) => {
                p.next();
                if p.peek().is_none() {
                    return true;
                }
                // Try matching `*` against all suffixes
                let p_rest: String = p.collect();
                let v_rest: String = v.collect();
                for i in 0..=v_rest.len() {
                    let mut pp = p_rest.chars().peekable();
                    let mut vv = v_rest[i..].chars().peekable();
                    if glob_match_inner(&mut pp, &mut vv) {
                        return true;
                    }
                }
                return false;
            }
            (Some('?'), Some(_)) => {
                p.next();
                v.next();
            }
            (Some(pc), Some(vc)) if pc == vc => {
                p.next();
                v.next();
            }
            _ => return false,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn setup() -> (PolicyEngine, Uuid, Uuid) {
        let engine = PolicyEngine::new();
        let role_id = Uuid::new_v4();
        let principal_id = Uuid::new_v4();

        engine.add_role(Role {
            id: role_id,
            name: "reader".into(),
            permissions: vec![],
        });
        engine.add_rule(PolicyRule {
            id: Uuid::new_v4(),
            role_id,
            resource: "memory:*".into(),
            action: Action::Read,
            effect: Effect::Allow,
            priority: 10,
        });
        engine.add_principal(Principal {
            id: principal_id,
            name: "agent".into(),
            role_ids: vec![role_id],
        });
        (engine, role_id, principal_id)
    }

    #[test]
    fn allow_read_on_matching_resource() {
        let (engine, _, pid) = setup();
        let (effect, rule) = engine.check(&pid, "memory:abc123", Action::Read);
        assert_eq!(effect, Effect::Allow);
        assert!(rule.is_some());
    }

    #[test]
    fn deny_write_when_only_read_granted() {
        let (engine, _, pid) = setup();
        let (effect, rule) = engine.check(&pid, "memory:abc123", Action::Write);
        assert_eq!(effect, Effect::Deny);
        assert!(rule.is_none());
    }

    #[test]
    fn deny_unknown_principal() {
        let (engine, _, _) = setup();
        let (effect, _) = engine.check(&Uuid::new_v4(), "memory:x", Action::Read);
        assert_eq!(effect, Effect::Deny);
    }

    #[test]
    fn glob_wildcard_matches_any() {
        assert!(glob_match("memory:*", "memory:anything"));
        assert!(glob_match("*", "whatever"));
        assert!(!glob_match("memory:*", "other:thing"));
    }

    #[test]
    fn glob_exact_match() {
        assert!(glob_match("memory:abc", "memory:abc"));
        assert!(!glob_match("memory:abc", "memory:xyz"));
    }
}
