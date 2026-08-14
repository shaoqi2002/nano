import os
from pathlib import Path

from dotenv import load_dotenv


BACKEND_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BACKEND_DIR / ".env")

DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
CHAT_CONTEXT_MESSAGE_LIMIT = int(os.getenv("CHAT_CONTEXT_MESSAGE_LIMIT", "50"))
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://agent:agent@localhost:5432/agent",
)
