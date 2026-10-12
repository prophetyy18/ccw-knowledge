#!/usr/bin/env python3
"""Run all ccw-knowledge tests.

Usage:
    python scripts/run_tests.py [--unit-only] [--e2e-only] [--verbose]
"""
from __future__ import annotations

import argparse
import os
import sys
import unittest
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--unit-only", action="store_true")
    parser.add_argument("--e2e-only", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    if not args.e2e_only:
        suite.addTests(loader.discover(start_dir=str(repo_root / "tests" / "unit"),
                                       pattern="test_*.py",
                                       top_level_dir=str(repo_root)))
    if not args.unit_only:
        suite.addTests(loader.discover(start_dir=str(repo_root / "tests" / "e2e"),
                                       pattern="test_*.py",
                                       top_level_dir=str(repo_root)))

    runner = unittest.TextTestRunner(verbosity=2 if args.verbose else 1)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
