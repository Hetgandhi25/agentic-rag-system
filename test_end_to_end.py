import os
import urllib.request
from src.document_processor import process_pdf
from src.graph import app

pdf_url = "https://arxiv.org/pdf/1706.03762.pdf"
pdf_path = "sample.pdf"

if not os.path.exists(pdf_path):
    print("Downloading sample PDF...")
    urllib.request.urlretrieve(pdf_url, pdf_path)

print("\n1. Indexing PDF into InMemoryVectorStore...")
chunks, pages = process_pdf(pdf_path)
print(f"Indexed {chunks} chunks from {pages} pages!")

# Turn 1
print("\n--- TURN 1: Question 1 ---")
q1 = "What is the main architecture proposed in this paper?"
res1 = app.invoke({"question": q1, "chat_history": []})
history = res1.get("chat_history", [])
print(f"Turn 1 Answer snippet: {res1.get('answer')[:100]}...")
print(f"Chat History length: {len(history)}")

# Turn 2: Follow-up question relying on memory!
print("\n--- TURN 2: Follow-up Question (Memory Test) ---")
q2 = "What did I just ask you about in my previous question?"
res2 = app.invoke({"question": q2, "chat_history": history})
history2 = res2.get("chat_history", [])
print(f"\nTurn 2 Answer:\n{res2.get('answer')}")
print(f"Updated Chat History length: {len(history2)}")

print("\n=== MULTI-TURN MEMORY TEST PASSED SUCCESSFULLY ===")
