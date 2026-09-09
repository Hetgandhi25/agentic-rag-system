import os
import json
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_ollama import OllamaEmbeddings
from src.config import (
    EMBEDDING_MODEL,
    OLLAMA_BASE_URL,
    STORAGE_DIR,
    VECTOR_STORE_FILE,
    CHAT_HISTORY_FILE,
    METADATA_FILE,
)

# Global vectorstore reference
_vectorstore = None

def get_embeddings():
    """Returns the configured embeddings model."""
    print(f"Initializing OllamaEmbeddings(model='{EMBEDDING_MODEL}', base_url='{OLLAMA_BASE_URL}')...", flush=True)
    return OllamaEmbeddings(
        model=EMBEDDING_MODEL,
        base_url=OLLAMA_BASE_URL
    )

def ensure_storage_dir():
    """Ensure persistent storage directory exists."""
    os.makedirs(STORAGE_DIR, exist_ok=True)

def load_persisted_vectorstore():
    """Load vectorstore from disk if it exists."""
    global _vectorstore
    if _vectorstore is not None:
        return _vectorstore

    ensure_storage_dir()
    if os.path.exists(VECTOR_STORE_FILE):
        try:
            print(f"[STORAGE] Loading persisted vectorstore from {VECTOR_STORE_FILE}...", flush=True)
            _vectorstore = InMemoryVectorStore.load(VECTOR_STORE_FILE, get_embeddings())
            print("[STORAGE] Successfully restored vectorstore from disk!", flush=True)
            return _vectorstore
        except Exception as e:
            print(f"[STORAGE] Failed to load vectorstore: {e}", flush=True)

    _vectorstore = InMemoryVectorStore(embedding=get_embeddings())
    return _vectorstore

def get_db() -> InMemoryVectorStore:
    """Return the active vector store, loading from disk if needed."""
    return load_persisted_vectorstore()

def process_pdf(file_path: str):
    """Load, chunk, index PDF, and persist vectorstore + metadata to disk."""
    global _vectorstore
    ensure_storage_dir()
    print(f"\n==========================================", flush=True)
    print(f"[PDF PROCESSOR] Ingesting document: {file_path}", flush=True)
    print(f"==========================================", flush=True)

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    print("Step 1: Loading PDF with PyPDFLoader...", flush=True)
    loader = PyPDFLoader(file_path)
    docs = loader.load()
    if not docs:
        raise ValueError("The uploaded PDF is empty or contains no readable text.")
    print(f"Loaded {len(docs)} pages.", flush=True)

    print("Step 2: Splitting text into chunks...", flush=True)
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    chunks = splitter.split_documents(docs)
    print(f"Created {len(chunks)} chunks.", flush=True)

    print("Step 3: Generating embeddings & indexing into InMemoryVectorStore...", flush=True)
    embeddings = get_embeddings()
    _vectorstore = InMemoryVectorStore.from_documents(
        documents=chunks,
        embedding=embeddings
    )

    print("Step 4: Persisting vectorstore and metadata to disk...", flush=True)
    _vectorstore.dump(VECTOR_STORE_FILE)

    metadata = {
        "filename": os.path.basename(file_path),
        "num_pages": len(docs),
        "num_chunks": len(chunks)
    }
    with open(METADATA_FILE, "w") as f:
        json.dump(metadata, f, indent=2)

    # Clear old chat history for new document
    if os.path.exists(CHAT_HISTORY_FILE):
        try:
            os.remove(CHAT_HISTORY_FILE)
        except Exception:
            pass

    print("PDF Processing & Storage Persistence Complete!", flush=True)
    return len(chunks), len(docs)

def clear_database():
    """Clear in-memory and disk persistent storage."""
    global _vectorstore
    print("[PDF PROCESSOR] Clearing vectorstore and storage files.", flush=True)
    _vectorstore = None
    for fpath in [VECTOR_STORE_FILE, CHAT_HISTORY_FILE, METADATA_FILE]:
        if os.path.exists(fpath):
            try:
                os.remove(fpath)
            except Exception:
                pass

def is_vectorstore_ready() -> bool:
    """Dynamically check if vector store exists in RAM or on disk."""
    global _vectorstore
    if _vectorstore is not None:
        return True
    return os.path.exists(VECTOR_STORE_FILE)

def load_chat_history() -> list:
    """Load persistent chat history from disk."""
    if os.path.exists(CHAT_HISTORY_FILE):
        try:
            with open(CHAT_HISTORY_FILE, "r") as f:
                data = json.load(f)
                # Convert list of lists to list of tuples
                return [tuple(pair) for pair in data]
        except Exception:
            return []
    return []

def save_chat_history(history: list):
    """Save chat history to disk."""
    ensure_storage_dir()
    try:
        with open(CHAT_HISTORY_FILE, "w") as f:
            json.dump(history, f, indent=2)
    except Exception as e:
        print(f"[STORAGE] Failed to save chat history: {e}", flush=True)

def load_document_metadata() -> dict:
    """Load metadata of currently persisted document."""
    if os.path.exists(METADATA_FILE):
        try:
            with open(METADATA_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}
