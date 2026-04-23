import asyncio
import json
import httpx

from config import settings

SYSTEM_PROMPT = """You are an image analysis assistant. Analyze the provided image and return a JSON object with:
1. "description": A 1-2 sentence description of what's in the image.
2. "tags": An array of 3-8 descriptive tags (lowercase single words or short phrases).
3. "category": One category from this list: Selfie, Portrait, Group Photo, Family, Friends, Baby & Kids, Couple, Wedding, Party & Celebration, Birthday, Holiday & Festival, Graduation, Funeral & Memorial, Reunion, Landscape, Cityscape, Travel, Beach & Ocean, Mountains, Sunset & Sunrise, Architecture, Indoor, Outdoor, Nature, Wildlife, Plants & Flowers, Sky & Clouds, Water & Lakes, Forest & Parks, Pets & Animals, Food & Drink, Coffee & Cafe, Restaurant & Dining, Cooking & Recipes, Sports & Fitness, Gym & Workout, Gaming, Music & Concerts, Movies & TV, Art & Creativity, Fashion & Style, Shopping, Home & Garden, DIY & Crafts, Cars & Vehicles, Motorbikes, Boats & Marine, Aviation, Technology & Gadgets, Work & Office, Education & Study, Documents & Text, Screenshots & UI, Maps & Directions, Receipts & Finance, Medical & Health, Construction & Industry, Night Life, Funny & Memes, Other.
4. "tag_confidences": An object mapping each tag to a confidence score between 0.0 and 1.0.
5. "category_confidence": A confidence score between 0.0 and 1.0 for the category.
6. "album": A short descriptive album/group name for this image (e.g. "Beach Vacation 2022", "Family Dinner", "Work Documents", "Pet Photos", "City Walk"). Group similar scenes, events, or subjects under the same album name. Keep it concise (2-4 words).
7. "faces": An array of objects for each person/face visible in the image. Each object should have:
   - "description": Brief description of the person (e.g. "man with glasses and brown hair", "young woman in red shirt", "child smiling")
   - "estimated_age": Estimated age range (e.g. "20-30", "5-10", "40-50")
   - "gender": Apparent gender ("male", "female", "unknown")
   - "position": Where in the image ("left", "center", "right", "background")
   If no faces are visible, return an empty array.
8. "sentiment": The overall mood/sentiment of the image. One of: "happy", "sad", "neutral", "excited", "peaceful", "dramatic", "funny", "romantic", "nostalgic", "tense", "lonely", "energetic".
9. "sentiment_score": A score from -1.0 (very negative) to 1.0 (very positive) representing the emotional tone.
10. "nsfw": A boolean. Set to true if the image contains explicit nudity, sexual content, pornographic material, or highly suggestive content. Lingerie, swimwear at a beach, breastfeeding, or artistic nudity should be false. Only flag clearly sexual or pornographic content as true.
11. "nsfw_confidence": A confidence score between 0.0 and 1.0 for the NSFW classification.

Return ONLY valid JSON, no markdown, no explanation."""

TIMEOUT = httpx.Timeout(120.0, connect=10.0)


def _using_ollama() -> bool:
    """Return True if Ollama is configured as the AI backend."""
    return bool(settings.OLLAMA_URL)


async def analyze_image(image_base64: str) -> dict | None:
    """
    Send an image to the configured vision model for analysis.
    Uses Ollama if OLLAMA_URL is set, otherwise LM Studio / llama.cpp.
    Returns parsed analysis dict or None on failure.
    """
    if _using_ollama():
        return await _analyze_ollama(image_base64)
    return await _analyze_lmstudio(image_base64)


async def _analyze_lmstudio(image_base64: str) -> dict | None:
    """Send image to Gemma 4 via LM Studio's OpenAI-compatible API."""
    url = f"{settings.LLAMA_CPP_URL}/v1/chat/completions"

    payload = {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}},
                    {"type": "text", "text": "Analyze this image and return JSON."},
                ],
            },
        ],
        "temperature": 0.3,
        "max_tokens": 4096,
    }

    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                response = await client.post(url, json=payload)

            if response.status_code >= 500:
                raise AIServerDownError(
                    f"LM Studio returned {response.status_code} — model likely crashed"
                )
            response.raise_for_status()

            data = response.json()
            message = data["choices"][0]["message"]
            content = message.get("content") or ""
            # Gemma 4 is a thinking model — JSON may be in reasoning_content
            reasoning = message.get("reasoning_content") or ""

            result = _parse_json_response(content) or _parse_json_response(reasoning)
            if result:
                return result

            print(f"[AI] Could not parse LM Studio response (attempt {attempt + 1}): {(content or reasoning)[:200]}")

        except AIServerDownError:
            raise
        except httpx.TimeoutException:
            print(f"[AI] LM Studio timeout on attempt {attempt + 1}")
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.RemoteProtocolError) as e:
            print(f"[AI] LM Studio unreachable on attempt {attempt + 1}: {e}")
            raise AIServerDownError(f"LM Studio unreachable: {e}") from e
        except Exception as e:
            print(f"[AI] LM Studio error on attempt {attempt + 1}: {e}")

    return None


async def _analyze_ollama(image_base64: str) -> dict | None:
    """Send image to a vision model via Ollama's OpenAI-compatible API."""
    # Ollama supports the OpenAI /v1/chat/completions endpoint
    url = f"{settings.OLLAMA_URL.rstrip('/')}/v1/chat/completions"
    model = settings.OLLAMA_MODEL

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}},
                    {"type": "text", "text": "Analyze this image and return JSON."},
                ],
            },
        ],
        "temperature": 0.3,
        "max_tokens": 4096,
        "stream": False,
    }

    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                response = await client.post(url, json=payload)

            if response.status_code >= 500:
                raise AIServerDownError(
                    f"Ollama returned {response.status_code} — model may have crashed"
                )
            response.raise_for_status()

            data = response.json()
            content = data["choices"][0]["message"].get("content") or ""

            result = _parse_json_response(content)
            if result:
                return result

            print(f"[AI] Could not parse Ollama response (attempt {attempt + 1}): {content[:200]}")

        except AIServerDownError:
            raise
        except httpx.TimeoutException:
            print(f"[AI] Ollama timeout on attempt {attempt + 1}")
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.RemoteProtocolError) as e:
            print(f"[AI] Ollama unreachable on attempt {attempt + 1}: {e}")
            raise AIServerDownError(f"Ollama unreachable: {e}") from e
        except Exception as e:
            print(f"[AI] Ollama error on attempt {attempt + 1}: {e}")

    return None


class AIServerDownError(Exception):
    """Raised when the AI server (LM Studio) is unreachable or the model has crashed."""
    pass


async def wait_for_lm_studio(timeout: float = 120.0, poll_interval: float = 3.0):
    """Poll the AI backend until it is ready, or timeout is reached."""
    if _using_ollama():
        return await _wait_for_ollama(timeout, poll_interval)

    url = f"{settings.LLAMA_CPP_URL}/v1/models"
    deadline = asyncio.get_event_loop().time() + timeout
    print("[AI] Waiting for LM Studio model to be loaded...")
    while asyncio.get_event_loop().time() < deadline:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
                r = await client.get(url)
                if r.status_code == 200:
                    models = r.json().get("data", [])
                    if models:
                        print(f"[AI] LM Studio ready with model: {models[0]['id']}")
                        return True
        except Exception:
            pass
        await asyncio.sleep(poll_interval)
    print("[AI] LM Studio did not load a model in time.")
    return False


async def _wait_for_ollama(timeout: float = 120.0, poll_interval: float = 3.0):
    """Poll Ollama until the configured model is available."""
    url = f"{settings.OLLAMA_URL.rstrip('/')}/api/tags"
    model = settings.OLLAMA_MODEL
    deadline = asyncio.get_event_loop().time() + timeout
    print(f"[AI] Waiting for Ollama model '{model}'...")
    while asyncio.get_event_loop().time() < deadline:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
                r = await client.get(url)
                if r.status_code == 200:
                    available = [m["name"] for m in r.json().get("models", [])]
                    # Match by prefix so "gemma3:12b" matches "gemma3:12b-instruct-q4_K_M" etc.
                    if any(m.startswith(model.split(":")[0]) for m in available):
                        print(f"[AI] Ollama ready. Available models: {available}")
                        return True
        except Exception:
            pass
        await asyncio.sleep(poll_interval)
    print(f"[AI] Ollama model '{model}' not available in time.")
    return False


def _parse_json_response(content: str) -> dict | None:
    """Try to extract a JSON object from the AI response."""
    # Try direct parse
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # Try to find JSON in markdown code block
    import re
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Try to find any JSON object
    match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", content, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    return None
