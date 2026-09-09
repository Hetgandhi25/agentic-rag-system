import os
from dotenv import load_dotenv

load_dotenv()

# Configuration variables
CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "./chroma_db")
MAX_ITERATIONS = int(os.getenv("MAX_ITERATIONS", "3"))

# Ollama Models
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")

