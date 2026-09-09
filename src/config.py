import os
import urllib.request
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", os.path.join(BASE_DIR, "chroma_db"))
MAX_ITERATIONS = int(os.getenv("MAX_ITERATIONS", "3"))

def detect_ollama_url():
    """Detect working Ollama endpoint for local host or Docker container."""
    env_url = os.getenv("OLLAMA_BASE_URL")
    if env_url:
        return env_url

    candidates = [
        "http://localhost:11434",
        "http://192.168.100.16:11434",
        "http://172.17.0.1:11434",
        "http://host.docker.internal:11434"
    ]
    for url in candidates:
        try:
            req = urllib.request.urlopen(f"{url}/api/tags", timeout=1)
            if req.status == 200:
                print(f"[CONFIG] Ollama connected successfully at: {url}")
                return url
        except Exception:
            continue
    return "http://192.168.100.16:11434"

OLLAMA_BASE_URL = detect_ollama_url()
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")

