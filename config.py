import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

# Telegram Bot Config
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# UM Spectrum Config
SPECTRUM_BASE_URL = os.getenv("SPECTRUM_BASE_URL", "https://spectrum.um.edu.my").rstrip("/")
CHECK_INTERVAL_MINUTES = int(os.getenv("CHECK_INTERVAL_MINUTES", "30"))
SISWA_EMAIL = os.getenv("SISWA_EMAIL", "").strip()

# Monitored courses whitelist (comma separated, or empty for all enrolled courses)
_monitored_raw = os.getenv("MONITORED_COURSES", "").strip()
MONITORED_COURSES = [c.strip() for c in _monitored_raw.split(",") if c.strip()] if _monitored_raw else []

# Excluded courses blacklist (comma separated keywords to ignore)
_excluded_raw = os.getenv("EXCLUDED_COURSES", "LEAP,Turnitin").strip()
EXCLUDED_COURSES = [c.strip() for c in _excluded_raw.split(",") if c.strip()] if _excluded_raw else []

# File paths
AUTH_STATE_FILE = BASE_DIR / "auth_state.json"
DB_FILE = BASE_DIR / "spectrumbot.db"
# Auto-migrate legacy database if present
_legacy_db = BASE_DIR / "specwatch.db"
if not DB_FILE.exists() and _legacy_db.exists():
    try:
        _legacy_db.rename(DB_FILE)
    except Exception:
        DB_FILE = _legacy_db

def validate_config(require_telegram: bool = True) -> tuple[bool, str]:
    """Validates configuration parameters."""
    if require_telegram:
        if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "your_bot_token_here":
            return False, "TELEGRAM_BOT_TOKEN is not set in .env or is still using placeholder value."
        if not TELEGRAM_CHAT_ID or TELEGRAM_CHAT_ID == "your_chat_id_here":
            return False, "TELEGRAM_CHAT_ID is not set in .env or is still using placeholder value."
    return True, ""
