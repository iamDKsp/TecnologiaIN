"""Test configuration utilities."""

import sys
from pathlib import Path

# Ensure the project root is on the import path when running tests directly.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
