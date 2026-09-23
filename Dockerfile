# ── Stage 1: builder ──────────────────────────────────────────────────────────
FROM rust:1.93-slim-bookworm AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    protobuf-compiler \
    libprotobuf-dev \
    libclang-dev \
    clang \
    cmake \
    pkg-config \
    libssl-dev \
    libz-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# ── Layer 1: download external crates (cache-friendly) ────────────────────────
# Copy manifests + lock file. cargo fetch downloads all external deps to
# $CARGO_HOME/registry without compiling anything. This layer is only
# invalidated when Cargo.toml / Cargo.lock change.
COPY Cargo.toml Cargo.lock rust-toolchain.toml ./

COPY crates/kernel/Cargo.toml    crates/kernel/Cargo.toml
COPY crates/indexer/Cargo.toml   crates/indexer/Cargo.toml
COPY crates/graph/Cargo.toml     crates/graph/Cargo.toml
COPY crates/policy/Cargo.toml    crates/policy/Cargo.toml
COPY crates/scheduler/Cargo.toml crates/scheduler/Cargo.toml
COPY crates/bus/Cargo.toml       crates/bus/Cargo.toml
COPY crates/optimizer/Cargo.toml crates/optimizer/Cargo.toml
COPY crates/crdt/Cargo.toml      crates/crdt/Cargo.toml
COPY crates/server/Cargo.toml    crates/server/Cargo.toml
COPY cli/Cargo.toml              cli/Cargo.toml

# Minimal stub src files so cargo can resolve the workspace
RUN mkdir -p \
    crates/kernel/src crates/indexer/src crates/graph/src crates/policy/src \
    crates/scheduler/src crates/bus/src crates/optimizer/src crates/crdt/src \
    crates/server/src cli/src && \
    for d in kernel indexer graph policy scheduler bus optimizer crdt; do \
        printf 'pub fn _stub() {}' > crates/$d/src/lib.rs; \
    done && \
    printf 'fn main() {}' > crates/server/src/main.rs && \
    printf 'fn main() {}' > cli/src/main.rs

# Copy build scripts + protos so build.rs scripts can run during fetch
COPY crates/kernel/build.rs    crates/kernel/build.rs
COPY crates/indexer/build.rs   crates/indexer/build.rs
COPY crates/policy/build.rs    crates/policy/build.rs
COPY crates/scheduler/build.rs crates/scheduler/build.rs
COPY crates/bus/build.rs       crates/bus/build.rs
COPY crates/optimizer/build.rs crates/optimizer/build.rs
COPY crates/server/build.rs    crates/server/build.rs
COPY proto/                    proto/

# Fetch all external crate sources (no compilation of our code)
RUN cargo fetch --locked

# ── Layer 2: compile external deps ────────────────────────────────────────────
# Build only external deps using the stubs. This layer is reused as long as
# Cargo.toml / Cargo.lock don't change.
RUN cargo build --release 2>&1 | grep -v "^error" || true

# ── Layer 3: compile real source ──────────────────────────────────────────────
COPY . .

# Touch every .rs file so Cargo knows to recompile all workspace crates
# (external dep artifacts from the previous layer are kept)
RUN find crates cli -name "*.rs" -exec touch {} + && \
    cargo build --release --bin contextos-server --bin ctx

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM debian:bookworm-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    libssl3 \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -ms /bin/bash contextos
USER contextos
WORKDIR /app

COPY --from=builder /build/target/release/contextos-server /app/contextos-server
COPY --from=builder /build/target/release/ctx              /app/ctx

EXPOSE 50051 9090

ENV CONTEXTOS_BIND="0.0.0.0:50051" \
    CONTEXTOS_ROCKSDB_PATH="/data/rocksdb" \
    CONTEXTOS_LOG="info"

VOLUME ["/data"]

ENTRYPOINT ["/app/contextos-server"]
