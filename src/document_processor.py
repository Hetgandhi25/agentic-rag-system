import os
import shutil
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from sqlalchemy.orm import Session

from src.config import STORAGE_DIR
from src.database import SessionLocal
from src.models import Document

CHROMA_PERSIST_DIR = os.path.join(STORAGE_DIR, "chroma_db")

def ensure_storage_dir():
    """Ensure persistent storage directory exists."""
    os.makedirs(STORAGE_DIR, exist_ok=True)
    os.makedirs(CHROMA_PERSIST_DIR, exist_ok=True)

def get_vectorstore() -> Chroma:
    """Return the active Chroma vector store. Uses default all-MiniLM-L6-v2 ONNX embeddings for zero config."""
    ensure_storage_dir()
    return Chroma(
        collection_name="rag_documents",
        persist_directory=CHROMA_PERSIST_DIR,
        collection_metadata={"hnsw:space": "cosine"}
    )

def process_pdf(file_path: str, filename: str) -> dict:
    """Load, chunk, index PDF into Chroma, and save to SQLite."""
    ensure_storage_dir()
    print(f"\n==========================================", flush=True)
    print(f"[PDF PROCESSOR] Ingesting document: {filename}", flush=True)
    print(f"==========================================", flush=True)

    db: Session = SessionLocal()
    try:
        new_doc = Document(filename=filename)
        db.add(new_doc)
        db.commit()
        db.refresh(new_doc)
        
        # Save physical file path to delete later
        safe_name = os.path.basename(file_path)
        actual_file_path = os.path.join(STORAGE_DIR, safe_name)

        print("Step 1: Loading PDF with PyPDFLoader...", flush=True)
        loader = PyPDFLoader(file_path)
        docs = loader.load()
        num_pages = len(docs)
        print(f"Loaded {num_pages} pages.", flush=True)

        print("Step 2: Splitting text into chunks...", flush=True)
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
        )
        chunks = text_splitter.split_documents(docs)
        for chunk in chunks:
            chunk.metadata["document_id"] = new_doc.id
            chunk.metadata["filename"] = filename
            # Ensure page numbers are integers
            if "page" not in chunk.metadata or not isinstance(chunk.metadata["page"], int):
                chunk.metadata["page"] = 0

        num_chunks = len(chunks)
        print(f"Created {num_chunks} chunks.", flush=True)

        print("Step 3: Generating embeddings & indexing into ChromaDB...", flush=True)
        vectorstore = get_vectorstore()
        vectorstore.add_documents(chunks)

        # Update DB
        new_doc.num_pages = num_pages
        new_doc.num_chunks = num_chunks
        db.commit()

        print("PDF Processing & Storage Persistence Complete!", flush=True)
        return {
            "id": new_doc.id,
            "filename": filename,
            "num_pages": num_pages,
            "num_chunks": num_chunks
        }
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()

def delete_document(document_id: str):
    """Delete document from SQLite, its chunks from Chroma, and the physical PDF."""
    db: Session = SessionLocal()
    doc = db.query(Document).filter(Document.id == document_id).first()
    if doc:
        filename = doc.filename
        db.delete(doc)
        db.commit()
        
        # Delete the physical PDF file
        try:
            file_path = os.path.join(STORAGE_DIR, filename)
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"[STORAGE] Deleted physical file: {filename}", flush=True)
        except Exception as e:
            print(f"[STORAGE] Failed to delete physical file {filename}: {e}", flush=True)
            
        # Delete from Chroma using internal collection with where filter
        try:
            vectorstore = get_vectorstore()
            vectorstore._collection.delete(where={"document_id": document_id})
            print(f"[STORAGE] Deleted vectors for document {document_id}", flush=True)
        except Exception as e:
            print(f"[STORAGE] Warning: Could not delete vectors for doc {document_id}: {e}", flush=True)
    db.close()
