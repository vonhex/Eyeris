#!/usr/bin/env python3
"""
Ollama → llama.cpp proxy
Listens on the Ollama port so A-EYE (and anything else expecting Ollama)
can use a llama.cpp server transparently.
"""
import os
import json
import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

LLAMA_URL = os.getenv("LLAMA_URL", "http://10.0.1.103:8080")
LISTEN_PORT = int(os.getenv("LISTEN_PORT", 11434))

# Active model name from llama.cpp
ACTUAL_MODEL = "gemma4:e4b"
REPORTED_MODEL = "llava:latest"

app = FastAPI()

async def sync_model():
    """Fetch currently loaded models from llama.cpp."""
    global ACTUAL_MODEL
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{LLAMA_URL}/v1/models")
            if resp.status_code == 200:
                data = resp.json()
                loaded = [m["id"] for m in data.get("data", [])]
                if loaded:
                    ACTUAL_MODEL = loaded[0]
                    print(f"[Proxy] Synced actual model name: {ACTUAL_MODEL}")
    except Exception as e:
        print(f"[Proxy] Warning: Could not sync model from llama.cpp: {e}")

@app.on_event("startup")
async def startup_event():
    await sync_model()


# ── Health / discovery ────────────────────────────────────────────────────────

@app.get("/")
@app.head("/")
async def root():
    return {"status": "ok"}

@app.get("/api/version")
async def version():
    return {"version": "0.3.14"}

@app.get("/api/tags")
async def list_tags():
    """Return models with vision families to satisfy filtering."""
    return {
        "models": [
            {
                "name": REPORTED_MODEL,
                "model": REPORTED_MODEL,
                "modified_at": "2025-01-01T00:00:00Z",
                "size": 0,
                "digest": "proxy-digest-vision",
                "details": {
                    "parent_model": "",
                    "format": "gguf",
                    "family": "llava",
                    "families": ["llava", "clip", "vision"],
                    "parameter_size": "35B",
                    "quantization_level": "Q4_K_M"
                },
            },
            {
                "name": ACTUAL_MODEL,
                "model": ACTUAL_MODEL,
                "modified_at": "2025-01-01T00:00:00Z",
                "size": 0,
                "digest": "proxy-digest-actual",
                "details": {
                    "parent_model": "",
                    "format": "gguf",
                    "family": "llava",
                    "families": ["llava", "clip", "vision"],
                    "parameter_size": "35B",
                    "quantization_level": "Q4_K_M"
                },
            }
        ]
    }

@app.get("/api/status")
@app.get("/api/ps")
async def status():
    return {"models": [{"name": REPORTED_MODEL, "size": 0}]}

@app.post("/api/show")
async def show(request: Request):
    body = await request.json()
    name = body.get("name", REPORTED_MODEL)
    return {
        "modelfile": f"FROM {name}\nTEMPLATE \"\"\"\n{{{{ .System }}}}\nUSER: {{{{ .Prompt }}}}\nASSISTANT: \"\"\"",
        "parameters": "stop                           \"<|end_of_text|>\"",
        "template": "{{ .System }}\nUSER: {{ .Prompt }}\nASSISTANT: ",
        "details": {
            "parent_model": "",
            "format": "gguf",
            "family": "llava",
            "families": ["llava", "clip", "vision"],
            "parameter_size": "35B",
            "quantization_level": "Q4_K_M"
        },
        "capabilities": ["completion", "vision"],
        "model_info": {
            "clip.has_clip_projector": True,
            "general.architecture": "llama",
            "general.name": name
        }
    }

@app.post("/api/pull")
async def pull(request: Request):
    """Fake pull endpoint that always returns success."""
    body = await request.json()
    model = body.get("name")
    print(f"[Proxy] Fake pulling {model}")
    
    async def streamer():
        yield json.dumps({"status": f"pulling {model}"}) + "\n"
        yield json.dumps({"status": "success"}) + "\n"
        
    return StreamingResponse(streamer(), media_type="application/x-ndjson")


# ── Translation helpers ───────────────────────────────────────────────────────

def _build_openai_messages(prompt: str, images: list[str]) -> list:
    if not images:
        return [{"role": "user", "content": prompt}]
    content = [{"type": "text", "text": prompt}]
    for img in images:
        url = img if img.startswith("data:") else f"data:image/jpeg;base64,{img}"
        content.append({"type": "image_url", "image_url": {"url": url}})
    return [{"role": "user", "content": content}]


def _translate_chat_messages(messages: list) -> list:
    """Convert Ollama chat messages (images as top-level list) to OpenAI format."""
    out = []
    for msg in messages:
        images = msg.get("images", [])
        text = msg.get("content", "")
        if images:
            content = [{"type": "text", "text": text}]
            for img in images:
                url = img if img.startswith("data:") else f"data:image/jpeg;base64,{img}"
                content.append({"type": "image_url", "image_url": {"url": url}})
            out.append({"role": msg["role"], "content": content})
        else:
            out.append({"role": msg["role"], "content": text})
    return out


async def _call_llama(openai_body: dict) -> dict:
    # Always use the ACTUAL_MODEL when talking to llama.cpp
    openai_body["model"] = ACTUAL_MODEL
    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post(f"{LLAMA_URL}/v1/chat/completions", json=openai_body)
        resp.raise_for_status()
        return resp.json()


# ── Generation endpoints ──────────────────────────────────────────────────────

@app.post("/api/generate")
async def generate(request: Request):
    body = await request.json()
    model = body.get("model", REPORTED_MODEL)
    stream = body.get("stream", False)
    options = body.get("options", {})

    messages = _build_openai_messages(body.get("prompt", ""), body.get("images", []))
    openai_body = {
        "model": ACTUAL_MODEL,
        "messages": messages,
        "stream": stream,
        "temperature": options.get("temperature", 0.7),
    }

    if stream:
        async def streamer():
            async with httpx.AsyncClient(timeout=300) as client:
                async with client.stream("POST", f"{LLAMA_URL}/v1/chat/completions",
                                         json=openai_body) as resp:
                    async for line in resp.aiter_lines():
                        if line.startswith("data: ") and line != "data: [DONE]":
                            try:
                                chunk = json.loads(line[6:])
                                delta = chunk["choices"][0].get("delta", {})
                                token = delta.get("content", "")
                                done = chunk["choices"][0].get("finish_reason") is not None
                                yield json.dumps({"model": model, "response": token, "done": done}) + "\n"
                            except Exception:
                                continue
        return StreamingResponse(streamer(), media_type="application/x-ndjson")

    result = await _call_llama(openai_body)
    content = result["choices"][0]["message"]["content"]
    return {
        "model": model,
        "response": content,
        "done": True,
        "done_reason": "stop",
    }


@app.post("/api/chat")
async def chat(request: Request):
    body = await request.json()
    model = body.get("model", REPORTED_MODEL)
    stream = body.get("stream", False)
    options = body.get("options", {})

    messages = _translate_chat_messages(body.get("messages", []))
    openai_body = {
        "model": ACTUAL_MODEL,
        "messages": messages,
        "stream": stream,
        "temperature": options.get("temperature", 0.7),
    }

    if stream:
        async def streamer():
            async with httpx.AsyncClient(timeout=300) as client:
                async with client.stream("POST", f"{LLAMA_URL}/v1/chat/completions",
                                         json=openai_body) as resp:
                    async for line in resp.aiter_lines():
                        if line.startswith("data: ") and line != "data: [DONE]":
                            try:
                                chunk = json.loads(line[6:])
                                delta = chunk["choices"][0].get("delta", {})
                                token = delta.get("content", "")
                                done = chunk["choices"][0].get("finish_reason") is not None
                                yield json.dumps({
                                    "model": model,
                                    "message": {"role": "assistant", "content": token},
                                    "done": done,
                                }) + "\n"
                            except Exception:
                                continue
        return StreamingResponse(streamer(), media_type="application/x-ndjson")

    result = await _call_llama(openai_body)
    content = result["choices"][0]["message"]["content"]
    return {
        "model": model,
        "message": {"role": "assistant", "content": content},
        "done": True,
        "done_reason": "stop",
    }


if __name__ == "__main__":
    print(f"Ollama→llama.cpp proxy — listening on :{LISTEN_PORT}")
    print(f"Forwarding to: {LLAMA_URL}")
    uvicorn.run(app, host="0.0.0.0", port=LISTEN_PORT)
