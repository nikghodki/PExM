# Contributing to ContextOS

Thanks for your interest in making ContextOS better. This guide covers how to
set up a working tree, the checks every change must pass, and how to propose
changes.

## License

By contributing, you agree that your contributions are licensed under the
project's dual **MIT OR Apache-2.0** license (see [LICENSE](LICENSE)).
Please ensure your contributions do not include proprietary code.

## Prerequisites

| Tool | Version | Install |
|---|---|---|
| Rust (stable) | ≥ 1.80 | <https://rustup.rs> |
| `protoc` | ≥ 3.21 | `brew install protobuf` / `apt install protobuf-compiler` |
| Python | ≥ 3.10 | system or `pyenv` |
| `git`, `cargo` | — | — |

The workspace pins `rustfmt` and `clippy` components via `rust-toolchain.toml`;
rustup installs them automatically on first build.

## Development setup

```bash
git clone <repo-url> contextos
cd contextos

# Compile every crate
cargo check --workspace

# Build the gRPC server and `ctx` CLI
cargo build

# Run the full test suite (unit + integration)
cargo test --workspace

# Run the Python SDK tests (no server required)
cd sdk/python
pip install -e ".[dev]"
python -m pytest tests/ -v
```

## Checks every change must pass

Run these from the repo root before opening a pull request. CI runs the same:

```bash
cargo fmt --all --check            # formatting
cargo clippy --workspace --all-targets   # lints
cargo test --workspace             # unit + integration tests
```

For Python SDK changes also run:

```bash
cd sdk/python
ruff check .
python -m pytest tests/ -v
```

## Adding a new gRPC service

1. Add a `.proto` file to `proto/`.
2. Create a crate under `crates/<service>/` with a `build.rs` that runs
   `tonic_build::compile_protos("../../proto/<service>.proto")`.
3. Implement the service trait in `crates/server/src/<service>_svc.rs`.
4. Register it in `crates/server/src/main.rs` with `.add_service(...)`.
5. Regenerate the Python stubs: `make proto-python`.
6. Expose it as a client in `sdk/python/contextos/client.py` and add tests.

## Adding a memory tier / kernel behaviour

The kernel lives in `crates/kernel`. Keep tier storage isolated behind the
`Store` trait so the backend (RocksDB today) stays swappable. Add unit tests
alongside the change.

## Pull requests

1. Open a short issue describing the change (or reference an existing one).
2. Create a feature branch: `git checkout -b feat/<short-description>`.
3. Keep commits focused and well-described; CI must be green.
4. Open a pull request against `main` with a clear summary of the change and
   how you verified it.

## Code of conduct

Participation in this project is governed by the
[Code of Conduct](CODE_OF_CONDUCT.md). Be kind and assume good faith.
