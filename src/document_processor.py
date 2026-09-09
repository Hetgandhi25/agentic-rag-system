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
    return OllamaEmbeddings(
        model=EMBEDDING_MODEL,
        base_url=OLLAMA_BASE_URL
    )

def get_db() -> InMemoryVectorStore:
    """Return the active in-memory vector store."""
    global _vectorstore
    if _vectorstore is None:
        _vectorstore = InMemoryVectorStore(embedding=get_embeddings())
    return _vectorstore

def process_pdf(file_path: str):
    """Load, chunk, and index a PDF into the in-memory vector store."""
    global _vectorstore

    loader = PyPDFLoader(file_path)
    docs = loader.load()

    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    chunks = splitter.split_documents(docs)

    _vectorstore = InMemoryVectorStore.from_documents(
        documents=chunks,
        embedding=get_embeddings()
    )
    return len(chunks), len(docs)

def clear_database():
    """Clear the in-memory vector store."""
    global _vectorstore
    _vectorstore = None
