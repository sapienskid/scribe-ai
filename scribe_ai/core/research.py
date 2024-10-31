import aiohttp
import json
import logging
import os
from dotenv import load_dotenv
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, fields
from enum import Enum
import uuid
from datetime import datetime
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
    STORYTELLER = "Narrative Specialist"


@dataclass
class Story:
    title: str
    content: str
    source: str
    relevance_score: float
    emotional_impact: float
    verification_status: str
    metadata: Dict[str, Any]
    border_themes: Optional[List[str]] = None
    narrative_elements: Optional[Dict[str, Any]] = None

    def to_dict(self):
        return dataclass_to_dict(self)


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
    stories: List[Story] = None

    def to_dict(self):
        return {
            "query": self.query.to_dict(),
            "content": self.content,
            "sources": self.sources,
            "urls": self.urls,
            "confidence": self.confidence,
            "agent": self.agent.value,
            "metadata": self.metadata,
            "stories": [story.to_dict() for story in self.stories]
        }


class Source:
    def __init__(self, url: str, title: str, content: str, author: Optional[str] = None, published_date: Optional[str] = None):
        self.id = str(uuid.uuid4())
        self.url = url
        self.title = title
        self.content = content
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
            confidence=analysis['confidenc'],
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

    async def synthesize_findings(self, findings: List[ResearchFinding], content_plan: str, stories: List[Story]) -> Dict[str, Any]:
        thinking = await self.think(f"Synthesizing {len(findings)} findings and {len(stories)} stories for :{content_plan}")
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
Number of stories: {len(stories)}
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

    async def critiqe_research(self, synthesis: Dict[str, Any], findings: List[ResearchFinding], stories: List[Story]) -> Dict[str, Any]:
        prompt = f"""
        Critically analyze this research:
        Synthesis: {json.dumps(synthesis)}
        Findings: {json.dumps([f.to_dict() for f in findings])}
        Stories: {json.dumps([s.to_dict() for s in stories])}
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


class StoryFinder:
    def __init__(self, api):
        self.api = api

    async def find_relevant_stories(self, topic: str) -> List[Story]:
        prompt = f"""
        Find compelling true stories related to: {topic}

        Search for stories that:
        1. Illustrate key aspects of the topic
        2. Have emotional resonance
        3. Come from verifiable sources
        4. Are recent and relevant

        Return exactly 3 stories, each as a complete JSON object with these exact fields:
        {{
            "title": "story title",
            "content": "full story text",
            "source": "where the story comes from",
            "relevance_score": 0.9,
            "emotional_impact": 0.8,
            "verification_status": "verified",
            "metadata": {{"key": "value"}},
            "broader_themes": ["theme1", "theme2"],
            "narrative_elements": {{
                "hooks": ["hook1", "hook2"],
                "key_points": ["point1", "point2"],
                "suggestions": ["suggestion1", "suggestion2"]
            }}
        }}

        Format as a JSON array of exactly 3 story objects. Ensure complete JSON validity.
        """
        try:
            response = await self.api.generate_content(prompt)
            if isinstance(response, str):
                try:
                    stories_data = json.loads(response)
                except json.JSONDecodeError as e:
                    logger.error(
                        f"JSON parsing error in find_relevant_stories: {str(e)}")
                    logger.debug(f"Problematic response: {response[:1000]}...")
                    stories_data = self._create_fallback_stories(topic)
                else:
                    stories_data = response
                if not isinstance(stories_data, list):
                    logger.error(f"Stories data is not a list")
                    stories_data = self._create_fallback_stories(topic)

                stories = []
                valid_fields = {f.name for f in fields[Story]}

                for story_data in stories_data:
                    try:
                        processed_data = {
                            "title": story_data.get("title", "Untitled Story"),
                            "content": story_data.get("content", "No content available"),
                            "source": story_data.get("source", "Unknown source"),
                            "relevance_score": float(story_data.get("relevance_score", 0.5)),
                            "emotional_impact": float(story_data.get("emotional_impact", 0.5)),
                            "verification_status": story_data.get("verification_status", "needs_verification"),
                            "metadata": story_data.get("metadata", {}),
                            "broader_themes": story_data.get("broader_themes", []),
                            "narrative_elements": story_data.get("narrative_elements", {
                                "hooks": [],
                                "key_points": [],
                                "suggestions": []
                            })
                        }
                        filtered_data = {
                            k: v for k, v in processed_data.items() if k in valid_fields
                        }
                        story = Story(**filtered_data)
                        stories.append(story)
                    except Exception as e:
                        logger.error(f"Error processing story data: {str(e)}")
                
                if not stories:
                    stories = [self._create_fallback_story(topic)]
        except Exception as e:
            logger.error(f"Error in find_relevant_stories: {str(e)}")
            return [self._create_fallback_story(topic)]
    def _create_fallback_stories(self, topic: str) -> List[Dict]:
        """Create fallback story data when normal processing fails."""
        return [{
            "title": f"Story about {topic}",
            "content": f"A story related to {topic} will be available soon.",
            "source": "System generated",
            "relevance_score": 0.5,
            "emotional_impact": 0.5,
            "verification_status": "needs_verification",
            "metadata": {"generated": "fallback"},
            "broader_themes": [topic],
            "narrative_elements": {
                "hooks": ["Pending"],
                "key_points": ["Pending"],
                "suggestions": ["Pending"]
            }
        }]
    def _create_fallback_story(self, topic: str) -> Story:
        """Create a single fallback Story instance."""
        return Story(
            title=f"Story about {topic}",
            content=f"A story related to {topic} will be available soon.",
            source="System generated",
            relevance_score=0.5,
            emotional_impact=0.5,
            verification_status="needs_verification",
            metadata={"generated": "fallback"},
            broader_themes=[topic],
            narrative_elements={
                "hooks": ["Pending"],
                "key_points": ["Pending"],
                "suggestions": ["Pending"]
            }
        )
    

class StorytellerAgent(BaseAgent):
    def __init__(self, api):
        super().__init__(AgentRole.STORYTELLER, api)
        self.story_finder = StoryFinder(api)
    
    async def find_stories(self, topic: str)->List[Story]:
        thinking = await self.think(f"Finding compelling stories about: {topic}")
        stories = await self.story_finder.find_relevant_stories(topic)
        enhanced_stories = []
        for story in stories:
            enhancement_prompt = f"""
            Based on this thinking: {thinking}
            Analyze and enhance this story:
            {json.dumps(story.__dict__)}

            1. Verify key facts if possible
            2. Identify emotional hooks
            3. Connect to broader themes
            4. Suggest narrative improvements

            Return enhanced story as JSON with the following structure, ensuring proper JSON formatting:
            {{
                "title": "story title",
                "content": "full story text",
                "source": "source name",
                "relevance_score": 0.0-1.0,
                "emotional_impact": 0.0-1.0,
                "verification_status": "verified or needs_verification",
                "metadata": {{}},
                "broader_themes": ["theme1", "theme2"],
                "narrative_elements": {{
                    "hooks": [],
                    "key_points": [],
                    "suggestions": []
                }}
            }}
            """
            try:
                response = await self.api.generate_content(enhancement_prompt)
                if isinstance(response, str):
                    try:
                        enhanced_story_data = json.loads(response)
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON parsing error: {str(e)}")
                        logger.debug(f"Problematic response: {response}")
                        enhanced_story_data= story.__dict__
                else:
                    enhanced_story_data = response
                valid_fields = {f.name for f in fields(story)}
                filtered_data ={
                    k:v for k, v in enhanced_story_data.items() if k in valid_fields
                }
                for field in valid_fields:
                    if field not in filtered_data:
                        filtered_data[field]=getattr(story, field)
                enhanced_story = Story(**filtered_data)
                enhanced_stories.append(enhanced_story)
            except Exception as e:
                logger.error(f"Error enhancing story: {str(e)}")
                enhanced_stories.append(story)
            
        return enhanced_stories
    
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
        
