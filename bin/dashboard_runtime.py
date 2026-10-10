#!/usr/bin/env python3
"""Portable entrypoint for MCP clients that do not support a cwd option."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from dashboard_runtime.__main__ import main
raise SystemExit(main())
