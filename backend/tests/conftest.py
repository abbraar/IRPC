import os
import sys
from pathlib import Path

# Disable external Gemini calls during tests (deterministic, offline).
os.environ.setdefault("GEMINI_DISABLED", "true")

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
