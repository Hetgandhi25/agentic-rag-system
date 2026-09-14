import uvicorn
from src.api import app

if __name__ == "__main__":
    print("Starting FastAPI Backend...")
    uvicorn.run("src.api:app", host="0.0.0.0", port=8000, reload=False)
