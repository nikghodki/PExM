.PHONY: all build check test fmt lint proto clean server cli sdk docker-up docker-down

PROTO_DIR    := proto
CARGO        := cargo
PYTHON       := python3

all: proto build

## ── Protobuf ─────────────────────────────────────────────────────────────────
proto:
	@echo "==> Generating proto stubs (via tonic-build in build.rs per crate)"
	@echo "    Run 'cargo build' to trigger build scripts."

proto-python:
	@echo "==> Generating Python gRPC stubs from proto/"
	cd sdk/python && $(PYTHON) -m grpc_tools.protoc \
		-I../../proto \
		--python_out=contextos/proto \
		--grpc_python_out=contextos/proto \
		../../proto/memory.proto \
		../../proto/indexer.proto \
		../../proto/policy.proto \
		../../proto/context.proto \
		../../proto/bus.proto \
		../../proto/optimizer.proto

## ── Rust ─────────────────────────────────────────────────────────────────────
build:
	$(CARGO) build --release

check:
	$(CARGO) check

test:
	$(CARGO) test --all

fmt:
	$(CARGO) fmt --all

lint:
	$(CARGO) clippy --all -- -D warnings

server:
	$(CARGO) run --bin contextos-server

cli:
	$(CARGO) run --bin ctx -- $(ARGS)

## ── Python SDK ───────────────────────────────────────────────────────────────
sdk:
	cd sdk/python && pip install -e ".[dev]"

sdk-test:
	cd sdk/python && $(PYTHON) -m pytest tests/ -v

## ── Docker ───────────────────────────────────────────────────────────────────
docker-up:
	docker-compose up -d

docker-down:
	docker-compose down -v

## ── Cleanup ──────────────────────────────────────────────────────────────────
clean:
	$(CARGO) clean
	rm -rf sdk/python/dist sdk/python/*.egg-info
