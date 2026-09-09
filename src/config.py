import os
from dotenv import load_dotenv

load_dotenv()

# Configuration variables
CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "./chroma_db")
MAX_ITERATIONS = int(os.getenv("MAX_ITERATIONS", "3"))

# LLM Models
LLM_MODEL = "gemini-1.5-pro"
EMBEDDING_MODEL = "models/text-embedding-004" # Updated from deprecated gemini-embedding-001

# Verify API key is present
def get_api_key():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set in your environment or .env file!")
    return api_key
