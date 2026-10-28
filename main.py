import os
import asyncio
import json
import time
from typing import Literal

import httpx
from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from gemini_service import (
    build_evidence_sources,
    generate_grounded_answer,
    get_validated_citations,
    resolve_followup_question,
    stream_grounded_answer,
)
from routers.documents import router as documents_router

from pathlib import Path
from dotenv import load_dotenv

load_dotenv(
    dotenv_path=Path(__file__).resolve().parent / ".env",
    override=True,
)

SEARXNG_URL = os.getenv(
    "SEARXNG_URL",
    "http://127.0.0.1:8080",
).rstrip("/")

SUPPORTED_CATEGORIES = {"general", "news", "science", "it", "images"}
SUPPORTED_TIME_RANGES = {"all", "day", "week", "month", "year"}
CAPABILITIES_CACHE_TTL = 300
_capabilities_cache = None
_capabilities_cached_at = 0.0

app = FastAPI(
    title="AI Search Engine API",
    description="Search the web and generate AI-powered answers.",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(documents_router)


async def get_searxng_capabilities() -> dict:
    """Read enabled engines and categories from the configured SearXNG."""

    global _capabilities_cache, _capabilities_cached_at
    if (
        _capabilities_cache is not None
        and time.monotonic() - _capabilities_cached_at < CAPABILITIES_CACHE_TTL
    ):
        return _capabilities_cache

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{SEARXNG_URL}/config")
            response.raise_for_status()
            config = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(
            status_code=502,
            detail="Could not read the configured SearXNG capabilities.",
        ) from exc

    engines = {}
    for engine in config.get("engines", []):
        if not engine.get("enabled"):
            continue
        name = str(engine.get("name", "")).strip()
        shortcut = str(engine.get("shortcut", "")).strip()
        if name:
            engines[name.lower()] = {
                "name": name,
                "shortcut": shortcut or name,
                "time_range_support": bool(engine.get("time_range_support")),
            }
        if shortcut:
            engines[shortcut.lower()] = engines[name.lower()]

    _capabilities_cache = {
        "categories": set(config.get("categories", [])),
        "engines": engines,
    }
    _capabilities_cached_at = time.monotonic()
    return _capabilities_cache


async def resolve_filters(
    time_range: str,
    category: str | None,
    engine: str | None,
) -> tuple[dict, dict]:
    """Validate filters and return SearXNG params plus user-facing metadata."""

    normalized_time_range = time_range.lower()
    if normalized_time_range not in SUPPORTED_TIME_RANGES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unsupported time_range '{time_range}'. "
                "Use all, day, week, month, or year."
            ),
        )

    capabilities = await get_searxng_capabilities()
    params = {}
    metadata = {
        "time_range": normalized_time_range,
        "category": None,
        "engine": None,
        "warnings": [],
    }

    if category:
        normalized_category = category.lower()
        if normalized_category not in SUPPORTED_CATEGORIES:
            raise HTTPException(
                status_code=422,
                detail=f"Unsupported category '{category}'.",
            )
        if normalized_category not in capabilities["categories"]:
            raise HTTPException(
                status_code=422,
                detail=f"Category '{category}' is not enabled in SearXNG.",
            )
        params["categories"] = normalized_category
        metadata["category"] = normalized_category

    selected_engine = None
    if engine:
        selected_engine = capabilities["engines"].get(engine.lower())
        if selected_engine is None:
            raise HTTPException(
                status_code=422,
                detail=f"Search engine '{engine}' is not enabled in SearXNG.",
            )
        params["engines"] = selected_engine["shortcut"]
        metadata["engine"] = selected_engine["name"]

    if normalized_time_range != "all":
        params["time_range"] = normalized_time_range
        if selected_engine and not selected_engine["time_range_support"]:
            metadata["warnings"].append(
                f"Engine '{selected_engine['name']}' does not advertise "
                "time-range support; SearXNG may ignore this filter."
            )
        elif not selected_engine:
            metadata["warnings"].append(
                "Time range is passed to SearXNG, but engines without "
                "time-range support may ignore it."
            )

    return params, metadata


async def fetch_search_results(
    query: str,
    search_params: dict | None = None,
) -> list[dict]:
    """Fetch and normalize results from SearXNG."""

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{SEARXNG_URL}/search",
                params={
                    "q": query,
                    "format": "json",
                    **(search_params or {}),
                },
            )

            response.raise_for_status()
            data = response.json()

    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"SearXNG returned HTTP {exc.response.status_code}.",
        ) from exc

    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "Could not connect to SearXNG. "
                "Check that your SSH tunnel is running."
            ),
        ) from exc

    return [
        {
            "title": result.get("title", ""),
            "url": result.get("url", ""),
            "snippet": result.get("content", ""),
            "engine": result.get("engine", ""),
            "thumbnail_url": result.get("thumbnail_src")
            or result.get("thumbnail")
            or result.get("img_src"),
            "image_url": result.get("img_src"),
            "published_date": result.get("publishedDate")
            or result.get("published_date")
            or result.get("date"),
        }
        for result in data.get("results", [])
    ]


@app.get("/")
async def home():
    return {
        "message": "AI Search Engine API is running!"
    }


@app.get("/filters")
async def filters():
    """Return the validated filter options exposed by this SearXNG instance."""

    capabilities = await get_searxng_capabilities()
    engines = {
        id(engine): engine
        for engine in capabilities["engines"].values()
    }

    return {
        "time_ranges": sorted(SUPPORTED_TIME_RANGES, key=lambda value: (
            "all", "day", "week", "month", "year"
        ).index(value)),
        "categories": sorted(
            SUPPORTED_CATEGORIES.intersection(capabilities["categories"])
        ),
        "engines": sorted(
            [
                {
                    "name": engine["name"],
                    "shortcut": engine["shortcut"],
                    "time_range_support": engine["time_range_support"],
                }
                for engine in engines.values()
            ],
            key=lambda engine: engine["name"].lower(),
        ),
    }


@app.get("/search")
async def search(
    q: str = Query(
        ...,
        min_length=1,
        description="The search query",
    ),
    time_range: str = Query("all"),
    category: str | None = Query(None),
    engine: str | None = Query(None),
):
    search_params, filter_metadata = await resolve_filters(
        time_range, category, engine
    )
    results = await fetch_search_results(q, search_params)

    return {
        "query": q,
        "total_results": len(results),
        "results": results,
        "filters": filter_metadata,
    }


@app.get("/ask")
async def ask(
    q: str = Query(
        ...,
        min_length=1,
        description="The question to answer",
    ),
    time_range: str = Query("all"),
    category: str | None = Query(None),
    engine: str | None = Query(None),
):
    # First retrieve the relevant web search results.
    search_params, filter_metadata = await resolve_filters(
        time_range, category, engine
    )
    results = await fetch_search_results(q, search_params)

    # Then ask Gemini to synthesize an answer.
    try:
        answer = generate_grounded_answer(q, results)

    except Exception as exc:
        # Keep implementation details and credentials out of the response.
        print(f"Gemini summarization failed: {type(exc).__name__}: {exc}")

        raise HTTPException(
            status_code=502,
            detail=(
                "Search succeeded, but AI summarization failed. "
                "Check the backend terminal for details."
            ),
        ) from exc

    return {
        "query": q,
        "summary": answer["summary"],
        "citations": answer["citations"],
        "total_results": len(results),
        "results": results,
        "filters": filter_metadata,
    }


def sse_event(event_type: str, **payload) -> str:
    return f"event: {event_type}\ndata: {json.dumps({'type': event_type, **payload})}\n\n"


async def next_stream_chunk(iterator):
    sentinel = object()

    def get_next():
        return next(iterator, sentinel)

    return await asyncio.to_thread(get_next), sentinel


@app.get("/ask/stream")
async def ask_stream(
    request: Request,
    q: str = Query(
        ...,
        min_length=1,
        description="The question to answer as a stream",
    ),
    time_range: str = Query("all"),
    category: str | None = Query(None),
    engine: str | None = Query(None),
):
    search_params, filter_metadata = await resolve_filters(
        time_range, category, engine
    )
    results = await fetch_search_results(q, search_params)
    return create_answer_stream(request, q, results, filter_metadata)


class ConversationMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class AnswerContextRequest(BaseModel):
    results: list[dict] = Field(default_factory=list)
    conversation_history: list[ConversationMessage] = Field(default_factory=list)


def create_answer_stream(
    request: Request,
    query: str,
    results: list[dict],
    filter_metadata: dict | None = None,
    conversation_history: list[ConversationMessage] | None = None,
    interpreted_question: str | None = None,
):
    sources = build_evidence_sources(results)

    async def event_stream():
        answer_parts = []
        iterator = None

        try:
            yield sse_event(
                "start",
                query=query,
                total_results=len(results),
                evidence_count=len(sources),
                filters=filter_metadata or {},
            )

            if not sources:
                yield sse_event(
                    "complete",
                    answer="No search results were found to summarize.",
                    citations=[],
                    total_results=0,
                    results=[],
                    filters=filter_metadata,
                )
                return

            iterator = stream_grounded_answer(
                query,
                results,
                conversation_history=[
                    message.model_dump() for message in (conversation_history or [])
                ],
                interpreted_question=interpreted_question,
            )
            while True:
                if await request.is_disconnected():
                    return

                chunk, sentinel = await next_stream_chunk(iterator)
                if chunk is sentinel:
                    break

                answer_parts.append(chunk)
                yield sse_event("chunk", text=chunk)

            answer = "".join(answer_parts).strip()
            citations = get_validated_citations(answer, sources)
            yield sse_event(
                "complete",
                answer=answer,
                citations=citations,
                total_results=len(results),
                results=results,
                filters=filter_metadata,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            yield sse_event(
                "error",
                message="The answer stream failed. Please try again.",
                recoverable=True,
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/ask/stream/context")
async def ask_stream_with_context(
    request: Request,
    q: str = Query(
        ...,
        min_length=1,
        description="The question to answer using supplied search results",
    ),
    context: AnswerContextRequest = Body(...),
):
    results = context.results
    conversation_history = [
        message.model_dump() for message in context.conversation_history
    ]
    interpreted_question = q

    if conversation_history:
        try:
            resolution = await asyncio.to_thread(
                resolve_followup_question,
                q,
                results,
                conversation_history,
            )
            interpreted_question = resolution["resolved_question"]
        except Exception as exc:
            # If reference resolution fails, search the original question and
            # keep the streaming answer path available.
            print(f"Follow-up question resolution failed: {type(exc).__name__}")
            resolution = {"resolved_question": q, "needs_search": True}

        if resolution["needs_search"] and not await request.is_disconnected():
            # Search only when the supplied cached evidence cannot answer the
            # clarified follow-up. These results define this answer's source
            # IDs and citation metadata.
            try:
                results = await fetch_search_results(interpreted_question)
            except Exception as exc:
                # If refresh fails, retain the cached evidence and its valid
                # citations; the answer prompt still gets the resolved question.
                print(f"Follow-up search failed: {type(exc).__name__}")

        if await request.is_disconnected():
            return

    return create_answer_stream(
        request,
        q,
        results,
        conversation_history=context.conversation_history,
        interpreted_question=interpreted_question,
    )
