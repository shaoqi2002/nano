import os
from pathlib import Path

from dotenv import load_dotenv


BACKEND_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BACKEND_DIR / ".env")

DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
CHAT_CONTEXT_MESSAGE_LIMIT = int(os.getenv("CHAT_CONTEXT_MESSAGE_LIMIT", "50"))
AGENT_MAX_TOOL_ROUNDS = int(os.getenv("AGENT_MAX_TOOL_ROUNDS", "4"))
AGENT_MAX_TOOL_CALLS = int(os.getenv("AGENT_MAX_TOOL_CALLS", "6"))
WEB_SEARCH_MAX_RESULTS = int(os.getenv("WEB_SEARCH_MAX_RESULTS", "5"))
WEB_SEARCH_TIMEOUT_SECONDS = float(
    os.getenv("WEB_SEARCH_TIMEOUT_SECONDS", "15")
)
WEB_EXTRACT_MAX_URLS = int(os.getenv("WEB_EXTRACT_MAX_URLS", "5"))
WEB_EXTRACT_MAX_CONTENT_LENGTH = int(
    os.getenv("WEB_EXTRACT_MAX_CONTENT_LENGTH", "20000")
)
WEB_EXTRACT_TIMEOUT_SECONDS = float(
    os.getenv("WEB_EXTRACT_TIMEOUT_SECONDS", "45")
)
DEEP_RESEARCH_TIMEOUT_SECONDS = float(
    os.getenv("DEEP_RESEARCH_TIMEOUT_SECONDS", "180")
)
DEEP_RESEARCH_POLL_INTERVAL_SECONDS = float(
    os.getenv("DEEP_RESEARCH_POLL_INTERVAL_SECONDS", "2")
)
DEEP_RESEARCH_MAX_CONTENT_LENGTH = int(
    os.getenv("DEEP_RESEARCH_MAX_CONTENT_LENGTH", "30000")
)
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://agent:agent@localhost:5432/agent",
)
