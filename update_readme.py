import re

with open('README.md', 'r') as f:
    content = f.read()

content = content.replace('Gemini 1.5 Pro', 'Local Ollama (qwen3:8b)')
content = content.replace('text-embedding-004', 'nomic-embed-text (Ollama)')
content = content.replace('yourusername', 'Hetgandhi25')

env_text_old = '''## Environment Variables
Create a \.env\ file in the root directory (use \.env.example\ as a template) and add your Google Gemini API Key:

\\\env
GEMINI_API_KEY=your_gemini_api_key_here
MAX_ITERATIONS=3
\\\'''

env_text_new = '''## Environment Variables
Create a \.env\ file in the root directory (use \.env.example\ as a template) and configure your local Ollama endpoints:

\\\env
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3:8b
EMBEDDING_MODEL=nomic-embed-text
MAX_ITERATIONS=3
\\\'''

content = content.replace(env_text_old, env_text_new)

with open('README.md', 'w') as f:
    f.write(content)
