"""Avoid pytest putting the local adapter package ahead of the official SDK."""
import sys
from pathlib import Path

_adapter_root = str(Path(__file__).resolve().parents[1])
while _adapter_root in sys.path:
    sys.path.remove(_adapter_root)
sys.modules.pop("a2a", None)
