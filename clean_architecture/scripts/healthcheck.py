#!/usr/bin/env python3
"""Container health check probe.

Used by the Docker HEALTHCHECK instruction and docker-compose. It probes
Streamlit's built-in liveness endpoint and exits with status 0 when healthy,
1 otherwise. No third-party dependencies are required.
"""
from __future__ import annotations

import os
import sys
import urllib.request

PORT = os.getenv("STREAMLIT_SERVER_PORT", "8501")
URL = f"http://127.0.0.1:{PORT}/_stcore/health"


def main() -> int:
    try:
        with urllib.request.urlopen(URL, timeout=4) as resp:
            if resp.status == 200:
                return 0
            print(f"Unexpected status: {resp.status}", file=sys.stderr)
            return 1
    except Exception as exc:  # pragma: no cover - network dependent
        print(f"Health check failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
