"""pytest configuration for 书山有路 backend tests."""
import sys
from pathlib import Path

# Ensure backend root is on sys.path so "from app.xxx" imports work
backend_root = Path(__file__).resolve().parent.parent
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))
