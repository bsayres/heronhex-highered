"""Entry point for the .mcpb bundle (host runs it with uv)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from highered_institutions.server import main

main()
