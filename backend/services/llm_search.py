"""
LLM-powered natural language search expansion.

Sends the user's query to the configured AI backend (LM Studio or Ollama)
as a text-only request to expand it into structured search terms.
Then runs a weighted relevance search across MariaDB.
"""

import asyncio
import json
import re

import httpx
from sqlalchemy.orm import Session

from config import settings

EXPAND_PROMPT = """You are a search query assistant for a personal photo library.
The user will give you a natural language search query.
Expand it into a JSON object with these fields:
- "keywords": array of 4-8 specific search terms (lowercase). Include synonyms and related concepts.
- "date_year": integer year if the query mentions a specific year, else null.
- "location": location name string if the query mentions a place, else null.

Examples:
- "beach vacation with kids" → {"keywords": ["beach", "ocean", "vacation", "kids", "children", "swimming", "sand", "holiday"], "date_year": null, "location": null}
- "christmas 2022" → {"keywords": ["christmas", "xmas", "holiday", "family", "gifts", "tree", "celebration"], "date_year": 2022, "location": null}
- "photos from Paris" → {"keywords": ["paris", "eiffel", "france", "travel", "city", "architecture"], "date_year": null, "location": "paris"}

Return ONLY valid JSON, nothing else."""

TIMEOUT = httpx.Timeout(30.0, connect=5.0)


async def expand_query(query: str) -> dict:
    """
    Use the local AI backend to expand a natural language query into structured search terms.
    Returns a dict with 'keywords', 'date_year', 'location'.
    """
    try:
        if settings.OLLAMA_URL:
            result = await _expand_ollama(query)
            if result:
                return result
    except Exception as e:
        print(f"[Search] LLM expansion failed: {e}")

    # Fallback: split query into keywords
    words = [w.strip().lower() for w in re.split(r"[\s,]+", query) if len(w.strip()) > 2]
    return {"keywords": words, "date_year": None, "location": None}


async def _expand_lmstudio(query: str) -> dict | None:
    url = f"{settings.LLAMA_CPP_URL}/v1/chat/completions"
    payload = {
        "messages": [
            {"role": "system", "content": EXPAND_PROMPT},
            {"role": "user", "content": query},
        ],
        "temperature": 0.2,
        "max_tokens": 256,
    }
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.post(url, json=payload)
        r.raise_for_status()
    content = r.json()["choices"][0]["message"].get("content", "")
    return _parse(content)


async def _expand_ollama(query: str) -> dict | None:
    url = f"{settings.OLLAMA_URL.rstrip('/')}/v1/chat/completions"
    payload = {
        "model": settings.OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": EXPAND_PROMPT},
            {"role": "user", "content": query},
        ],
        "temperature": 0.2,
        "max_tokens": 256,
        "stream": False,
    }
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.post(url, json=payload)
        r.raise_for_status()
    content = r.json()["choices"][0]["message"].get("content", "")
    return _parse(content)


def _parse(content: str) -> dict | None:
    """Extract JSON from the LLM response."""
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*?\}", content, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return None


def search_images_db(
    db: Session,
    query: str,
    expanded: dict,
    folder: str | None = None,
    tag: str | None = None,
    category: str | None = None,
    page: int = 1,
    page_size: int = 48,
    analyzed_only: bool = False,
    favorite: bool | None = None,
    is_video: bool = False,
) -> dict:
    """
    Search images in MariaDB using weighted keyword relevance across multiple columns.
    Returns {"ids": [...], "total": int, "scores": {id: score}}.
    """
    from sqlalchemy import text

    keywords = expanded.get("keywords") or []
    original_words = [w.strip().lower() for w in re.split(r"[\s,]+", query) if len(w.strip()) > 2]
    date_year = expanded.get("date_year")
    location_hint = (expanded.get("location") or "").lower().strip()

    if not keywords and not original_words:
        return {"ids": [], "total": 0, "scores": {}}

    # De-duplicate keywords preserving order; original query words get 2× weight
    seen = set()
    all_keywords = []
    for w in original_words:
        if w not in seen:
            seen.add(w)
            all_keywords.append((w, 2.0))
    for w in keywords:
        if w not in seen:
            seen.add(w)
            all_keywords.append((w, 1.0))

    # Build a raw SQL relevance query against the images table + joined tags
    # For each keyword we add a weighted LIKE match across columns:
    #   ai_description, filename, album, location_name → weight 1×
    #   tag name → weight 1.5×
    # Original query words get an extra multiplier.

    select_parts = ["i.id"]
    score_expr_parts = []

    params: dict = {}

    for idx, (kw, multiplier) in enumerate(all_keywords):
        p = f"kw{idx}"
        params[p] = f"%{kw}%"
        col_score = (
            f"(CASE WHEN i.ai_description LIKE :{p} THEN 1 ELSE 0 END"
            f" + CASE WHEN i.filename LIKE :{p} THEN 0.5 ELSE 0 END"
            f" + CASE WHEN i.album LIKE :{p} THEN 0.8 ELSE 0 END"
            f" + CASE WHEN i.location_name LIKE :{p} THEN 1.2 ELSE 0 END)"
        )
        score_expr_parts.append(f"({col_score}) * {multiplier}")

    # Tag join score
    for idx, (kw, multiplier) in enumerate(all_keywords):
        p = f"kw{idx}"
        score_expr_parts.append(
            f"(CASE WHEN EXISTS (SELECT 1 FROM image_tags it JOIN tags t ON t.id=it.tag_id WHERE it.image_id=i.id AND t.name LIKE :{p}) THEN 1.5 ELSE 0 END) * {multiplier}"
        )

    # Year filter bonus
    if date_year:
        params["year"] = date_year
        score_expr_parts.append("(CASE WHEN YEAR(i.date_taken) = :year THEN 3 ELSE 0 END)")

    # Location hint bonus
    if location_hint:
        params["loc"] = f"%{location_hint}%"
        score_expr_parts.append("(CASE WHEN i.location_name LIKE :loc THEN 2 ELSE 0 END)")

    score_sql = " + ".join(score_expr_parts) if score_expr_parts else "0"

    # WHERE: at least one keyword must match somewhere
    where_parts = []
    for idx, (kw, _) in enumerate(all_keywords[:10]):  # cap at 10 for query safety
        p = f"kw{idx}"
        where_parts.append(
            f"(i.ai_description LIKE :{p} OR i.filename LIKE :{p} OR i.album LIKE :{p} OR i.location_name LIKE :{p}"
            f" OR EXISTS (SELECT 1 FROM image_tags it JOIN tags t ON t.id=it.tag_id WHERE it.image_id=i.id AND t.name LIKE :{p}))"
        )
    base_where = " OR ".join(where_parts) if where_parts else "1=1"

    # Optional filters
    extra_where = []
    if folder:
        params["folder"] = folder
        if "/" in folder:
            extra_where.append("i.file_path LIKE CONCAT(:folder, '/%')")
        else:
            extra_where.append("i.source_folder = :folder")
    if analyzed_only:
        extra_where.append("i.analyzed = 1")
    if favorite is not None:
        params["fav"] = 1 if favorite else 0
        extra_where.append("i.favorite = :fav")
    
    params["is_vid"] = 1 if is_video else 0
    extra_where.append("i.is_video = :is_vid")

    if tag:
        params["tag_filter"] = tag.lower()
        extra_where.append(
            "EXISTS (SELECT 1 FROM image_tags it JOIN tags t ON t.id=it.tag_id WHERE it.image_id=i.id AND t.name=:tag_filter)"
        )
    if category:
        params["cat_filter"] = category
        extra_where.append(
            "EXISTS (SELECT 1 FROM image_categories ic JOIN categories c ON c.id=ic.category_id WHERE ic.image_id=i.id AND c.name=:cat_filter)"
        )

    extra_sql = (" AND " + " AND ".join(extra_where)) if extra_where else ""

    full_where = f"({base_where}){extra_sql}"

    # Count query
    count_sql = text(f"SELECT COUNT(DISTINCT i.id) FROM images i WHERE {full_where}")
    total = db.execute(count_sql, params).scalar() or 0

    if total == 0:
        return {"ids": [], "total": 0, "scores": {}}

    # Scored query
    offset = (page - 1) * page_size
    params["limit"] = page_size
    params["offset"] = offset

    scored_sql = text(
        f"SELECT i.id, ({score_sql}) AS score "
        f"FROM images i "
        f"WHERE {full_where} "
        f"GROUP BY i.id "
        f"ORDER BY score DESC "
        f"LIMIT :limit OFFSET :offset"
    )
    rows = db.execute(scored_sql, params).fetchall()
    ids = [r[0] for r in rows]
    scores = {r[0]: float(r[1]) for r in rows}

    return {"ids": ids, "total": total, "scores": scores}
