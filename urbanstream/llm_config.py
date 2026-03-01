import os
from dotenv import load_dotenv

load_dotenv()


# Ollama connection
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_TINY_MODEL = os.getenv("OLLAMA_TINY_MODEL", "llama3.2:1b")
OLLAMA_MID_MODEL = os.getenv("OLLAMA_MID_MODEL", "llama3.2:3b")
OLLAMA_BIG_MODEL = os.getenv("OLLAMA_BIG_MODEL", "llama3:8b")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

# Performance
_keep_alive_raw = os.getenv("OLLAMA_KEEP_ALIVE", "-1")
try:
    OLLAMA_KEEP_ALIVE = int(_keep_alive_raw)  # -1 = never unload
except ValueError:
    OLLAMA_KEEP_ALIVE = _keep_alive_raw  # allow duration strings like "5m"
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "1024"))  # context window size

# Smart filter
LLM_COOLDOWN_SECONDS = int(os.getenv("LLM_COOLDOWN_SECONDS", "30"))
LLM_RELEVANCE_THRESHOLD = float(os.getenv("LLM_RELEVANCE_THRESHOLD", "0.6"))
LLM_MAX_RESPONSE_TOKENS = int(os.getenv("LLM_MAX_RESPONSE_TOKENS", "150"))
LLM_CONTEXT_WINDOW = int(os.getenv("LLM_CONTEXT_WINDOW", "20"))

# RAG
CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "chroma_data")
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "5"))

# Moderation thresholds
MOD_ENABLED = os.getenv("MOD_ENABLED", "true").lower() in ("true", "1", "yes")
MOD_WARN_THRESHOLD = float(os.getenv("MOD_WARN_THRESHOLD", "0.6"))
MOD_JAIL_THRESHOLD = float(os.getenv("MOD_JAIL_THRESHOLD", "0.75"))
MOD_TIMEOUT_THRESHOLD = float(os.getenv("MOD_TIMEOUT_THRESHOLD", "0.85"))
MOD_TIMEOUT_DURATION = int(os.getenv("MOD_TIMEOUT_DURATION", "300"))

# Bot identity
BOT_NAME = os.getenv("BOT_NAME", "UrbanBot")
