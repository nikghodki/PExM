# Contributing to PExM

We welcome contributions! Here's how to get started.

## Setup

```bash
git clone https://github.com/nikghodki/pexm.git
cd pexm
pip install -e ".[dev]"
```

Requires Python 3.9+ and PyTorch with MPS (Apple Silicon) or CUDA.

## Running Tests

```bash
PYTHONPATH=. python -m unittest discover pexm/tests -v
```

## Running Benchmarks

```bash
PYTHONPATH=. python -m pexm.benchmarks.generate_corpus
PYTHONPATH=. python -m pexm.benchmarks.run_full_benchmark
```

## Project Structure

```
pexm/
  core/                 # Core model — ExperienceModel, streams
  serve/                # MCP server + HTTP server
  benchmarks/           # Corpus generation + evaluation
  tests/
examples/               # Quickstart, comparison, integration configs
integrations/           # Framework-specific configs and guides
```

## What to Contribute

**High impact:**
- Real-world agent integration examples (CrewAI, LangGraph, etc.)
- Better backbone models (domain-specific, multilingual)
- Scale testing beyond 500 experiences
- Improved surprise calibration

**Medium impact:**
- New benchmark datasets
- Persistence (save/load model state)
- Batch absorb optimization
- Documentation improvements

**Experiments we'd love to see:**
- PExM on a real codebase (git history as experiences)
- Multi-agent memory sharing
- Online self-improvement from agent task outcomes

## Pull Request Process

1. Fork the repository
2. Create a feature branch: `git checkout -b feat/your-feature`
3. Run tests: `PYTHONPATH=. python -m unittest discover pexm/tests -v`
4. Commit with a clear message
5. Open a PR with a description of what changed and why

## Code Style

- No comments unless the WHY is non-obvious
- Prefer simple over clever
- Functions should do one thing
- If a benchmark number changes, update the README

## License

By contributing, you agree that your contributions will be licensed under Apache-2.0.
