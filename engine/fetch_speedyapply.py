#!/usr/bin/env python3
"""Entry point for the daily fetch. The code lives in engine/fetch/.

One file per source, one shared schema, one ledger that records when a listing
was first seen, last seen, and whether it is still open. Exit code is non-zero
when a source returns nothing, and in that case nothing is written.

Usage: python3 engine/fetch_speedyapply.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import fetch  # noqa: E402

if __name__ == "__main__":
    sys.exit(fetch.main())
