#!/usr/bin/env python3
# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Initialize or upgrade the ScholarGraph database schema via Alembic.

Run from the repository root::

    uv run python scripts/init_db.py
    uv run python scripts/init_db.py --show-revision

Production and local dev should run this (or ``uv run alembic upgrade head``)
before starting the API. Pytest uses ``create_all`` snapshots in test helpers only.
"""

from __future__ import annotations

import argparse
import sys

from backend.db.migrations import get_current_revision, get_head_revision, upgrade_head

EXIT_SUCCESS = 0
EXIT_ERROR = 1


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply Alembic migrations to DATABASE_URL")
    parser.add_argument(
        "--show-revision",
        action="store_true",
        help="Print current and head revision after upgrade",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        upgrade_head()
    except Exception as exc:
        print(f"init_db failed: {exc}", file=sys.stderr)
        return EXIT_ERROR

    if args.show_revision:
        current = get_current_revision()
        head = get_head_revision()
        print(f"current_revision={current}")
        print(f"head_revision={head}")
        if current != head:
            print("warning: database revision does not match Alembic head", file=sys.stderr)
            return EXIT_ERROR
    return EXIT_SUCCESS


if __name__ == "__main__":
    raise SystemExit(main())
