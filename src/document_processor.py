import os
import shutil
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_ollama import OllamaEmbeddings
from src.config import CHROMA_DB_PATH, EMBEDDING_MODEL, OLLAMA_BASE_URL

def get_embeddings():
    """Returns the configured embeddings model."""
    return OllamaEmbeddings(
        model=EMBEDDING_MODEL,
        base_url=OLLAMA_BASE_URL
    )

def get_db() -> Chroma:
    """Open and return the persistent ChromaDB vector store."""
    return Chroma(persist_directory=CHROMA_DB_PATH, embedding_function=get_embeddings())

def process_pdf(file_path: str):
    """Load, chunk, and index a PDF into the ChromaDB vector store."""
    if os.path.exists(CHROMA_DB_PATH):
        shutil.rmtree(CHROMA_DB_PATH)

    loader = PyPDFLoader(file_path)
    docs = loader.load()

    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    chunks = splitter.split_documents(docs)

    Chroma.from_documents(chunks, get_embeddings(), persist_directory=CHROMA_DB_PATH)
    return len(chunks), len(docs)

def clear_database():
    """Delete the current ChromaDB vector store."""
    if os.path.exists(CHROMA_DB_PATH):
        shutil.rmtree(CHROMA_DB_PATH)
