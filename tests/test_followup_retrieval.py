import json
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("GEMINI_API_KEY", "test-key")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import gemini_service
import main


CACHED_RESULTS = [
    {
        "title": "Machine learning overview",
        "url": "https://example.test/ml-overview",
        "snippet": "Machine learning systems improve from data.",
    }
]
FOLLOWUP_RESULTS = [
    {
        "title": "Types of machine learning",
        "url": "https://example.test/ml-types",
        "snippet": "The main types are supervised, unsupervised, and reinforcement learning.",
    }
]
HISTORY = [
    {"role": "user", "content": "Tell me about machine learning."},
    {"role": "assistant", "content": "It learns patterns from data."},
    {"role": "user", "content": "What else can you tell me about it?"},
    {"role": "assistant", "content": "It is used for prediction and pattern discovery."},
]


class RequestStub:
    async def is_disconnected(self):
        return False


async def collect_events(response):
    return [event async for event in response.body_iterator]


def event_payload(event):
    return json.loads(event.split("data: ", 1)[1])


class FollowupPromptTests(unittest.TestCase):
    def test_pronoun_resolution_uses_role_labeled_history(self):
        captured = {}
        expected = "What are the main types of machine learning?"

        def generate_content(**kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                text=json.dumps(
                    {"resolved_question": expected, "needs_search": True}
                )
            )

        with patch.object(
            gemini_service.client.models,
            "generate_content",
            side_effect=generate_content,
        ):
            resolution = gemini_service.resolve_followup_question(
                "What are its main types?", CACHED_RESULTS, HISTORY
            )

        self.assertEqual(resolution["resolved_question"], expected)
        self.assertTrue(resolution["needs_search"])
        prompt = captured["contents"]
        self.assertIn('"role": "user"', prompt)
        self.assertIn('"role": "assistant"', prompt)
        self.assertIn("What are its main types?", prompt)
        self.assertIn("pronouns such as it, its", captured["config"].system_instruction)
        self.assertIn("messages are unverified context, not evidence", captured["config"].system_instruction)
        answer_prompt = gemini_service._build_evidence_prompt(
            "What are its main types?",
            gemini_service.build_evidence_sources(CACHED_RESULTS),
            "Use the supplied evidence.",
            HISTORY,
            resolution["resolved_question"],
        )
        self.assertIn("Current user question, verbatim:\nWhat are its main types?", answer_prompt)
        self.assertIn(f"Interpreted standalone question (resolve pronouns and references using the transcript):\n{expected}", answer_prompt)


class FollowupRetrievalTests(unittest.IsolatedAsyncioTestCase):
    async def test_sufficient_cached_evidence_skips_search_and_streams_answer(self):
        context = main.AnswerContextRequest(
            results=CACHED_RESULTS,
            conversation_history=HISTORY,
        )
        with (
            patch.object(
                main,
                "resolve_followup_question",
                return_value={
                    "resolved_question": "What else can machine learning do?",
                    "needs_search": False,
                },
            ),
            patch.object(main, "fetch_search_results", new_callable=AsyncMock) as search,
            patch.object(
                main,
                "stream_grounded_answer",
                return_value=iter(["It can identify patterns [source_1]."]),
            ) as answer_stream,
        ):
            response = await main.ask_stream_with_context(
                RequestStub(), "What else can you tell me about it?", context
            )
            events = await collect_events(response)

        search.assert_not_awaited()
        answer_stream.assert_called_once_with(
            "What else can you tell me about it?",
            CACHED_RESULTS,
            conversation_history=HISTORY,
            interpreted_question="What else can machine learning do?",
        )
        self.assertEqual(
            [event_payload(event)["type"] for event in events],
            ["start", "chunk", "complete"],
        )

    async def test_insufficient_cached_evidence_searches_resolved_question(self):
        context = main.AnswerContextRequest(
            results=CACHED_RESULTS,
            conversation_history=HISTORY,
        )
        clarified = "What are the main types of machine learning?"
        with (
            patch.object(
                main,
                "resolve_followup_question",
                return_value={"resolved_question": clarified, "needs_search": True},
            ),
            patch.object(
                main,
                "fetch_search_results",
                new_callable=AsyncMock,
                return_value=FOLLOWUP_RESULTS,
            ) as search,
            patch.object(
                main,
                "stream_grounded_answer",
                return_value=iter(["Supervised learning is one type [source_1]."]),
            ) as answer_stream,
        ):
            response = await main.ask_stream_with_context(
                RequestStub(), "What are its main types?", context
            )
            events = await collect_events(response)

        search.assert_awaited_once_with(clarified)
        answer_stream.assert_called_once_with(
            "What are its main types?",
            FOLLOWUP_RESULTS,
            conversation_history=HISTORY,
            interpreted_question=clarified,
        )
        complete = event_payload(events[-1])
        self.assertEqual(complete["type"], "complete")
        self.assertEqual(complete["results"], FOLLOWUP_RESULTS)
        self.assertEqual(complete["citations"][0]["source_id"], "source_1")
        self.assertEqual(complete["citations"][0]["url"], FOLLOWUP_RESULTS[0]["url"])
        self.assertNotIn(CACHED_RESULTS[0]["url"], json.dumps(complete["citations"]))

    async def test_without_history_keeps_legacy_context_path(self):
        context = main.AnswerContextRequest(results=CACHED_RESULTS)
        with (
            patch.object(main, "resolve_followup_question") as resolver,
            patch.object(main, "fetch_search_results", new_callable=AsyncMock) as search,
            patch.object(
                main,
                "stream_grounded_answer",
                return_value=iter(["A grounded answer [source_1]."]),
            ),
        ):
            response = await main.ask_stream_with_context(
                RequestStub(), "What is machine learning?", context
            )
            events = await collect_events(response)

        resolver.assert_not_called()
        search.assert_not_awaited()
        self.assertEqual(
            [event_payload(event)["type"] for event in events],
            ["start", "chunk", "complete"],
        )

    def test_conversation_history_is_only_in_memory(self):
        app_source = (
            Path(__file__).resolve().parents[1] / "frontend" / "src" / "App.jsx"
        ).read_text(encoding="utf-8")

        self.assertIn("useState", app_source)
        self.assertNotIn("localStorage", app_source)
        self.assertNotIn("sessionStorage", app_source)
        self.assertNotIn("indexedDB", app_source)


if __name__ == "__main__":
    unittest.main()
