#!/usr/bin/env python3
"""PExM MCP Server — Model Context Protocol over stdio.

Works with Claude Code, OpenClaw, Codex, and any MCP-compatible agent.
MCP is JSON-RPC 2.0 over stdin/stdout — no dependencies beyond stdlib.

Tools exposed:
  pexm_absorb    - absorb a new experience
  pexm_query     - query for relevant context
  pexm_surprise  - check if an experience is novel

Start:
  PYTHONPATH=. python -m pexm.serve.mcp_server

Configure in Claude Code (.claude/settings.json):
  {"mcpServers": {"pexm": {"command": "python", "args": ["-m", "pexm.serve.mcp_server"]}}}
"""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import torch
from pexm.core.experience_model import ExperienceModel

_model = None
_optimizer = None


def _ensure_model():
    global _model, _optimizer
    if _model is None:
        device = "mps" if torch.backends.mps.is_available() else "cuda:0" if torch.cuda.is_available() else "cpu"
        _model = ExperienceModel(device=device)
        _optimizer = _model.get_optimizer()
        _optimizer.zero_grad()
        _log(f"PExM loaded on {device}")


def _log(msg):
    sys.stderr.write(f"[pexm] {msg}\n")
    sys.stderr.flush()


TOOLS = [
    {
        "name": "pexm_absorb",
        "description": "Absorb a new experience into PExM memory. Call this when the agent learns something — reads a file, gets a tool result, discovers a fact. The model learns from the experience and stores it for future retrieval.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "state": {"type": "string", "description": "What was happening (e.g. 'debugging the auth module')"},
                "outcome": {"type": "string", "description": "What was learned (e.g. 'JWT tokens expire after 3600 seconds')"},
            },
            "required": ["state", "outcome"],
        },
    },
    {
        "name": "pexm_query",
        "description": "Query PExM for relevant context based on what the agent is currently doing. Returns ranked text from absorbed experiences, ready to use as context.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "state": {"type": "string", "description": "What the agent is doing now (e.g. 'fixing token expiry in tests')"},
                "top_k": {"type": "integer", "description": "Number of results (default 5)", "default": 5},
            },
            "required": ["state"],
        },
    },
    {
        "name": "pexm_surprise",
        "description": "Check how novel an experience is. Returns a score from 0 (familiar) to 1 (never seen). Use this to decide whether to absorb — high surprise means new information worth learning.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "state": {"type": "string", "description": "Context of the experience"},
                "outcome": {"type": "string", "description": "Content to check for novelty"},
            },
            "required": ["state", "outcome"],
        },
    },
]


def handle_request(request):
    method = request.get("method", "")
    req_id = request.get("id")
    params = request.get("params", {})

    if method == "initialize":
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "pexm", "version": "0.1.0"},
        }

    if method == "notifications/initialized":
        return None

    if method == "tools/list":
        return {"tools": TOOLS}

    if method == "tools/call":
        _ensure_model()
        tool_name = params.get("name", "")
        args = params.get("arguments", {})

        if tool_name == "pexm_absorb":
            metrics = _model.absorb(args["state"], args["outcome"])
            _model.maybe_step(_optimizer)
            text = (f"Absorbed. Surprise: {metrics['surprise']:.3f}. "
                    f"Stored: {_model.n_stored} experiences.")
            return {"content": [{"type": "text", "text": text}]}

        elif tool_name == "pexm_query":
            result = _model.query(args["state"], top_k=args.get("top_k", 5))
            if not result["context"]:
                text = "No relevant experiences found."
            else:
                text = result["context"]
            return {"content": [{"type": "text", "text": text}]}

        elif tool_name == "pexm_surprise":
            score = _model.surprise(args["state"], args["outcome"])
            novel = _model.is_novel(args["state"], args["outcome"])
            text = f"Surprise: {score:.3f}. {'Novel — worth absorbing.' if novel else 'Familiar — already known.'}"
            return {"content": [{"type": "text", "text": text}]}

        return {"content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}], "isError": True}

    if method == "ping":
        return {}

    return None


def main():
    _log("PExM MCP server starting (stdio)")

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue

        result = handle_request(request)

        if result is not None:
            response = {"jsonrpc": "2.0", "id": request.get("id"), "result": result}
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
