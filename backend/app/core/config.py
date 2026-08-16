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
LANGGRAPH_DATABASE_URL = os.getenv(
    "LANGGRAPH_DATABASE_URL",
    DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://", 1),
)
LANGGRAPH_POOL_SIZE = int(os.getenv("LANGGRAPH_POOL_SIZE", "10"))
OBJECT_STORAGE_ENDPOINT_URL = os.getenv("OBJECT_STORAGE_ENDPOINT_URL", "")
OBJECT_STORAGE_REGION = os.getenv("OBJECT_STORAGE_REGION", "")
OBJECT_STORAGE_ACCESS_KEY_ID = os.getenv("OBJECT_STORAGE_ACCESS_KEY_ID", "")
OBJECT_STORAGE_SECRET_ACCESS_KEY = os.getenv(
    "OBJECT_STORAGE_SECRET_ACCESS_KEY",
    "",
)
OBJECT_STORAGE_BUCKET = os.getenv("OBJECT_STORAGE_BUCKET", "")
DOCUMENT_MAX_BYTES = int(os.getenv("DOCUMENT_MAX_BYTES", str(25 * 1024 * 1024)))
DOCUMENT_CACHE_DIR = Path(os.getenv("DOCUMENT_CACHE_DIR", "/data/document-cache"))
DOCUMENT_CACHE_MAX_BYTES = int(
    os.getenv("DOCUMENT_CACHE_MAX_BYTES", str(5 * 1024 * 1024 * 1024))
)
EMBEDDING_BASE_URL = os.getenv(
    "EMBEDDING_BASE_URL",
    "https://dashscope.aliyuncs.com/compatible-mode/v1",
)
EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY", "")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-v4")
EMBEDDING_DIMENSIONS = int(os.getenv("EMBEDDING_DIMENSIONS", "1024"))
EMBEDDING_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "8"))
EMBEDDING_TIMEOUT_SECONDS = float(os.getenv("EMBEDDING_TIMEOUT_SECONDS", "60"))
DOCUMENT_INDEX_POLL_SECONDS = float(
    os.getenv("DOCUMENT_INDEX_POLL_SECONDS", "5")
)
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "6"))
RAG_MIN_SIMILARITY = float(os.getenv("RAG_MIN_SIMILARITY", "0.25"))
RAG_QUERY_MIN_SIMILARITY = float(
    os.getenv("RAG_QUERY_MIN_SIMILARITY", "0.45")
)
RAG_MAX_SCORE_DROP = float(os.getenv("RAG_MAX_SCORE_DROP", "0.12"))
RAG_CHUNK_SIZE = int(os.getenv("RAG_CHUNK_SIZE", "700"))
RAG_CHUNK_OVERLAP = int(os.getenv("RAG_CHUNK_OVERLAP", "100"))
