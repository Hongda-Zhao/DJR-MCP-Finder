#!/usr/bin/env python3
"""Run one benchmark embedding config with the multi-backend embedder."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from djrmcp_finder.benchmark_config import expand_benchmark_model
from djrmcp_finder.config import load_config
from djrmcp_finder.stages.benchmark_embedding import run


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--model", required=True)
    parser.add_argument("--device", default=None)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    config = expand_benchmark_model(load_config(args.config), args.model)
    result = run(config, device_override=args.device, limit=args.limit)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
