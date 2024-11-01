import aiohttp
import json
import logging
import os
from dotenv import load_dotenv
from typing import Dict, Any, List, Optional, Set, Tuple
from dataclasses import dataclass, fields
from enum import Enum
import uuid
from datetime import datetime
import asyncio
from scribe_ai.utils.text_processing import GeminiAPI
from scribe_ai.utils.rate_limiter import RateLimiter
rate_limiter =RateLimiter(15, 60)
api = GeminiAPI(use_json=True)
load_dotenv()

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

logger = logging.getLogger(__name__)


def dataclass_to_dict(obj):
    """Convert a dataclass object to a dictionary."""
    if hasattr(obj, "__dict__"):
        result = {}
        for key, value in obj.__dict__.items():
            result[key] = dataclass_to_dict(value)
        return result
    elif isinstance(obj, (list, tuple)):
        return [dataclass_to_dict(item) for item in obj]
    elif isinstance(obj, Enum):
        return obj.value
    else:
        return obj


class AgentRole(Enum):
    QUERY_SPECIALIST = "Query Generation Specialist"
    SEARCH_EXPERT = "Search Operations Expert"
    FACT_CHECKER = "Fact Verification Specialist"
    SYNTHESIS_EXPERT = "Information Synthesis Expert"
    WEB_EXPERT = "Web Research Specialist"
    CRITIC = "Critical Analysis Specialist"




@dataclass
class ResearchQuery:
    text: str
    type: str
    priority: int
    agent: AgentRole
    context: Optional[str] = None

    def to_dict(self):
        return {
            "text": self.text,
            "type": self.type,
            "priority": self.priority,
            "agent": self.agent.value,
            "context": self.context
        }


@dataclass
class ResearchFinding:
    query: ResearchQuery
    content: str
    sources: List[str]
    urls: List[str]
    confidence: float
    agent: AgentRole
    metadata: Dict[str, Any] = None
    def to_dict(self):
        return {
            "query": self.query.to_dict(),
            "content": self.content,
            "sources": self.sources,
            "urls": self.urls,
            "confidence": self.confidence,
            "agent": self.agent.value,
            "metadata": self.metadata,
        }


class Source:
    def __init__(self, url: str, title: str, content: str, author: Optional[str] = None, published_date: Optional[str] = None):
        self.id = str(uuid.uuid4())
        self.url = url
        self.title = title
        self.content = content
        self.author = author # Add this line
        self.published_date = published_date
        self.used_sections = []
        self.credibility_score = 0.0
        self.verification_status = None


    def add_used_section(self, section: str):
        if section not in self.used_sections:
            self.used_sections.append(section)

    def to_dict(self):
        return {
            "id": self.id,
            "url": self.url,
            "title": self.title,
            "author": self.author,
            "published_date": self.published_date,
            "credibility_score": self.credibility_score,
            "verification_status": self.verification_status,
            "used_sections": self.used_sections
        }

    def to_citation(self) -> str:
        """Generate a citation string for the source."""
        citation = f"[{self.title}] ({self.url})"
        if self.author:
            citation += f"by {self.author}"
        if self.published_date:
            citation += f"({self.published_date})"
        return citation


class BaseAgent:
    def __init__(self, role: AgentRole, api, ratelimiter=None):
        self.role = role
        self.api = api
        self.rate_limiter = ratelimiter
        self.memory: List[Dict[str, Any]] = []

    async def think(self, context: str, ) -> str:
        prompt = f"""
        As a {self.role.value}, analyze this content plan:
        {context}
        Think step by step about:
        1. What are teh key aspects to consider?
        2. What potential challenges might arise?
        3. What approach would be most effective?
        Respond in first person, as if you are actively thinking thoough this.
        """
        response = await self.api.generate_content(prompt)
        return response if isinstance(response, str) else json.dumps(response)

    def remember(self, information: Dict[str, Any]):
        self.memory.append(information)

    def recall(self, context: str) -> List[Dict[str, Any]]:
        return [m for m in self.memory if context.lower() in str(m).lower()]


class QueryAgent(BaseAgent):
    def __init__(self, api):
        super().__init__(AgentRole.QUERY_SPECIALIST, api)

    async def generate_queries(self, content_plan: str) -> List[ResearchQuery]:
        thinking = await self.think(content_plan)
        prompt = f"""
        Based on this thinking:{thinking}
        Generate a diverse set of research queries for : {content_plan}

        Create different types of queries:
        1. Web queries (for current information)
        2. Fact-checking queries
        3. Deep-dive specific aspect queries

        Return a JSON array where each object has exactly these fields:
        {{
            "text": "the actual query string",
            "type": "one of: web, fact-check, or deep-dive",
            "priority": "number from 1-5, 5 being highest",
            "agent": "must be one of: {', '.join(role.value for role in AgentRole)}"
        }}

        """
        try:
            queries_data = await self.api.generate_content(prompt)

            if not isinstance(queries_data, list):
                logger.error(f"Expected JSON array, got: {type(queries_data)}")
                return []
            research_queries = []
            for query_data in queries_data:
                try:
                    if not all(key in query_data for key in ["text", 'type', 'priority', 'agent']):
                        logger.error(
                            f"Missing required fields in query data: {query_data}")
                        continue
                    if query_data['type'] not in ['web', 'fact-check', 'deep-dive']:
                        logger.error(f"Invalid query type: {
                                     query_data['type']}")
                        continue
                    if not (1 <= query_data["priority"] <= 5):
                        logger.error(f"Invalid priority vlaue: {
                                     query_data["priority"]}")
                        continue
                    try:
                        agent_role = next(
                            role for role in AgentRole if role.value == query_data["agent"])
                    except StopIteration:
                        logger.error(f"Invalid agent role: {
                                     query_data["agent"]}")
                        continue
                    research_queries.append(ResearchQuery(text=query_data["text"],
                                                          type=query_data["type"], priority=query_data["priority"], agent=agent_role, context=content_plan))

                except Exception as e:
                    logger.error(f"Error processing query data: {str(e)}")
            return research_queries
        except Exception as e:
            logger.error(f"Error generating queries: {str(e)}")
            return []


class WebResearchAgent(BaseAgent):
    def __init__(self, api, rate_limiter):
        super().__init__(AgentRole.WEB_EXPERT, api, rate_limiter)
        self.orchestrator = None  # Initialize orchestrator reference

    def set_orchestrator(self, orchestrator):
        self.orchestrator = orchestrator

    async def search_web(self, query: ResearchQuery) -> ResearchFinding:
        tavily_data = await self._search_tavily(query.text)
        sources = []
        urls = []  # Track URLs separately

        if tavily_data and 'results' in tavily_data:
            for result in tavily_data['results']:
                try:
                    source = Source(
                        url=result.get('url', ''),
                        title=result.get('title', 'Untitled'),
                        content=result.get('content', ''),
                        author=result.get('author'),
                        published_date=result.get('published_date')
                    )

                    if source.url and source.content:
                        if hasattr(self, 'orchestrator') and self.orchestrator is not None:
                            self.orchestrator.sources[source.id] = source
                            sources.append(source.id)
                            urls.append(source.url)
                        else:
                            logger.warning(
                                "Orchestrator not properly initialized")
                except Exception as e:
                    logger.error(f"Error processing source: {str(e)}")
                    continue

        if not sources:
            logger.warning("No valid sources found for query: " + query.text)
            error_response = {
                "content": "No valid sources found for this query.",
                "sources": [],
                "urls": [],
                "confidence": 0.0,
                "metadata": {
                    "error": "No valid sources found",
                    "source_credibility": "No sources to evaluate"
                }
            }
            return ResearchFinding(**error_response)

        prompt = f"""
        Analyze these web search results for the query: {query.text}

        Results: {json.dumps(tavily_data)}

        Provide analysis in the following exact JSON format:
        {{
            "content": "main findings with source references",
            "sources": ["source_id1", "source_id2"],
            "urls": ["url1", "url2"],
            "confidence": 0.8,
            "metadata": {{
                "source_credibility": "evaluation of source reliability and authority"
            }}
        }}

        Ensure the response maintains this exact JSON structure.
        The confidence score must be between 0 and 1.
        Include source references in the content using URLs where relevant.
        """

        try:
            response = await self.api.generate_content(prompt)
            # Handle both string and direct JSON responses
            if isinstance(response, str):
                analysis = json.loads(response)
            elif isinstance(response, dict):
                analysis = response
            else:
                raise ValueError("Unexpected response format")

            # Validate required fields
            required_fields = ['content', 'sources',
                               'urls', 'confidence', 'metadata']
            if not all(field in analysis for field in required_fields):
                raise ValueError("Missing required fields in analysis")

            # Ensure proper typing
            analysis['confidence'] = float(analysis.get('confidence', 0.0))

        except Exception as e:
            logger.error(f"Error generating analysis: {str(e)}")
            analysis = {
                "content": "Error generating analysis.",
                "sources": sources,
                "urls": urls,
                "confidence": 0.0,
                "metadata": {
                    "error": str(e),
                    "source_credibility": "Error during analysis"
                }
            }
        return ResearchFinding(
            query=query,
            content=analysis["content"],
            sources=sources,
            urls=urls,
            confidence=analysis['confidence'],
            agent=self.role,
            metadata=analysis['metadata']
        )

    async def _search_tavily(self, query: str) -> Dict[str, Any]:
        async with aiohttp.ClientSession() as session:
            await self.rate_limiter.wait()
            url = "https://api.tavily.com/search"
            params = {
                "api_key": TAVILY_API_KEY,
                "query": query,
                "search_depth": "advanced",
                'include_image': False,
                'include_answer': True,
                'max_results': 5

            }
            try:
                async with session.post(url, json=params) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        logger.error(f"Tavily API error: {response.status}")
                        return {"error": f"API returned status {response.status}", "results": []}
            except Exception as e:
                logger.error(f"Tavily API request failed: {str(e)}")
                return {"error": str(e), "results": []}


class FactCheckAgent(BaseAgent):
    def __init__(self, api):
        super().__init__(AgentRole.FACT_CHECKER, api)

    async def verify_information(self, finding: ResearchFinding) -> Dict[str, Any]:
        finding_str = (
            f"Content: {finding.content}\n"
            f"Sources: {', '.join(finding.sources)}\n"
            f"Confidence: {finding.confidence}"

        )
        prompt = f"""
        Fact check this research finding:
        {finding_str}

        Verify:
        1. Consistency across sources
        2. Potential biases
        3. Currency of information
        4. Credibility of sources
        5. Logical consistency

        Return a JSON object with this exact format:
        {{
            "verification_status": "verified|partially_verified|unverified",
            "confidence_score": 0.0,
            "issues_found": [],
            "suggestions": []
        }}
        """
        try:
            response = await self.api.generate_content(prompt)
            if isinstance(response, dict):
                result = self._validate_verification_result(response)
            elif isinstance(response, str):
                try:
                    parsed = json.loads(response)
                    result = self._validate_verification_result(response)
                except json.JSONDecodeError as e:
                    logger.error(
                        f"JSON parsing error in verify_information: {str(e)}")
                    result = self._create_fallback_verification()
            else:
                logger.error(f"Unexpected response type: {type(response)}")
                result = self._create_fallback_verification()

            return result
        except Exception as e:
            logger.error(f"Error in verify_information: {str(e)}")
            return self._create_fallback_verification()

    def _validate_verification_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and normalize verification result."""
        valid_statuses = {"verified", "partially_verified", "unverified"}
        validated = {
            "verification_status": (result.get("verification_status") if result.get("verification_status") in valid_statuses else "unverified"),
            "confidence_score": float(
                max(0.0, min(1.0, result.get("confidence_score", 0.0)))
            ),
            "issues_found": (
                [str(issue)for issue in result.get("issues_found", [])] if isinstance(
                    result.get("issues_found"), list)else []
            ),
            "suggestions": (
                [str(sugg)for sugg in result.get("suggestions", [])] if isinstance(
                    result.get("suggestions"), list) else []

            )

        }
        if validated["verification_status"] == "unverified" and not validated["issues_found"]:
            validated["issues_found"] = "Insufficient verification data"
        return validated

    def _create_fallback_verification(self) -> Dict[str, Any]:
        """Create a safe fallback verification result."""
        return {
            "verification_status": "unverified",
            "confidence_score": 0.0,
            "issues_found": ["Verification process failed"],
            "suggestions": ["Retry verification", "Check source reliability"]
        }


class SynthesisAgent(BaseAgent):
    def __init__(self, api):
        super().__init__(AgentRole.SYNTHESIS_EXPERT, api)

    async def synthesize_findings(self, findings: List[ResearchFinding], content_plan: str, ) -> Dict[str, Any]:
        thinking = await self.think(f"Synthesizing {len(findings)} findings  :{content_plan}")
        structure = {
            "front_matter": {
                "title": "",
                "authors": [],
                "date": "",
                "keywords": []
            },
            "executive_summary": {
                "abstract": "",
                "key_findings": [],
                "significance": ""
            },
            "introduction": {
                "background": "",
                "objectives": [],
                "scope": "",
                "research_questions": []
            },
            "literature_review": {
                "theoretical_framework": "",
                "previous_research": [],
                "gaps_identified": []
            },
            "methodology": {
                "research_design": "",
                "data_collection": {
                    "methods": [],
                    "sources": [],
                    "limitations": []
                },
                "analysis_approach": ""
            },
            "findings": {
                "primary_results": [],
                "thematic_analysis": {
                    "major_themes": [],
                    "supporting_evidence": []
                },
                "case_studies": [],
                "data_visualization_notes": []
            },
            "discussion": {
                "interpretation": "",
                "implications": [],
                "limitations": [],
                "future_directions": []
            },
            "conclusion": {
                "summary": "",
                "recommendations": [],
                "closing_thoughts": ""
            },
            "references": {
                "citations": [],
                "additional_resources": []
            },
            "appendices": {
                "supplementary_data": [],
                "methodological_details": [],
                "additional_analyses": []
            }
        }
        prompt = f"""
Based on this thinking: {thinking}
Synthesize the following research materials into a comprehensive report:
content Plan: {content_plan}
Number of findings: {len(findings)}
Focus on :
1. Integrating findings coherently
2. Highlighting key insights
3. Supporting claims with evidence
4. Maintaining a logical flow
5. Ensuring clarity and readability
6. Proper citation of sources
Return a JSON object matching exactly this structure:
{json.dumps(structure, indent=2)}
Ensure all JSON fields are properly formatted and escapted.

"""
        try:
            response = await self.api.generate_content(prompt)
            if isinstance(response, str):
                try:
                    synthesis = json.loads(response)
                except json.JSONDecodeError as e:
                    logger.error(
                        f"JSON parsing error in synthesize_findings:{str(e)}")
                    structure["executive_summary"]["abstract"] = f"Error synthesizing findings: {
                        str(e)}"
                    return structure

            else:
                synthesis = response

            for section, template_value in structure.items():
                if section not in synthesis:
                    synthesis[section] = template_value
                elif isinstance(template_value, dict):
                    for subsection, subtemplate in template_value.items():
                        if subsection not in synthesis[section]:
                            synthesis[section][subsection] = subtemplate
            return synthesis
        except Exception as e:
            logger.error(f"Error in synthesize_findings: {str(e)}")
            structure['executive_summary']['abstract'] = f"Error synthesizing findings: {
                str(e)}"
            return structure


class CriticAgent(BaseAgent):
    def __init__(self, api):
        super().__init__(AgentRole.CRITIC, api)

    async def critiqe_research(self, synthesis: Dict[str, Any], findings: List[ResearchFinding]) -> Dict[str, Any]:
        prompt = f"""
        Critically analyze this research:
        Synthesis: {json.dumps(synthesis)}
        Findings: {json.dumps([f.to_dict() for f in findings])}
        Evaluate:
        1. Comprehensiveness of coverage
        2. Quality of evidence
        3. Logical consistency
        4. Potential biases
        5. Methodological soundness

        Provide constructive criticism and suggestions for improvement.

        Return your analysis in the following exact JSON structure:
        {{
            "strengths": [
                "strength1",
                "strength2"
            ],
            "weaknesses": [
                "weakness1",
                "weakness2"
            ],
            "suggestions": [
                "suggestion1",
                "suggestion2"
            ],
            "overall_quality": 8
        }}

        Ensure your response is valid JSON with proper escaping of special characters.
"""
        try:
            response = await self.api.generate_content(prompt)
            if isinstance(response, dict):
                return self._validate_critique_format(response)
            if isinstance(response, str):
                try:
                    parsed_response = json.loads(response)
                    return self._validate_critique_format(parsed_response)
                except json.JSONDecodeError as e:
                    logger.error(
                        f"JSON parsing error in critique_research: {str(e)}")
                    logger.debug(f"Problematic response: {response}")
                    return self._create_fallback_critique()
            return self._create_fallback_critique()
        except Exception as e:
            logger.error(f"Error in critique_research: {str(e)}")
            return self._create_fallback_critique()

    def _validate_critique_format(self, critique: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and ensure the critique has all required fields."""
        required_fields = {
            'strengths': List,
            'weaknesses': List,
            'suggestions': List,
            'overall_quality': (int, float)
        }
        validated = {}
        for field, expected_type in required_fields.items():
            value = critique.get(field)
            if value is None or not isinstance(value, expected_type):
                if expected_type == List:
                    validated[field] = []
                elif expected_type in (int, float):
                    validated[field] = 5
                continue

            if expected_type == List:
                validated[field] = [str(item) for item in value if item]
                if not validated[field]:
                    validated[field] = ["No items provided"]
            elif field == "overall_quality":
                validated[field] = max(1, min(10, float(value)))
            else:
                validated[field] = value
        return validated

    def _create_fallback_critique(self) -> Dict[str, Any]:
        """Create a fallback critique structure when normal processing fails."""
        return {
            "strengths": ["Unable to analyze strengths due to processing error"],
            "weaknesses": ["Analysis failed - please review raw data"],
            "suggestions": ["Retry analysis", "Verify input data format"],
            "overall_quality": 5  # Neutral score when unable to properly evaluate
        }


class QuestionAnswering:
    """Handles direct question answering with source attribution,"""
    def __init__(self, web_research:WebResearchAgent, fact_checker:FactCheckAgent):
        self.web_research = web_research
        self.fact_checker = fact_checker
    
    async def answer_question(self, question:str) ->Dict[str, Any]:
        """
        Answers a specific question with sources and confidence scores.
        
        Args:
            question: The question to answer
            
        Returns:
            Dict containing answer, sources, confidence score, and verification status
        """
        query = ResearchQuery(
            text=question, type="fact-check",
            priority=5, 
            agent=AgentRole.WEB_EXPERT
        )
        finding = await self.web_research.search_web(query)
        verification = await self.fact_checker.verify_information(finding)
        answer_prompt = f"""
        Based on this research finding:
        {finding.content}
        
        Generate a concise, direct answer to: {question}
        
        Requirements:
        1. Be specific and to the point
        2. Include relevant numbers and facts
        3. Cite sources using [Source Title](URL) format
        4. Express any uncertainty when appropriate
        
        Return as JSON:
        {{
            "answer": "concise answer with inline citations",
            "confidence": 0.0-1.0,
            "key_points": ["point1", "point2"],
            "limitations": ["limitation1", "limitation2"]
        }}
        """
        try:
            response = await self.web_research.api.generate_content(answer_prompt)
            if isinstance(response, str):
                response = json.loads(response)
            
            return {
                "answer": response["answer"],
                "sources": finding.urls,
                "confidence": min(finding.confidence, float(verification["confidence_score"])),
                "verification_status": verification["verification_status"],
                "key_points": response.get("key_points", []),
                "limitations": response.get("limitations", []),
                "metadata": {
                    "issues_found": verification["issues_found"],
                    "suggestions": verification["suggestions"]
                }
            }
        except Exception as e:
            logger.error(f"Error in answer generation: {str(e)}")
            return {
                "answer": "Error generating answer",
                "sources": [],
                "confidence": 0.0,
                "verification_status": "error",
                "key_points": [],
                "limitations": ["Error in processing"],
                "metadata": {"error": str(e)}
            }
      

class ReportFormatter:
    @staticmethod
    def format_citation(source:dict)-> str:
        """Create an APA-style citation from a source dictionary."""
        try:
            author = source.get('author')
            if not author:
                author ="No author"
            date = source.get('published_date')
            year = date.split('-')[0] if date else "n.d."
            title = source.get('title', '').rstrip('.')
            url = source.get('url')
            citation = f"{author} ({year}). {title}"
            if url:
                citation+= f". Retrieved from {url}"
            return citation
        except Exception as e:
            logger.error(f"Error formatting citation: {str(e)}")
            return "Error formatting citation)"
    
    @staticmethod
    def add_intext_citations(text:str, sources:Dict[str, Any])->str:
        """Add in-text citations with proper APA formatting"""
        if not text or not sources:
            return text or ""
        cited_text=text
        try:
            for source_id, source in sources.items():
                if not sources:
                    continue
                author = source.get('author')
                if not author:
                    author ="No author"
                date = source.get('published_date', 'n.d')
                year = date.split('-')[0] if date else 'n.d'
                if "," in author:
                    last_name = author.split(',')[0].strip()
                else:
                    last_name = author.split()[-1] if author != "No author" else "No author"
                citation = f"({last_name}, {year})"

                used_sections = source.get('used_sections', [])
                for section in used_sections:
                    if section and section in cited_text and citation not in cited_text:
                        if section.endswith('.'):
                            cited_text = cited_text.replace(section, f"{section[:-1]} {citation}")
                        else:
                            cited_text = cited_text.replace(section, f"{section} {citation}")
            return cited_text
        except Exception as e:
            logger.error(f"Error adding in-text citations: {str(e)}")
            return text
    @staticmethod
    def format_markdown_report(report_data: Dict[str, Any]) -> str:
        """Format research report in Markdown with proper citations."""
        try:
            md_sections = []
            synthesis = report_data.get('synthesis', {})

            # Create source lookup
            sources = {s['id']: s for s in report_data.get(
                'sources', []) if isinstance(s, dict) and s.get('id')}

            # Front Matter
            md_sections.extend([
                "---",
                f"title: {synthesis.get('title_and_overview', {}).get(
                    'title', 'Research Report')}",
                "author: Sabin Pokharel",
                f"date: {datetime.now().strftime('%B %d, %Y')}",
                "---\n"
            ])

            # Executive Summary
            md_sections.extend([
                "# Executive Summary\n",
                ReportFormatter.add_intext_citations(
                    synthesis.get('title_and_overview', {}
                                  ).get('abstract', ''),
                    sources
                ),
                "\n"
            ])

            # Main Sections
            for section_name, section_content in synthesis.items():
                if not isinstance(section_content, dict) or section_name == 'title_and_overview':
                    continue

                md_sections.append(
                    f"\n# {section_name.replace('_', ' ').title()}\n")

                for subsection_name, subsection_content in section_content.items():
                    md_sections.append(
                        f"\n## {subsection_name.replace('_', ' ').title()}\n")

                    if isinstance(subsection_content, str):
                        content = ReportFormatter.add_intext_citations(
                            subsection_content, sources)
                        md_sections.append(content + "\n")
                    elif isinstance(subsection_content, list):
                        for item in subsection_content:
                            if item:
                                content = ReportFormatter.add_intext_citations(
                                    str(item), sources)
                                md_sections.append(f"- {content}\n")
                    elif isinstance(subsection_content, dict):
                        for key, value in subsection_content.items():
                            if value:
                                content = ReportFormatter.add_intext_citations(
                                    str(value), sources)
                                md_sections.append(
                                    f"### {key.replace('_', ' ').title()}\n{content}\n")

            # References
            md_sections.extend([
                "\n# References\n",
                *[f"- {ReportFormatter.format_citation(source)}\n"
                  for source in sorted(
                      sources.values(),
                      key=lambda s: (
                          s.get('published_date', 'n.d.'), s.get('title', ''))
                )]
            ])

            return "\n".join(md_sections)

        except Exception as e:
            logger.error(f"Error formatting markdown report: {str(e)}")
            return f"# Error in Report Generation\n\nAn error occurred: {str(e)}"        

class ResearchImprover:
    def __init__(self, orchestrator):
        self.orchestrator = orchestrator
        self.improvement_threshold = 8.0
        self.max_iterations = 3

    async def improve_research(self, synthesis: Dict[str, Any], critique: Dict[str, Any], findings: List[ResearchFinding], content_plan: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Iteratively improve research based on critique feedback. Returns improved synthesis and critique."""
        current_synthesis = synthesis
        current_critique = critique
        iteration = 0
        
        while (current_critique['overall_quality'] < self.improvement_threshold and iteration < self.max_iterations):
            improvement_plan = await self._create_improvement_plan(current_critique)
            new_findings = await self._conduct_additional_research(
                improvement_plan, content_plan, findings
            )
            findings.extend(new_findings)
            current_synthesis = await self._improve_synthesis(
                current_synthesis, improvement_plan, findings
            )
            current_critique = await self.orchestrator.agents[AgentRole.CRITIC].critiqe_research(
                current_synthesis, findings
            )
            iteration += 1
            
        return current_synthesis, current_critique

    async def _create_improvement_plan(self, critique: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a structured improvement plan based on the critique"""
        try:
            prompt = {
                "role": "research_improver",
                "critique": critique,
                "task": "create_improvement_plan",
                "format_instructions": {
                    "research_gaps": [
                        {
                            "topic": "string - specific topic needing more research",
                            "reason": "string - why this needs more research",
                            "suggested_queries": ["string - query1", "string - query2"]
                        }
                    ],
                    "narrative_gaps": [
                        {
                            "theme": "string - theme needing better coverage",
                            "requirements": ["string - requirement1", "string - requirement2"]
                        }
                    ],
                    "synthesis_improvements": [
                        {
                            "section": "string - section name",
                            "issue": "string - what needs improvement",
                            "suggestions": ["string - suggestion1", "string - suggestion2"]
                        }
                    ],
                    "verification_needs": [
                        {
                            "claim": "string - claim needing verification",
                            "verification_approach": "string - suggested approach"
                        }
                    ]
                }
            }

            response = await self.orchestrator.api.generate_content(json.dumps(prompt))
            
            # Handle both string and dict responses
            if isinstance(response, str):
                try:
                    parsed_response = json.loads(response)
                    return self._validate_improvement_plan(parsed_response)
                except json.JSONDecodeError as e:
                    logger.error(f"JSON parsing error in _create_improvement_plan: {str(e)}")
                    return self._create_fallback_plan()
            elif isinstance(response, dict):
                return self._validate_improvement_plan(response)
            else:
                logger.error(f"Unexpected response type: {type(response)}")
                return self._create_fallback_plan()
                
        except Exception as e:
            logger.error(f"Error in _create_improvement_plan: {str(e)}")
            return self._create_fallback_plan()

    def _validate_improvement_plan(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and ensure the improvement plan has all required fields."""
        required_sections = ['research_gaps', 'narrative_gaps', 'synthesis_improvements', 'verification_needs']
        validated_plan = {}
        
        for section in required_sections:
            if section not in plan or not isinstance(plan[section], list):
                validated_plan[section] = []
            else:
                validated_plan[section] = plan[section]
                
        return validated_plan

    def _create_fallback_plan(self) -> Dict[str, Any]:
        """Create a basic improvement plan when normal processing fails."""
        return {
            "research_gaps": [
                {
                    "topic": "general verification",
                    "reason": "ensure baseline coverage",
                    "suggested_queries": ["verify main claims", "check primary sources"]
                }
            ],
            "narrative_gaps": [
                {
                    "theme": "basic structure",
                    "requirements": ["ensure logical flow", "check completeness"]
                }
            ],
            "synthesis_improvements": [
                {
                    "section": "overall",
                    "issue": "review needed",
                    "suggestions": ["verify all sections", "check coherence"]
                }
            ],
            "verification_needs": [
                {
                    "claim": "general verification",
                    "verification_approach": "basic fact checking"
                }
            ]
        }

    async def _conduct_additional_research(self, improvement_plan: Dict[str, Any], content_plan: str, findings: List[ResearchFinding]) -> List[ResearchFinding]:
        """Conduct additional research based on the improvement plan."""
        new_findings = []
        
        for gap in improvement_plan.get('research_gaps', []):
            queries = []
            for query_text in gap.get('suggested_queries', []):
                query = ResearchQuery(
                    text=query_text,
                    type='deep-dive',
                    priority=5,
                    agent=AgentRole.WEB_EXPERT,
                    context=f"Filling research gap: {gap.get('topic', 'general improvement')}"
                )
                queries.append(query)
                
            tasks = [
                self.orchestrator.agents[AgentRole.WEB_EXPERT].search_web(query)
                for query in queries
            ]
            
            try:
                results = await asyncio.gather(*tasks)
                for finding in results:
                    verification = await self.orchestrator.agents[AgentRole.FACT_CHECKER].verify_information(finding)
                    if verification['verification_status'] in ['verified', 'partially_verified']:
                        new_findings.append(finding)
            except Exception as e:
                logger.error(f"Error in additional research: {str(e)}")
                
        return new_findings    
    async def _improve_synthesis(self, current_synthesis: Dict[str, Any], 
                               improvement_plan: Dict[str, Any],
                               findings: List[ResearchFinding], 
                               ) -> Dict[str, Any]:
        """Improve synthesis based on improvement plan."""
        prompt = f"""
        Improve this synthesis based on the improvement plan and additional research:
        
        Current Synthesis: {json.dumps(current_synthesis)}
        Improvement Plan: {json.dumps(improvement_plan)}
        Number of total findings: {len(findings)}
        Focus on:
        1. Addressing identified gaps
        2. Strengthening weak sections
        3. Incorporating new research
        4. Improving narrative flow
        5. Enhancing evidence support

        Return the improved synthesis maintaining the exact same JSON structure as the input synthesis.
        """
        response = await self.orchestrator.api.generate_content(prompt)
        return json.loads(response) if isinstance(response, str) else response

class ResearchOrchestrator:
    def __init__(self, rate_limiter, api):
        self.api = api
        self.rate_limiter = rate_limiter
        self.sources ={}
        self.agents ={
            AgentRole.QUERY_SPECIALIST: QueryAgent(api),
            AgentRole.WEB_EXPERT:WebResearchAgent(api, rate_limiter),
            AgentRole.FACT_CHECKER: FactCheckAgent(api),
            AgentRole.SYNTHESIS_EXPERT: SynthesisAgent(api),
            AgentRole.CRITIC:CriticAgent(api),
        }
        self.qa_system = QuestionAnswering(
            self.agents[AgentRole.WEB_EXPERT],
            self.agents[AgentRole.FACT_CHECKER]
        )
        self.improver = ResearchImprover(self)
        for agent in self.agents.values():
            if isinstance(agent, WebResearchAgent):
                agent.set_orchestrator(self)
    async def answer_question(self, question:str)->Dict[str, Any]:
        return await self.qa_system.answer_question(question)
    

    async def conduct_research(self, content_plan: str) -> Dict[str, Any]:
        logger.info(f"Starting research on: {content_plan}")

        # Find relevant stories

        # Generate queries
        queries = await self.agents[AgentRole.QUERY_SPECIALIST].generate_queries(content_plan)

        # Conduct parallel research
        findings = []

        # Create tasks for parallel execution
        tasks = []
        for query in sorted(queries, key=lambda x: x.priority, reverse=True):
            if query.agent == AgentRole.WEB_EXPERT:
                tasks.append(
                    self.agents[AgentRole.WEB_EXPERT].search_web(query))

        # Execute tasks in parallel
        results = await asyncio.gather(*tasks)

        # Process results
        for result in results:
            if isinstance(result, ResearchFinding):
                findings.append(result)

        # Verify findings
        verified_findings = []
        for finding in findings:
            verification = await self.agents[AgentRole.FACT_CHECKER].verify_information(finding)
            if verification['verification_status'] in ['verified', 'partially_verified']:
                verified_findings.append(finding)

        # Synthesize everything
        synthesis = await self.agents[AgentRole.SYNTHESIS_EXPERT].synthesize_findings(
            verified_findings, content_plan
        )

        # Critique research
        critique = await self.agents[AgentRole.CRITIC].critiqe_research(
            synthesis, verified_findings,
        )
        improved_synthesis, final_critique = await self.improver.improve_research(
            synthesis, critique, verified_findings,  content_plan
        )

        # Prepare final report
        report_data = {
            "content_plan": content_plan,
            "synthesis": improved_synthesis,
            "critique": final_critique,
            "improvement_history": {
                "initial_quality": critique['overall_quality'],
                "final_quality": final_critique['overall_quality'],
                "improvements_made": [s for s in final_critique.get('strengths', [])
                                    if s not in critique.get('strengths', [])]
            },
            "metadata": {
                "total_queries": len(queries),
                "total_findings": len(verified_findings),
                "quality_score": final_critique['overall_quality']
            },
            "sources": [self.sources[s].to_dict() for s in set().union(
                *[f.sources for f in verified_findings]
            ) if s in self.sources]
        }

        logger.info(f"Completed research on: {content_plan}")
        markdown_report = ReportFormatter.format_markdown_report(report_data)

        return {
            "json_report": report_data,
            "markdown_report": markdown_report
        }

