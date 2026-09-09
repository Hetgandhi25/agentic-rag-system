import os
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_ollama import OllamaEmbeddings
from src.config import EMBEDDING_MODEL, OLLAMA_BASE_URL

# Global in-memory vectorstore reference
_vectorstore = None

def get_embeddings():
    """Returns the configured embeddings model."""
    return OllamaEmbeddings(
        model=EMBEDDING_MODEL,
        base_url=OLLAMA_BASE_URL
    )

def get_db() -> Chroma:
    """Return the active in-memory ChromaDB vector store."""
    global _vectorstore
    if _vectorstore is None:
        _vectorstore = Chroma(embedding_function=get_embeddings())
    return _vectorstore

def process_pdf(file_path: str):
    """Load, chunk, and index a PDF into an in-memory ChromaDB vector store."""
    global _vectorstore

    loader = PyPDFLoader(file_path)
    docs = loader.load()

    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    chunks = splitter.split_documents(docs)

    _vectorstore = Chroma.from_documents(
        documents=chunks,
        embedding=get_embeddings()
    )
    return len(chunks), len(docs)

def clear_database():
    """Clear the in-memory vector store."""
    global _vectorstore
    _vectorstore = None
