import os
import sys
import unittest

os.environ.setdefault("GEMINI_API_KEY", "test-key")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import main


class SearchFilterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        async def capabilities():
            return {
                "categories": {"general", "news", "science", "it", "images"},
                "engines": {
                    "brave": {
                        "name": "brave",
                        "shortcut": "br",
                        "time_range_support": True,
                    },
                    "wikipedia": {
                        "name": "wikipedia",
                        "shortcut": "wp",
                        "time_range_support": False,
                    },
                },
            }

        self.original_capabilities = main.get_searxng_capabilities
        main.get_searxng_capabilities = capabilities

    async def asyncTearDown(self):
        main.get_searxng_capabilities = self.original_capabilities

    async def test_maps_supported_filters(self):
        params, metadata = await main.resolve_filters("week", "news", "brave")

        self.assertEqual(
            params,
            {"categories": "news", "engines": "br", "time_range": "week"},
        )
        self.assertEqual(metadata["engine"], "brave")
        self.assertEqual(metadata["warnings"], [])

    async def test_warns_when_engine_does_not_support_time_range(self):
        _, metadata = await main.resolve_filters("month", "general", "wikipedia")

        self.assertTrue(metadata["warnings"])

    async def test_all_time_preserves_default_query_parameters(self):
        params, metadata = await main.resolve_filters("all", None, None)

        self.assertEqual(params, {})
        self.assertEqual(metadata["warnings"], [])

    async def test_rejects_unknown_filter_values(self):
        invalid_filters = (
            ("hour", None, None),
            ("day", "unsupported", None),
            ("day", None, "unknown"),
        )

        for filters in invalid_filters:
            with self.subTest(filters=filters):
                with self.assertRaises(main.HTTPException) as context:
                    await main.resolve_filters(*filters)
                self.assertEqual(context.exception.status_code, 422)

    async def test_answer_context_accepts_cached_search_results(self):
        results = [
            {
                "title": "FastAPI",
                "url": "https://fastapi.tiangolo.com/",
                "snippet": "A web framework for building APIs.",
            }
        ]

        context = main.AnswerContextRequest(results=results)

        self.assertEqual(context.results, results)


if __name__ == "__main__":
    unittest.main()
