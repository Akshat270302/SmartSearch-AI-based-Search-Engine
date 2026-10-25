import os

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from gemini_service import summarize_search_results

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


async def fetch_search_results(query: str) -> list[dict]:
    """Fetch and normalize results from SearXNG."""

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{SEARXNG_URL}/search",
                params={
                    "q": query,
                    "format": "json",
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
        }
        for result in data.get("results", [])
    ]


@app.get("/")
async def home():
    return {
        "message": "AI Search Engine API is running!"
    }


@app.get("/search")
async def search(
    q: str = Query(
        ...,
        min_length=1,
        description="The search query",
    ),
):
    results = await fetch_search_results(q)

    return {
        "query": q,
        "total_results": len(results),
        "results": results,
    }


@app.get("/ask")
async def ask(
    q: str = Query(
        ...,
        min_length=1,
        description="The question to answer",
    ),
):
    # First retrieve the relevant web search results.
    results = await fetch_search_results(q)

    # Then ask Gemini to synthesize an answer.
    try:
        summary = summarize_search_results(q, results)

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
        "summary": summary,
        "total_results": len(results),
        "results": results,
    }