#!/usr/bin/env python3
"""Test runner script for DATN project.

Usage:
    python run_tests.py              # Run all tests
    python run_tests.py -v           # Run with verbose output
    python run_tests.py --cov        # Run with coverage
    python run_tests.py -k pattern   # Run tests matching pattern
"""

from __future__ import annotations

import sys


def main() -> int:
    """Run pytest with CLI arguments."""
    try:
        import pytest
    except ImportError:
        print("Error: pytest not installed. Run: pip install pytest pytest-cov")
        return 1
    
    # Default arguments
    args = ["tests/", "-v"]
    
    # Add user arguments
    if len(sys.argv) > 1:
        args.extend(sys.argv[1:])
    
    print(f"Running: pytest {' '.join(args)}")
    print("-" * 50)
    
    return pytest.main(args)


if __name__ == "__main__":
    raise SystemExit(main())
