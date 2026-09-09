import os
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_ollama import OllamaEmbeddings
from src.config import EMBEDDING_MODEL, OLLAMA_BASE_URL

# Global vectorstore reference
_vectorstore = None

def get_embeddings():
    """Returns the configured embeddings model."""
    print(f"Initializing OllamaEmbeddings(model='{EMBEDDING_MODEL}', base_url='{OLLAMA_BASE_URL}')...")
    return OllamaEmbeddings(
        model=EMBEDDING_MODEL,
        base_url=OLLAMA_BASE_URL
    )

def get_db() -> InMemoryVectorStore:
    """Return the active in-memory vector store."""
    global _vectorstore
    if _vectorstore is None:
        print("Initializing empty InMemoryVectorStore...")
        _vectorstore = InMemoryVectorStore(embedding=get_embeddings())
    return _vectorstore

def process_pdf(file_path: str):
    """Load, chunk, and index a PDF into the in-memory vector store."""
    global _vectorstore
    print(f"\n==========================================")
    print(f"[PDF PROCESSOR] Starting processing for: {file_path}")
    print(f"Using Pure Python InMemoryVectorStore (No SQLite / No Disk DB)")
    print(f"==========================================")

    print("Step 1: Loading PDF with PyPDFLoader...")
    loader = PyPDFLoader(file_path)
    docs = loader.load()
    print(f"Loaded {len(docs)} pages.")

    print("Step 2: Splitting text into chunks...")
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    chunks = splitter.split_documents(docs)
    print(f"Created {len(chunks)} chunks.")

    print("Step 3: Generating embeddings & indexing into InMemoryVectorStore...")
    embeddings = get_embeddings()
    _vectorstore = InMemoryVectorStore.from_documents(
        documents=chunks,
        embedding=embeddings
    )
    print("PDF Processing Complete! Vectors stored in RAM.")
    return len(chunks), len(docs)

def clear_database():
    """Clear the in-memory vector store."""
    global _vectorstore
    print("[PDF PROCESSOR] Clearing in-memory vector store.", flush=True)
    _vectorstore = None

def is_vectorstore_ready() -> bool:
    """Dynamically check if vector store has been initialized with documents."""
    global _vectorstore
    return _vectorstore is not None
