from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple
import json
import asyncio
import logging
from datetime import datetime
from scribe_ai.core.research import ResearchOrchestrator
from scribe_ai.utils.rate_limiter import RateLimiter
rate_limiter = RateLimiter(15, 60)  # 5 requests per second
from pathlib import Path
import hashlib


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
@dataclass
class Agent:
    name: str
    role: str
    persona: str
    expertise: List[str]
    responsibilities: List[str]
    communication_style: str
    collaboration_preferences: List[str]

@dataclass
class Section:
    title: str
    description: str
    content: Optional[str] = None
    index: int = 0

@dataclass
class ContentPlan:
    topic: str
    target_audience: str
    content_type: str
    sections: List[Section]
    research_requirements: Dict[str, List[str]]
    required_expertise: List[str]
    content_goals: List[str]
    introduction: Optional[str] = None
    conclusion: Optional[str] = None

    @classmethod
    def from_api_response(cls, response_data: Dict[str, Any], topic: str) -> 'ContentPlan':
        try:
            if isinstance(response_data, str):
                response_data = json.loads(response_data)
                
            sections_data = response_data.get("sections", [])
            # Filter out introduction and conclusion from sections
            # filtered_sections = [
            #     section for section in sections_data 
            #     if section.get("title", "").lower() not in ["introduction", "conclusion"]
            # ]
            filtered_sections = [
                section for section in sections_data 
                if 'introduction' not in section.get('title', '').lower() and 'conclusion' not in section.get('title', '').lower()
            ]
            sections = [
                Section(
                    title=section.get("title"),
                    description=section.get("description"),
                    index=idx
                ) for idx, section in enumerate(filtered_sections)
            ]
            
            cleaned_data = {
                "topic": topic,
                "target_audience": response_data.get("target_audience", "General audience"),
                "content_type": response_data.get("content_type", "Article"),
                "sections": sections,
                "research_requirements": response_data.get("research_requirements", {}),
                "required_expertise": response_data.get("required_expertise", []),
                "content_goals": response_data.get("content_goals", [])
            }
            return cls(**cleaned_data)
        except Exception as e:
            logger.error(f"Error creating ContentPlan from API response: {str(e)}")
            return cls._create_default(topic)

    @classmethod
    def _create_default(cls, topic: str) -> 'ContentPlan':
        sections = [
            Section(title="Main Discussion", description=f"Detailed analysis of {topic}", index=0),
            Section(title="Key Aspects", description=f"Important aspects of {topic}", index=1),
            Section(title="Future Implications", description="Future outlook and implications", index=2)
        ]
        return cls(
            topic=topic,
            target_audience="General audience",
            content_type="Article",
            sections=sections,
            research_requirements={"general": ["Basic topic research", "Fact verification"]},
            required_expertise=["Topic knowledge", "Content writing"],
            content_goals=["Inform readers", "Provide clear explanation"]
        )

@dataclass
class Citation:
    source: str
    url: Optional[str]
    author: Optional[str]
    date: Optional[str]
    quote: Optional[str]
    context: str
    reference_id: str  # Added for in-text citations

@dataclass
class ResearchFinding:
    content: str
    citations: List[Citation]
    confidence_score: float
    verification_status: str

@dataclass
class AgentSuggestion:
    agent_name: str
    agent_role: str
    suggestion: str
    priority: float
    improvement_area: str
    reasoning: str
    suggested_citations: List[Citation]   
@dataclass
class SectionImprovement:
    original_content: str
    improved_content: str
    improvement_type: str
    agent_name: str
    reasoning: str
    changes_made: List[str]
    citations_added: List[Citation]  # Added to track citations
    confidence_score: float  # Added for better scoring

class ContentCreationSystem:
    def __init__(self, api, research_orchestrator):
        self.api = api
        self.research_orchestrator = research_orchestrator
        self.agents = []
        self.improvement_threshold = 0.8
        self.max_iterations = 3  # Increased for better improvements
        self.cache_dir = Path("research_cache")
        self.cache_dir.mkdir(exist_ok=True)
        self.citations = []  # Track all citations
        self._setup_system_instructions()
    def _setup_system_instructions(self):
        """Initialize system instructions for different content creation tasks"""
        self.system_instructions = {
            "topic_analysis": """You are an expert content strategist specializing in topic analysis.
            Your role is to deeply analyze topics to determine:
            - Required expertise and roles for content creation
            - Content complexity and scope
            - Special considerations and requirements
            - Optimal team composition
            
            Provide detailed, structured analysis in JSON format with clear reasoning for each recommendation.""",
            
            "agent_creation": """You are an AI team architect specializing in assembling expert content creation teams.
            Your role is to:
            - Create diverse teams with complementary skills
            - Define clear roles and responsibilities
            - Ensure expertise alignment with topic requirements
            - Design effective collaboration patterns
            
            Create detailed agent profiles in JSON format with specific expertise and communication styles.""",
            
            "content_planning": """You are an expert content strategist and outline architect.
            Your role is to:
            - Create comprehensive content plans
            - Structure logical section flow
            - Define clear research requirements
            - Align content with audience needs
            - Establish measurable content goals
            
            Deliver structured content plans in JSON format with clear section progression and research needs.""",
            
            "section_creation": """You are an expert content writer specializing in creating cohesive, well-researched content.
            Your role is to:
            - Create engaging, audience-appropriate content
            - Integrate research findings naturally
            - Maintain narrative flow between sections
            - Support key points with citations
            - Ensure content goals are met
            
            Focus on creating clear, engaging content that builds on previous sections and sets up upcoming topics.""",
            
            "content_improvement": """You are an expert content editor and improvement specialist.
            Your role is to:
            - Analyze content for improvement opportunities
            - Ensure research integration
            - Verify citation accuracy
            - Enhance readability and flow
            - Maintain consistency across sections
            
            Provide specific, actionable improvements while preserving the original content's intent."""
        }
    
    async def analyze_topic_requirements(self, topic: str) -> Dict[str, Any]:
        """Analyze topic requirements with system instruction guidance"""
        self.api.set_system_instruction(self.system_instructions["topic_analysis"])
        
        prompt = {
            "role": "user",
            "content": f"""Analyze the topic '{topic}' and provide requirements in JSON format with:
            - required_roles: list of necessary team roles
            - expertise_areas: list of required knowledge areas
            - content_complexity: difficulty level
            - special_requirements: any special considerations
            - recommended_team_size: optimal number of team members"""
        }

        try:
            response = await self.api.generate_content(json.dumps(prompt))
            self.api.reset_chat()  # Reset for next task
            if response:
                return json.loads(response) if isinstance(response, str) else response
            return self._get_default_requirements()
        except Exception as e:
            logger.error(f"Error in topic analysis: {str(e)}")
            return self._get_default_requirements()

    async def create_agents(self, topic: str) -> List[Agent]:
        """Create agents with system instruction guidance"""
        self.api.set_system_instruction(self.system_instructions["agent_creation"])
        
        try:
            self.agents = []
            requirements = await self.analyze_topic_requirements(topic)
            
            agent_prompt = {
                "role": "user",
                "content": f"""Create a team of content creation agents for the topic '{topic}'.
                Requirements: {json.dumps(requirements)}
                Return a JSON array of agents with these fields for each:
                - name: unique name
                - role: specific role based on requirements
                - persona: personality description
                - expertise: list of knowledge areas
                - responsibilities: list of duties
                - communication_style: how they communicate
                - collaboration_preferences: how they work with others"""
            }

            response = await self.api.generate_content(json.dumps(agent_prompt))
            self.api.reset_chat()  # Reset for next task
            
            if not response:
                return await self._create_fallback_agents(topic)

            agents_data = json.loads(response) if isinstance(response, str) else response
            if isinstance(agents_data, dict) and "agents" in agents_data:
                agents_data = agents_data["agents"]
            
            self.agents = [Agent(**agent_data) for agent_data in agents_data]
            return self.agents

        except Exception as e:
            logger.error(f"Error in agent creation: {str(e)}")
            return await self._create_fallback_agents(topic)
    
    async def collect_agent_suggestions(
        self,
        section: Section,
        content: str,
        research_findings: Dict[str, Any],
        content_plan: ContentPlan,
        context: Dict[str, Any]
    ) -> List[AgentSuggestion]:
        """Collect improvement suggestions from all agents"""
        suggestions = []

        for agent in self.agents:
            suggestion_prompt = {
                "role": "user",
                "content": f"""As {agent.role} with expertise in {', '.join(agent.expertise)},
                analyze this content and provide suggestions for improvement:

                Section: {section.title}
                Current Content: {content}

                Context:
                Previous Sections: {json.dumps(context.get('previous_sections', []), indent=2)}
                Upcoming Sections: {json.dumps(context.get('upcoming_sections', []), indent=2)}

                Research Findings: {json.dumps(research_findings)}

                Consider:
                - Target audience: {content_plan.target_audience}
                - Content goals: {', '.join(content_plan.content_goals)}
                - Your specific expertise areas
                - Research integration opportunities

                Return a JSON object with:
                {{
                    "suggestion": "detailed improvement suggestion",
                    "priority": 0.95,
                    "improvement_area": "specific area of improvement",
                    "reasoning": "why this improvement matters",
                    "suggested_citations": [
                        {{
                            "source": "source name",
                            "author": "author name",
                            "date": "publication date",
                            "url": "source url",
                            "quote": "relevant quote",
                            "context": "where/how to use"
                        }}
                    ]
                }}"""
            }

            try:
                response = await self.api.generate_content(json.dumps(suggestion_prompt))
                if isinstance(response, str):
                    response = json.loads(response)

                if response and isinstance(response, dict):
                    # Create Citation objects from suggestions
                    citations = []
                    for cite_data in response.get("suggested_citations", []):
                        ref_id = f"ref_{len(self.citations) + len(citations) + 1}"
                        citation = Citation(
                            source=cite_data.get("source", ""),
                            author=cite_data.get("author", ""),
                            date=cite_data.get("date", ""),
                            url=cite_data.get("url", ""),
                            quote=cite_data.get("quote", ""),
                            context=cite_data.get("context", ""),
                            reference_id=ref_id
                        )
                        citations.append(citation)

                    suggestion = AgentSuggestion(
                        agent_name=agent.name,
                        agent_role=agent.role,
                        suggestion=response.get("suggestion", ""),
                        priority=response.get("priority", 0.0),
                        improvement_area=response.get("improvement_area", ""),
                        reasoning=response.get("reasoning", ""),
                        suggested_citations=citations
                    )
                    suggestions.append(suggestion)

            except Exception as e:
                logger.error(f"Error collecting agent suggestion: {str(e)}")

        return sorted(suggestions, key=lambda x: x.priority, reverse=True)
    async def create_content_plan(self, topic: str) -> ContentPlan:
        try:
            if not self.agents:
                await self.create_agents(topic)

            plan_prompt = {
                "role": "user",
                "content": f"""Create a detailed content plan for '{topic}'.
                Return JSON with:
                - target_audience: intended readers
                - content_type: type of content
                - sections: array of sections with title and description
                - research_requirements: needed research by area
                - required_expertise: needed knowledge areas
                - content_goals: what the content should achieve"""
            }

            response = await self.api.generate_content(json.dumps(plan_prompt))
            if not response:
                logger.warning("No API response for content plan, using default")
                return ContentPlan._create_default(topic)

            return ContentPlan.from_api_response(response, topic)

        except Exception as e:
            logger.error(f"Error creating content plan: {str(e)}")
            return ContentPlan._create_default(topic)
        
    async def research_topic(self, topic: str, content_plan: ContentPlan) -> Dict[str, Any]:
        """Conduct comprehensive research for the topic using ResearchOrchestrator"""
        research_prompt = {
            "topic": topic,
            "content_type": content_plan.content_type,
            "audience": content_plan.target_audience,
            "research_requirements": content_plan.research_requirements,
            "sections": [{"title": s.title, "description": s.description} for s in content_plan.sections]
        }
        
        research_results = await self.research_orchestrator.conduct_research(json.dumps(research_prompt))
        return research_results

    async def _extract_key_points(self, content: str) -> List[str]:
        """Extract key points from section content for context building"""
        if not content:
            return []
            
        try:
            prompt = {
                "role": "user",
                "content": f"Extract 3-5 key points from this content. Return them as a JSON object with a 'key_points' array:\n\n{content}"
            }
            
            response = await self.api.generate_content(json.dumps(prompt))
            if isinstance(response, str):
                try:
                    response = json.loads(response)
                except json.JSONDecodeError:
                    logger.error("Failed to parse response as JSON")
                    return []
                    
            if isinstance(response, dict):
                return response.get("key_points", [])
            return []
            
        except Exception as e:
            logger.error(f"Error extracting key points: {str(e)}")
            return []

    async def improve_section_content(
        self,
        section: Section,
        content: str,
        research_findings: Dict[str, Any],
        content_plan: ContentPlan,
        context: Dict[str, Any]
    ) -> str:
        """Improve content based on collected agent suggestions"""
        current_content = content
        
        # Collect all agent suggestions first
        suggestions = await self.collect_agent_suggestions(
            section, current_content, research_findings, content_plan, context
        )

        # Create improvement prompt incorporating all suggestions
        if suggestions:

            improvement_prompt = {
                "role": "user",
                "content": f"""Improve the following content based on these expert suggestions:

                Section: {section.title}
                Current Content: {current_content}
                
                Context:
                Previous Sections: {json.dumps(context.get('previous_sections', []), indent=2, ensure_ascii=False)}
                Upcoming Sections: {json.dumps(context.get('upcoming_sections', []), indent=2, ensure_ascii=False)}
                
                Research Findings: {json.dumps(research_findings, ensure_ascii=False)}
                
                Consider:
                - Target audience: {content_plan.target_audience}
                - Content goals: {', '.join(content_plan.content_goals)}
                - Narrative flow and transitions
                - Research integration with proper citations

                Expert Suggestions:
                {json.dumps([{
                    # Add the rest of the code here
                }], ensure_ascii=False)}
                """
            }

            try:
                response = await self.api.generate_content(json.dumps(improvement_prompt))
                if isinstance(response, str):
                    response = json.loads(response)

                if response and isinstance(response, dict):
                    improved_content = response.get("improved_content", current_content)
                    
                    # Add all suggested citations to the global list
                    for suggestion in suggestions:
                        self.citations.extend(suggestion.suggested_citations)
                    
                    return improved_content

            except Exception as e:
                logger.error(f"Error applying improvements: {str(e)}")

        return current_content

    def _get_cache_filename(self, topic: str) -> Path:
        """Generate a unique filename for caching research results"""
        # Create a hash of the topic to use as filename
        topic_hash = hashlib.md5(topic.encode()).hexdigest()
        return self.cache_dir / f"research_{topic_hash}.json"

    async def _get_cached_research(self, topic: str) -> Optional[Dict[str, Any]]:
        """Retrieve cached research results if they exist"""
        cache_file = self._get_cache_filename(topic)
        if cache_file.exists():
            try:
                with cache_file.open('r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error reading cache file: {str(e)}")
        return None

    async def _cache_research_results(self, topic: str, results: Dict[str, Any]):
        """Save research results to cache"""
        cache_file = self._get_cache_filename(topic)
        try:
            with cache_file.open('w') as f:
                json.dump(results, f)
        except Exception as e:
            logger.error(f"Error writing to cache file: {str(e)}")

    async def create_section_with_context(
        self,
        section: Section,
        content_plan: ContentPlan,
        research_results: Dict[str, Any],
        completed_sections: List[Section]
    ) -> str:
        """Create section content with system instruction guidance"""
        self.api.set_system_instruction(self.system_instructions["section_creation"])
        
        current_index = section.index
        upcoming_sections = [s for s in content_plan.sections if s.index > current_index]
        
        context = {
            "topic": content_plan.topic,
            "target_audience": content_plan.target_audience,
            "content_goals": content_plan.content_goals,
            "previous_sections": [
                {
                    "title": s.title,
                    "content": s.content,
                    "key_points": await self._extract_key_points(s.content) if s.content else []
                }
                for s in completed_sections
            ],
            "upcoming_sections": [
                {
                    "title": s.title,
                    "description": s.description
                }
                for s in upcoming_sections
            ]
        }

        prompt = {
            "role": "user",
            "content": f"""Create content for section '{section.title}' with the following context:
            {json.dumps(context, indent=2)}
            
            Research Findings:
            {json.dumps(research_results.get(section.title, {}), indent=2)}"""
        }

        try:
            response = await self.api.generate_content(json.dumps(prompt))
            self.api.reset_chat()  # Reset for next task
            
            if not response:
                return f"Content for {section.title} could not be generated."
            
            initial_content = response if isinstance(response, str) else json.dumps(response)
            
            # Improve content with improvement system instruction
            self.api.set_system_instruction(self.system_instructions["content_improvement"])
            improved_content = await self.improve_section_content(
                section,
                initial_content,
                research_results,
                content_plan,
                context
            )
            
            return improved_content

        except Exception as e:
            logger.error(f"Error creating section content: {str(e)}")
            return f"Error generating content for {section.title}"

    async def create_section_with_research(
        self,
        section: Section,
        content_plan: ContentPlan,
        research_results: Dict[str, Any],
        completed_sections: List[Section]
    ) -> str:
        """Create and improve section content with research integration"""
        initial_content = await self.create_section_with_context(
            section,
            content_plan,
            research_results,
            completed_sections
        )

        improved_content = await self.improve_section_content(
            section,
            initial_content,
            research_results,
            content_plan,
            {
                "previous_sections": [
                    {"title": s.title, "content": s.content}
                    for s in completed_sections
                ],
                "upcoming_sections": [
                    {"title": s.title, "description": s.description}
                    for s in content_plan.sections
                    if s.index > section.index
                ]
            }
        )

        return improved_content
    async def create_introduction_conclusion(
        self,
        content_plan: ContentPlan,
        research_findings: Dict[str, Any],
        all_sections_content: List[Dict[str, Any]]
    ) -> Tuple[str, str]:
        """Create introduction and conclusion based on all section content"""
        intro_prompt = {
            "role": "user",
            "content": f"""Create an introduction for this content:

            Topic: {content_plan.topic}
            Target Audience: {content_plan.target_audience}
            Content Goals: {', '.join(content_plan.content_goals)}

            Sections Overview:
            {json.dumps(all_sections_content, indent=2)}

            Research Findings:
            {json.dumps(research_findings, indent=2)}

            Return an engaging introduction that:
            1. Hooks the reader
            2. Provides context
            3. Outlines key points
            4. Sets expectations for the content"""
        }

        conclusion_prompt = {
            "role": "user",
            "content": f"""Create a conclusion for this content:

            Topic: {content_plan.topic}
            Target Audience: {content_plan.target_audience}
            Content Goals: {', '.join(content_plan.content_goals)}

            Full Content:
            {json.dumps(all_sections_content, indent=2)}

            Research Findings:
            {json.dumps(research_findings, indent=2)}

            Return a conclusion that:
            1. Summarizes key points
            2. Reinforces main messages
            3. Provides closure
            4. Suggests next steps or implications"""
        }

        try:
            intro_response = await self.api.generate_content(json.dumps(intro_prompt))
            conclusion_response = await self.api.generate_content(json.dumps(conclusion_prompt))

            introduction = intro_response if isinstance(intro_response, str) else json.dumps(intro_response)
            conclusion = conclusion_response if isinstance(conclusion_response, str) else json.dumps(conclusion_response)

            # Improve introduction and conclusion with agent suggestions
            improved_intro = await self.improve_section_content(
                Section("Introduction", "Introduction section"),
                introduction,
                research_findings,
                content_plan,
                {"upcoming_sections": all_sections_content}
            )

            improved_conclusion = await self.improve_section_content(
                Section("Conclusion", "Conclusion section"),
                conclusion,
                research_findings,
                content_plan,
                {"previous_sections": all_sections_content}
            )

            return improved_intro, improved_conclusion

        except Exception as e:
            logger.error(f"Error creating introduction/conclusion: {str(e)}")
            return "", ""
    async def create_content_with_research(self, topic: str) -> str:
        """Main method to create researched and improved content"""
        try:
            await self.create_agents(topic)
            content_plan = await self.create_content_plan(topic)

            # Check for cached research results
            research_results = await self._get_cached_research(topic)
            if not research_results:
                logger.info(f"No cached research found for topic: {topic}")
                research_results = await self.research_topic(topic, content_plan)
                await self._cache_research_results(topic, research_results)
            else:
                logger.info(f"Using cached research results for topic: {topic}")

            # Generate content for each section
            completed_sections = []
            all_sections_content = []

            for section in content_plan.sections:
                content = await self.create_section_with_research(
                    section,
                    content_plan,
                    research_results,
                    completed_sections
                )
                section.content = content
                completed_sections.append(section)
                all_sections_content.append({
                    "title": section.title,
                    "content": content,
                    "key_points": await self._extract_key_points(content)
                })
                logger.info(f"Completed section: {section.title}")

            # Create introduction and conclusion based on all content
            introduction, conclusion = await self.create_introduction_conclusion(
                content_plan,
                research_results,
                all_sections_content
            )
            
            content_plan.introduction = introduction
            content_plan.conclusion = conclusion

            return self.generate_markdown_with_citations(content_plan, research_results)

        except Exception as e:
            logger.error(f"Error in content creation: {str(e)}")
            raise
    
    
    def generate_markdown_with_citations(
        self,
        content_plan: ContentPlan,
        research_results: Dict[str, Any]
    ) -> str:
        """Generate well-formatted markdown with proper spacing and citations"""
        try:
            markdown_content = []
            
            # Title with proper spacing
            markdown_content.extend([
                f"# {content_plan.topic}",
                "\n"
            ])
            
            # Introduction if available
            if content_plan.introduction:
                markdown_content.extend([
                    content_plan.introduction,
                    "\n\n"
                ])
            
            # Main sections with proper formatting
            for section in content_plan.sections:
                if section.content:
                    # Process content with citations
                    content_with_citations = section.content
                    for citation in self.citations:
                        if citation.context in section.content:
                            citation_text = f" [{citation.reference_id}]"
                            content_with_citations = content_with_citations.replace(
                                citation.context,
                                f"{citation.context}{citation_text}"
                            )
                    
                    markdown_content.extend([
                        f"## {section.title}",
                        "",  # Empty line after heading
                        content_with_citations,
                        "\n"  # Space between sections
                    ])
            
            # Conclusion if available
            if content_plan.conclusion:
                markdown_content.extend([
                    "## Conclusion",
                    "",  # Empty line after heading
                    content_plan.conclusion,
                    "\n"
                ])
            
            # References section
            if self.citations:
                markdown_content.extend([
                    "## References",
                    "",  # Empty line after heading
                    *[self._format_citation(citation) for citation in self.citations],
                    ""  # Final newline
                ])
            
            # Join with newlines to create proper markdown spacing
            return "\n".join(markdown_content)

        except Exception as e:
            logger.error(f"Error generating markdown: {str(e)}")
            return f"Error generating markdown for {content_plan.topic}"

    def _format_citation(self, citation: Citation) -> str:
        """Format a single citation in academic style with reference ID"""
        try:
            # Use APA style formatting
            authors = citation.author or "No author"
            date = f"({citation.date})" if citation.date else "(n.d.)"
            title = citation.source or "Untitled"
            url = citation.url or ""
            
            citation_text = f"[{citation.reference_id}] {authors}. {date}. {title}."
            if url:
                citation_text += f" Retrieved from {url}"
            
            if citation.quote:
                citation_text += f"\n   Quote: \"{citation.quote}\""
                
            return citation_text + "\n"
            
        except Exception as e:
            logger.error(f"Error formatting citation: {str(e)}")
            return "Error formatting citation"

async def main():
    try:
        from scribe_ai.utils.text_processing import GeminiAPI
        
        api = GeminiAPI(use_json=True)
        research_orchestrator = ResearchOrchestrator(rate_limiter, api)
        system = ContentCreationSystem(api, research_orchestrator)
        
        topic = "The Impact of Artificial Intelligence on Healthcare"
        markdown_content = await system.create_content_with_research(topic)
        
        with open("generated_content.md", "w") as f:
            f.write(markdown_content)
            
        print("\nContent generated successfully with research and citations!")
        print("\nPreview:")
        print(markdown_content[:500] + "..." if len(markdown_content) > 500 else markdown_content)

    except Exception as e:
        logger.error(f"Error in main: {str(e)}")
        raise

if __name__ == "__main__":
    asyncio.run(main())