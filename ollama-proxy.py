#!/usr/bin/env python3
"""
Ollama → llama.cpp proxy
Listens on the Ollama port so A-EYE (and anything else expecting Ollama)
can use a llama.cpp server transparently.
"""
import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

LLAMA_URL = "http://10.0.1.103:8080"
LISTEN_PORT = 11434

# Model name reported back to clients (whatever A-EYE has configured)
FAKE_MODEL = "gemma4:e4b"

app = FastAPI()


# ── Health / discovery ────────────────────────────────────────────────────────

@app.get("/")
@app.head("/")
async def root():
    return {"status": "ok"}

@app.get("/api/version")
async def version():
    return {"version": "0.1.0-proxy"}

@app.get("/api/tags")
async def list_tags():
    """Return a fake model list so A-EYE thinks Ollama is healthy."""
    return {
        "models": [{
            "name": FAKE_MODEL,
            "model": FAKE_MODEL,
            "modified_at": "2025-01-01T00:00:00Z",
            "size": 0,
            "digest": "llama-cpp-proxy",
            "details": {"family": "proxy", "parameter_size": "35B", "quantization_level": "Q8"},
        }]
    }

@app.get("/api/status")
@app.get("/api/ps")
async def status():
    return {"models": [{"name": FAKE_MODEL, "size": 0}]}

@app.post("/api/show")
async def show(request: Request):
    return {"name": FAKE_MODEL, "details": {"family": "proxy"}}


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
    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post(f"{LLAMA_URL}/v1/chat/completions", json=openai_body)
        resp.raise_for_status()
        return resp.json()


# ── Generation endpoints ──────────────────────────────────────────────────────

@app.post("/api/generate")
async def generate(request: Request):
    body = await request.json()
    stream = body.get("stream", False)
    options = body.get("options", {})

    messages = _build_openai_messages(body.get("prompt", ""), body.get("images", []))
    openai_body = {
        "model": FAKE_MODEL,
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
                            import json
                            chunk = json.loads(line[6:])
                            delta = chunk["choices"][0].get("delta", {})
                            token = delta.get("content", "")
                            done = chunk["choices"][0].get("finish_reason") is not None
                            import json as _json
                            yield _json.dumps({"response": token, "done": done}) + "\n"
        return StreamingResponse(streamer(), media_type="application/x-ndjson")

    result = await _call_llama(openai_body)
    content = result["choices"][0]["message"]["content"]
    return {
        "model": body.get("model", FAKE_MODEL),
        "response": content,
        "done": True,
        "done_reason": "stop",
    }


@app.post("/api/chat")
async def chat(request: Request):
    body = await request.json()
    stream = body.get("stream", False)
    options = body.get("options", {})

    messages = _translate_chat_messages(body.get("messages", []))
    openai_body = {
        "model": FAKE_MODEL,
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
                            import json
                            chunk = json.loads(line[6:])
                            delta = chunk["choices"][0].get("delta", {})
                            token = delta.get("content", "")
                            done = chunk["choices"][0].get("finish_reason") is not None
                            import json as _json
                            yield _json.dumps({
                                "message": {"role": "assistant", "content": token},
                                "done": done,
                            }) + "\n"
        return StreamingResponse(streamer(), media_type="application/x-ndjson")

    result = await _call_llama(openai_body)
    content = result["choices"][0]["message"]["content"]
    return {
        "model": body.get("model", FAKE_MODEL),
        "message": {"role": "assistant", "content": content},
        "done": True,
        "done_reason": "stop",
    }


if __name__ == "__main__":
    print(f"Ollama→llama.cpp proxy — listening on :{LISTEN_PORT}")
    print(f"Forwarding to: {LLAMA_URL}")
    uvicorn.run(app, host="0.0.0.0", port=LISTEN_PORT)
