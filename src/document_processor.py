import os
import chromadb
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_ollama import OllamaEmbeddings
from src.config import CHROMA_DB_PATH, EMBEDDING_MODEL, OLLAMA_BASE_URL

COLLECTION_NAME = "agentic_rag"

def get_embeddings():
    """Returns the configured embeddings model."""
    return OllamaEmbeddings(
        model=EMBEDDING_MODEL,
        base_url=OLLAMA_BASE_URL
    )

def get_client():
    """Returns a persistent ChromaDB client."""
    os.makedirs(CHROMA_DB_PATH, exist_ok=True)
    return chromadb.PersistentClient(path=CHROMA_DB_PATH)

def get_db() -> Chroma:
    """Open and return the persistent ChromaDB vector store."""
    client = get_client()
    return Chroma(
        client=client,
        collection_name=COLLECTION_NAME,
        embedding_function=get_embeddings()
    )

def process_pdf(file_path: str):
    """Load, chunk, and index a PDF into the ChromaDB vector store using collection management."""
    client = get_client()

    # Logically reset the collection via DB API instead of deleting files on disk
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass

    loader = PyPDFLoader(file_path)
    docs = loader.load()

    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    chunks = splitter.split_documents(docs)

    Chroma.from_documents(
        documents=chunks,
        embedding=get_embeddings(),
        client=client,
        collection_name=COLLECTION_NAME
    )
    return len(chunks), len(docs)

def clear_database():
    """Delete the current ChromaDB collection cleanly."""
    client = get_client()
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
