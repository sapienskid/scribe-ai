import unittest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from scribe_ai.core.research import ResearchOrchestrator, ResearchQuery, AgentRole, Source, ReportFormatter
from scribe_ai.utils.rate_limiter import RateLimiter
import aiohttp
import json


class MockResponse:
    def __init__(self, status=200, json_data=None):
        self.status = status
        self._json_data = json_data

    async def json(self):
        return self._json_data

class TestResearchOrchestrator(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        """Setup for asynchronous test methods."""
        self.rate_limiter = RateLimiter(15, 60)
        self.mock_api = AsyncMock()
        self.orchestrator = ResearchOrchestrator(self.rate_limiter, self.mock_api)

    async def test_answer_question(self):
        # Mock API responses
        self.mock_api.generate_content.side_effect = [
            # Web search
            json.dumps({
                "content": "Sample content from source 1. More content related to the question.",
                "sources": ["source_id1"],
                "urls": ["https://www.example.com/source1"],
                "confidence": 0.9,
                "metadata": {
                    "source_credibility": "Highly credible source."
                }
            }),
            # Fact check
            {
                "verification_status": "verified",
                "confidence_score": 0.95,
                "issues_found": [],
                "suggestions": []
            },
            # Answer generation
            {
                "answer": "Concise answer to the question. [Source 1](https://www.example.com/source1)",
                "confidence": 0.98,
                "key_points": ["Key point 1", "Key point 2"],
                "limitations": []
            }
        ]

        # Test question
        question = "What is the capital of France?"
        answer = await self.orchestrator.answer_question(question)

        # Assertions
        self.assertEqual(answer['answer'], "Concise answer to the question. [Source 1](https://www.example.com/source1)")
        self.assertEqual(answer['sources'], ['https://www.example.com/source1'])
        self.assertEqual(answer['confidence'], 0.9)
        self.assertEqual(answer['verification_status'], 'verified')

    async def test_conduct_research_basic(self):
        # Mock API responses
        self.mock_api.generate_content.side_effect = [
            # Queries
            json.dumps([
                {"text": "query 1", "type": "web", "priority": 5, "agent": "Web Research Specialist"},
            ]),
            # Web search
            json.dumps({
                "content": "Sample content for query 1.",
                "sources": ["source_id1"],
                "urls": ["https://www.example.com/source1"],
                "confidence": 0.8,
                "metadata": {
                    "source_credibility": "Reliable source."
                }
            }),
            # Fact check
            {
                "verification_status": "verified",
                "confidence_score": 0.85,
                "issues_found": [],
                "suggestions": []
            },
            # Synthesis
            json.dumps({
                "executive_summary": {"abstract": "This is a synthesized abstract."},
            }),
            # Critique
            json.dumps({
                "strengths": ["Good research"],
                "weaknesses": [],
                "suggestions": [],
                "overall_quality": 9.5
            }),
            # Improvement (no improvement needed)
            json.dumps({
                "executive_summary": {"abstract": "This is a synthesized abstract."},
            }),
            # Critique (no change)
            json.dumps({
                "strengths": ["Good research"],
                "weaknesses": [],
                "suggestions": [],
                "overall_quality": 9.5
            }),
        ]

        content_plan = "Sample content plan"
        report = await self.orchestrator.conduct_research(content_plan)

        # Assertions
        self.assertIn('json_report', report)
        self.assertIn('markdown_report', report)
        self.assertEqual(report['json_report']['content_plan'], content_plan)
        self.assertEqual(report['json_report']['synthesis']['executive_summary']['abstract'], "This is a synthesized abstract.")
        self.assertEqual(report['json_report']['critique']['overall_quality'], 9.5)

    async def test_web_search_agent_tavily_success(self):
        # Mock Tavily API response
        mock_tavily_response = {
            "results": [
                {
                    "url": "https://www.example.com/source1",
                    "title": "Sample Source 1",
                    "content": "This is sample content from source 1.",
                    "author": "Author 1",
                    "published_date": "2023-12-19T00:00:00Z"
                }
            ]
        }
        async with aiohttp.ClientSession() as mock_session:
            mock_session.post = AsyncMock(return_value=MockResponse(json_data=mock_tavily_response))
            self.orchestrator.agents[AgentRole.WEB_EXPERT]._search_tavily = MagicMock(return_value=asyncio.Future())
            self.orchestrator.agents[AgentRole.WEB_EXPERT]._search_tavily.return_value.set_result(mock_tavily_response)

            query = ResearchQuery(
                text="test query", type="web", priority=4, agent=AgentRole.WEB_EXPERT
            )
            finding = await self.orchestrator.agents[AgentRole.WEB_EXPERT].search_web(query)

            self.assertEqual(finding.content, "Sample content for query 1.")
            self.assertEqual(finding.sources, ['https://www.example.com/source1'])
            self.assertEqual(finding.confidence, 0.8)

    async def test_format_citation(self):
        source = {
            'author': 'John Doe',
            'published_date': '2024-01-20',
            'title': 'A Sample Research Paper',
            'url': 'https://example.com/paper'
        }
        citation = ReportFormatter.format_citation(source)
        self.assertEqual(citation, "John Doe (2024). A Sample Research Paper. Retrieved from https://example.com/paper")

    async def test_add_intext_citations(self):
        text = "This is a sentence about a topic. This is another sentence."
        sources = {
            'source_id1': {
                'id': 'source_id1',
                'author': 'Jane Smith',
                'published_date': '2023-12-15',
                'title': 'Research on Something',
                'used_sections': ['This is a sentence about a topic.']
            }
        }
        cited_text = ReportFormatter.add_intext_citations(text, sources)
        self.assertEqual(cited_text, "This is a sentence about a topic. (Smith, 2023) This is another sentence.")

if __name__ == '__main__':
    unittest.main()
