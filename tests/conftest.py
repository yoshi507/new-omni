import os
import sys
import tempfile
from pathlib import Path

# Isolated data dir + deterministic config before any omnibot import.
_TMP = tempfile.mkdtemp(prefix="omnibot-test-")
os.environ["DATA_DIR"] = _TMP
os.environ.setdefault("SESSION_SECRET", "test-secret-" + "x" * 40)
os.environ.setdefault("DISCORD_CLIENT_ID", "123")
os.environ.setdefault("DISCORD_CLIENT_SECRET", "shh")
os.environ.setdefault("PUBLIC_BASE_URL", "https://dash.example.com")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
