//! RocksDB-backed persistent storage for the memory kernel.

use anyhow::Result;
use rocksdb::{ColumnFamilyDescriptor, Options, DB};
use std::path::Path;
use tracing::info;

/// Column family names used by the kernel.
pub const CF_L2: &str = "l2_task";
pub const CF_L3: &str = "l3_semantic";
pub const CF_L4: &str = "l4_archive";
pub const CF_META: &str = "meta";

pub struct RocksStore {
    db: DB,
}

impl RocksStore {
    /// Open (or create) the RocksDB database at `path`.
    pub fn open(path: impl AsRef<Path>) -> Result<Self> {
        let path = path.as_ref();
        let mut opts = Options::default();
        opts.create_if_missing(true);
        opts.create_missing_column_families(true);
        opts.set_compression_type(rocksdb::DBCompressionType::Zstd);

        let cfs = [CF_L2, CF_L3, CF_L4, CF_META]
            .into_iter()
            .map(|name| ColumnFamilyDescriptor::new(name, Options::default()))
            .collect::<Vec<_>>();

        let db = DB::open_cf_descriptors(&opts, path, cfs)?;
        info!(?path, "RocksDB opened");
        Ok(Self { db })
    }

    /// Write a key-value pair to the given column family.
    pub fn put(&self, cf: &str, key: &[u8], value: &[u8]) -> Result<()> {
        let handle = self
            .db
            .cf_handle(cf)
            .ok_or_else(|| anyhow::anyhow!("unknown CF: {cf}"))?;
        self.db.put_cf(handle, key, value)?;
        Ok(())
    }

    /// Read a value from the given column family.
    pub fn get(&self, cf: &str, key: &[u8]) -> Result<Option<Vec<u8>>> {
        let handle = self
            .db
            .cf_handle(cf)
            .ok_or_else(|| anyhow::anyhow!("unknown CF: {cf}"))?;
        Ok(self.db.get_cf(handle, key)?)
    }

    /// Delete a key from the given column family.
    pub fn delete(&self, cf: &str, key: &[u8]) -> Result<()> {
        let handle = self
            .db
            .cf_handle(cf)
            .ok_or_else(|| anyhow::anyhow!("unknown CF: {cf}"))?;
        self.db.delete_cf(handle, key)?;
        Ok(())
    }

    /// Iterate over all keys in a column family.
    pub fn scan(&self, cf: &str) -> Result<Vec<(Vec<u8>, Vec<u8>)>> {
        let handle = self
            .db
            .cf_handle(cf)
            .ok_or_else(|| anyhow::anyhow!("unknown CF: {cf}"))?;
        let iter = self.db.iterator_cf(handle, rocksdb::IteratorMode::Start);
        Ok(iter
            .flatten()
            .map(|(k, v)| (k.to_vec(), v.to_vec()))
            .collect())
    }
}
