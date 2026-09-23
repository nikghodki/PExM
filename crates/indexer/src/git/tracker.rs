//! Git-aware diff tracking using libgit2 bindings.

use anyhow::Result;
use chrono::{DateTime, TimeZone, Utc};
use git2::{DiffOptions, Repository};
use serde::{Deserialize, Serialize};
use std::path::Path;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FileDiff {
    pub path: String,
    pub added_lines: i32,
    pub removed_lines: i32,
    pub old_content: String,
    pub new_content: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CommitDiff {
    pub repo_id: String,
    pub commit_sha: String,
    pub author: String,
    pub message: String,
    pub timestamp: DateTime<Utc>,
    pub files: Vec<FileDiff>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FunctionDelta {
    pub function_id: String,
    pub commit_sha: String,
    pub old_body: String,
    pub new_body: String,
    pub linked_test_ids: Vec<String>,
}

pub struct GitTracker {
    repo: Repository,
    repo_id: String,
}

impl GitTracker {
    pub fn open(repo_path: impl AsRef<Path>, repo_id: impl Into<String>) -> Result<Self> {
        let repo = Repository::open(repo_path)?;
        let repo_id = repo_id.into();
        Ok(Self { repo, repo_id })
    }

    /// Compute the diff for a specific commit SHA.
    pub fn diff_for_commit(&self, sha: &str) -> Result<CommitDiff> {
        let oid = self.repo.revparse_single(sha)?.id();
        let commit = self.repo.find_commit(oid)?;
        let tree = commit.tree()?;

        let parent_tree = commit.parent(0).ok().and_then(|p| p.tree().ok());

        let mut diff_opts = DiffOptions::new();
        let diff =
            self.repo
                .diff_tree_to_tree(parent_tree.as_ref(), Some(&tree), Some(&mut diff_opts))?;

        // Collect file paths first (file callback), then count lines (line callback).
        // Rust disallows two closures mutably borrowing `files` simultaneously,
        // so we do two passes over the diff.

        // Pass 1: collect file entries
        let mut files: Vec<FileDiff> = Vec::new();
        diff.foreach(
            &mut |delta, _| {
                let path = delta
                    .new_file()
                    .path()
                    .map(|p| p.to_string_lossy().into_owned())
                    .unwrap_or_default();
                files.push(FileDiff {
                    path,
                    added_lines: 0,
                    removed_lines: 0,
                    old_content: String::new(),
                    new_content: String::new(),
                });
                true
            },
            None,
            None,
            None,
        )?;

        // Pass 2: count added / removed lines per file (tracked by index)
        let mut file_idx: usize = 0;
        let mut line_counts: Vec<(i32, i32)> = vec![(0, 0); files.len()];
        diff.foreach(
            &mut |_, _| {
                file_idx += 1;
                true
            },
            None,
            None,
            Some(&mut |delta, _, line| {
                // delta.new_file().path() lets us match back to our files vec
                let path = delta
                    .new_file()
                    .path()
                    .map(|p| p.to_string_lossy().into_owned())
                    .unwrap_or_default();
                if let Some(idx) = files.iter().position(|f| f.path == path) {
                    match line.origin() {
                        '+' => line_counts[idx].0 += 1,
                        '-' => line_counts[idx].1 += 1,
                        _ => {}
                    }
                }
                true
            }),
        )?;

        for (i, (added, removed)) in line_counts.into_iter().enumerate() {
            if let Some(f) = files.get_mut(i) {
                f.added_lines = added;
                f.removed_lines = removed;
            }
        }

        let author = commit.author();
        let timestamp = Utc
            .timestamp_opt(commit.time().seconds(), 0)
            .single()
            .unwrap_or_else(Utc::now);

        Ok(CommitDiff {
            repo_id: self.repo_id.clone(),
            commit_sha: sha.to_owned(),
            author: author.name().unwrap_or("unknown").to_owned(),
            message: commit.message().unwrap_or("").trim().to_owned(),
            timestamp,
            files,
        })
    }

    /// Walk recent commits and collect diffs up to `limit`.
    pub fn recent_commits(&self, limit: usize) -> Result<Vec<CommitDiff>> {
        let mut walk = self.repo.revwalk()?;
        walk.push_head()?;

        let mut results = Vec::new();
        for oid in walk.take(limit) {
            let oid = oid?;
            match self.diff_for_commit(&oid.to_string()) {
                Ok(d) => results.push(d),
                Err(e) => tracing::warn!("skipping commit {oid}: {e}"),
            }
        }
        Ok(results)
    }
}
