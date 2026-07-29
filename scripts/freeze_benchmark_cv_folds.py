#!/usr/bin/env python3
"""Freeze the one Train global-component 5-fold map shared by all candidates/heads."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from djrmcp_finder.config import load_config
from djrmcp_finder.cv_folds import freeze_cv_fold_map


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument(
        "--reuse-if-valid",
        action="store_true",
        help="Validate and reuse an existing immutable map; never overwrite it.",
    )
    args = parser.parse_args()
    result = freeze_cv_fold_map(
        load_config(args.config), reuse_if_valid=args.reuse_if_valid
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
