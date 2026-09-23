#!/usr/bin/env python3
"""PExM HTTP API server.

Simple REST API that any agent framework can call.
Works with anything that can make HTTP requests — no SDK needed.

Endpoints:
  POST /absorb     {"state": "...", "outcome": "..."}
  POST /query      {"state": "...", "top_k": 5}
  POST /surprise   {"state": "...", "outcome": "..."}
  GET  /health
  GET  /stats

Start: PYTHONPATH=. python -m pexm.serve.http_server --port 7437
"""

import argparse
import json
import sys
import os
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import torch
from pexm.core.experience_model import ExperienceModel

_model = None
_optimizer = None
_lock = threading.Lock()


def get_model():
    return _model


class PExMHandler(BaseHTTPRequestHandler):
    def _json_response(self, data, status=200):
        body = json.dumps(data, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length))

    def do_GET(self):
        if self.path == "/health":
            self._json_response({"status": "ok", "model": _model.backbone_name,
                                 "stored": _model.n_stored})
        elif self.path == "/stats":
            self._json_response(_model.diagnostics())
        else:
            self._json_response({"error": "not found"}, 404)

    def do_POST(self):
        try:
            body = self._read_json()
        except Exception as e:
            self._json_response({"error": f"invalid JSON: {e}"}, 400)
            return

        if self.path == "/absorb":
            state = body.get("state", "")
            outcome = body.get("outcome", "")
            if not state or not outcome:
                self._json_response({"error": "state and outcome required"}, 400)
                return
            with _lock:
                metrics = _model.absorb(state, outcome)
                _model.maybe_step(_optimizer)
            self._json_response(metrics)

        elif self.path == "/query":
            state = body.get("state", "")
            top_k = body.get("top_k", 5)
            if not state:
                self._json_response({"error": "state required"}, 400)
                return
            with _lock:
                result = _model.query(state, top_k=top_k)
            self._json_response(result)

        elif self.path == "/surprise":
            state = body.get("state", "")
            outcome = body.get("outcome", "")
            if not state or not outcome:
                self._json_response({"error": "state and outcome required"}, 400)
                return
            with _lock:
                score = _model.surprise(state, outcome)
                novel = _model.is_novel(state, outcome)
            self._json_response({"surprise": score, "is_novel": novel})

        elif self.path == "/batch_absorb":
            experiences = body.get("experiences", [])
            if not experiences:
                self._json_response({"error": "experiences list required"}, 400)
                return
            results = []
            with _lock:
                for exp in experiences:
                    m = _model.absorb(exp.get("state", ""), exp.get("outcome", ""))
                    _model.maybe_step(_optimizer)
                    results.append(m)
                _optimizer.step()
                _optimizer.zero_grad()
            self._json_response({"absorbed": len(results),
                                 "stored": _model.n_stored})
        else:
            self._json_response({"error": "not found"}, 404)

    def log_message(self, format, *args):
        pass  # Silence request logs


def main():
    global _model, _optimizer

    parser = argparse.ArgumentParser(description="PExM HTTP API server")
    parser.add_argument("--port", type=int, default=7437)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--device", default=None)
    args = parser.parse_args()

    device = args.device
    if device is None:
        if torch.backends.mps.is_available():
            device = "mps"
        elif torch.cuda.is_available():
            device = "cuda:0"
        else:
            device = "cpu"

    print(f"Loading PExM on {device}...")
    _model = ExperienceModel(device=device)
    _optimizer = _model.get_optimizer()
    _optimizer.zero_grad()
    print(f"Ready. Stored: {_model.n_stored} experiences")

    server = HTTPServer((args.host, args.port), PExMHandler)
    print(f"PExM server listening on http://{args.host}:{args.port}")
    print(f"  POST /absorb     - absorb an experience")
    print(f"  POST /query      - query for relevant context")
    print(f"  POST /surprise   - check novelty of an experience")
    print(f"  POST /batch_absorb - absorb multiple experiences")
    print(f"  GET  /health     - health check")
    print(f"  GET  /stats      - model diagnostics")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()
