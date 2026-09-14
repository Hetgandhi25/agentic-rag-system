# Integrating Model Pai with the Existing Ollama Project

This guide describes how to add the remote Model Pai/Qwen endpoint alongside the current Ollama integration. It does not require changing or deleting the Ollama path immediately.

## Endpoint and authentication

The remote model server is OpenAI-compatible:

```text
Base URL: http://192.168.100.10:8000/v1
Model: qwen3.8-27b
Authentication: Model Pai/OpenAI-compatible API key
```

Do not use a vLLM-specific key. The key is sent as an OpenAI-compatible bearer token.

## New standalone example

The companion file `model_pai_client.py` can be tested independently from the current application:

```powershell
$env:MODEL_PAI_API_KEY = "your-model-pai-key"
python .\model_pai_client.py "Explain retrieval augmented generation in one sentence."
```

Optional settings:

```powershell
$env:MODEL_PAI_MODEL = "qwen3.8-27b"
$env:MODEL_PAI_BASE_URL = "http://192.168.100.10:8000/v1"
python .\model_pai_client.py --think "Explain how vector search works."
```

The project virtual environment must have the OpenAI Python package installed:

```powershell
.\venv\Scripts\python.exe -m pip install openai
```

## Recommended integration points

Use the following existing files as integration points. Keep the existing Ollama implementation intact until the new provider has been tested.

### 1. `src/config.py`

Add provider settings using the project's existing configuration style:

```python
MODEL_PAI_BASE_URL = os.getenv(
    "MODEL_PAI_BASE_URL",
    "http://192.168.100.10:8000/v1",
)
MODEL_PAI_API_KEY = os.getenv("MODEL_PAI_API_KEY") or os.getenv("DEFAULT_API_KEY")
MODEL_PAI_MODEL = os.getenv("MODEL_PAI_MODEL", "qwen3.8-27b")
```

Do not hard-code the API key. Add the key to the local environment or `.env` file, and keep that file out of version control.

### 2. `src/nodes.py` or the module that currently calls Ollama

Create one OpenAI client at application startup or behind a small provider function:

```python
from openai import OpenAI

model_pai_client = OpenAI(
    base_url=MODEL_PAI_BASE_URL,
    api_key=MODEL_PAI_API_KEY,
)
```

Replace only the Ollama call in the selected execution path with:

```python
response = model_pai_client.chat.completions.create(
    model=MODEL_PAI_MODEL,
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ],
    temperature=0.7,
    top_p=0.8,
    max_tokens=1024,
    extra_body={
        "top_k": 20,
        "chat_template_kwargs": {"enable_thinking": False},
    },
)
answer = response.choices[0].message.content or ""
```

Adapt `system_prompt`, `user_prompt`, and the output assignment to the existing node's state shape. Preserve the current retrieval and document-processing logic; only the generation provider should change.

### 3. `src/api.py` or the provider-selection layer

If the application exposes a provider setting, add a provider value such as `model_pai` and route it to the new OpenAI client. Keep `ollama` as the default until validation is complete.

A useful provider selection shape is:

```python
if provider == "ollama":
    return call_ollama(messages)
if provider == "model_pai":
    return call_model_pai(messages)
raise ValueError(f"Unsupported provider: {provider}")
```

Use the project's existing error handling and response schema so the UI does not need provider-specific response parsing.

### 4. `requirements.txt`

Add this dependency if it is not already present:

```text
openai
```

Install dependencies into the same virtual environment used to run the application:

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Environment configuration

Add the following values to the local environment used by the application:

```text
MODEL_PAI_BASE_URL=http://192.168.100.10:8000/v1
MODEL_PAI_MODEL=qwen3.8-27b
MODEL_PAI_API_KEY=your-model-pai-key
```

For PowerShell:

```powershell
$env:MODEL_PAI_BASE_URL = "http://192.168.100.10:8000/v1"
$env:MODEL_PAI_MODEL = "qwen3.8-27b"
$env:MODEL_PAI_API_KEY = "your-model-pai-key"
```

## Validation sequence

1. Test the standalone script first.
2. Confirm the remote server is reachable from the machine running the application.
3. Run one application request with the provider explicitly set to `model_pai`.
4. Confirm the returned text is assigned to the same state field used by Ollama.
5. Test a retrieval-grounded question and verify that retrieved context is still included.
6. Test an Ollama request to confirm the existing provider still works.
7. Only then consider making Model Pai the default provider.

## Common failures

- `401 Unauthorized`: the Model Pai key is missing, invalid, or not available in the process environment.
- `404 Not Found`: the base URL is wrong or missing `/v1`.
- `405 Method Not Allowed`: the request is being sent to the server root or another non-API route instead of `/v1/chat/completions`.
- Model not found: use the exact model identifier returned by the remote server's `/v1/models` endpoint.
- Empty answer: inspect `response.choices[0].message.content` and preserve the existing application's expected state field.
