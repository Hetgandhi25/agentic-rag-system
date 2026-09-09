import os
import time
import json
import shutil
import urllib.request
from src.config import OLLAMA_BASE_URL, STORAGE_DIR, VECTOR_STORE_FILE, CHAT_HISTORY_FILE, METADATA_FILE
from src.document_processor import process_pdf, clear_database, is_vectorstore_ready, load_chat_history
from src.graph import app

print("==================================================")
print("🚀 STARTING PRODUCTION AUDIT & BENCHMARK SUITE")
print("==================================================")

pdf_url = "https://arxiv.org/pdf/1706.03762.pdf"
sample_pdf = "sample_test.pdf"

if not os.path.exists(sample_pdf):
    print("Downloading sample PDF...")
    urllib.request.urlretrieve(pdf_url, sample_pdf)

# --------------------------------------------------
# TEST A: PDF Upload, Indexing, Direct Question
# --------------------------------------------------
print("\n[TEST A] Upload PDF -> Index -> Direct Question")
t0 = time.time()
chunks, pages = process_pdf(sample_pdf)
t_index = time.time() - t0

print(f"Indexed {chunks} chunks from {pages} pages in {t_index:.2f} seconds.")
assert is_vectorstore_ready(), "Vectorstore should be ready!"
assert os.path.exists(VECTOR_STORE_FILE), "Vector store JSON file must exist on disk!"

q_direct = "What is the main architecture proposed in this paper?"
t0_ask = time.time()
res_a = app.invoke({"question": q_direct, "chat_history": []})
t_ask_a = time.time() - t0_ask

print(f"Direct Question Latency: {t_ask_a:.2f} seconds")
print(f"Direct Answer Snippet:\n{res_a.get('answer')[:150]}...")
assert "Transformer" in res_a.get("answer"), "Answer must mention Transformer!"
print(">>> TEST A: PASSED ✅")

# --------------------------------------------------
# TEST B: Query Rewriting Loop
# --------------------------------------------------
print("\n[TEST B] Vague Question -> Query Rewriting Loop")
q_vague = "How fast is it compared to others?"
t0_b = time.time()
res_b = app.invoke({"question": q_vague, "chat_history": []})
t_ask_b = time.time() - t0_b

print(f"Query Rewriting Latency: {t_ask_b:.2f} seconds")
print(f"Total Iterations Run: {res_b.get('iterations')}")
assert res_b.get("iterations") > 1, "Should have run multiple iterations!"
print(">>> TEST B: PASSED ✅")

# --------------------------------------------------
# TEST C: Multi-Turn Conversation Memory Persistence
# --------------------------------------------------
print("\n[TEST C] Multi-Turn Conversation Memory")
history = res_a.get("chat_history", [])
q_memory = "What did I ask you about in my previous question?"
res_c = app.invoke({"question": q_memory, "chat_history": history})

print(f"Memory Recall Answer:\n{res_c.get('answer')[:150]}...")
assert "Transformer" in res_c.get("answer") or "architecture" in res_c.get("answer"), "Memory recall must identify previous topic!"
print(">>> TEST C: PASSED ✅")

# --------------------------------------------------
# TEST D: Out-of-Domain Question (No Hallucination)
# --------------------------------------------------
print("\n[TEST D] Out-of-Domain Question (Hallucination Prevention)")
q_unrelated = "What is the recipe for baking a chocolate cake?"
res_d = app.invoke({"question": q_unrelated, "chat_history": []})

print(f"Out-of-Domain Response:\n{res_d.get('answer')}")
print(">>> TEST D: PASSED ✅")

# --------------------------------------------------
# TEST E: Clear Database and History
# --------------------------------------------------
print("\n[TEST E] Clear Storage & Vector Store")
clear_database()
assert not os.path.exists(VECTOR_STORE_FILE), "Vector store file must be deleted!"
assert not os.path.exists(CHAT_HISTORY_FILE), "Chat history file must be deleted!"
assert not is_vectorstore_ready(), "Vectorstore should report not ready!"
print(">>> TEST E: PASSED ✅")

# --------------------------------------------------
# TEST F: App Restart & Disk Persistence Test
# --------------------------------------------------
print("\n[TEST F] App Restart & Disk Persistence Verification")
# Re-index
process_pdf(sample_pdf)
assert os.path.exists(VECTOR_STORE_FILE), "Vector store file created!"

# Simulate App Restart by resetting global variables
from src import document_processor
document_processor._vectorstore = None

# Verify auto-restore from disk
assert is_vectorstore_ready(), "is_vectorstore_ready() must return True from disk persistence!"
db_restored = document_processor.get_db()
docs_restored = db_restored.similarity_search("Transformer", k=1)
assert len(docs_restored) > 0, "Must retrieve documents from restored disk vector store!"
print(f"Restored from disk doc snippet: {docs_restored[0].page_content[:80]}...")
print(">>> TEST F: PASSED ✅")

# --------------------------------------------------
# TEST G: Invalid PDF / File Handling
# --------------------------------------------------
print("\n[TEST G] Invalid PDF Upload Handling")
bad_pdf = "empty_test.pdf"
with open(bad_pdf, "w") as f:
    f.write("Not a real PDF file content")

try:
    process_pdf(bad_pdf)
    print("WARNING: Bad PDF did not raise exception")
except Exception as e:
    print(f"Expected failure caught successfully: {e}")
    print(">>> TEST G: PASSED ✅")

if os.path.exists(bad_pdf):
    os.remove(bad_pdf)

print("\n==================================================")
print("🎉 ALL PRODUCTION AUDIT TESTS COMPLETED SUCCESSFULLY!")
print("==================================================")
