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
    index: int =0

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
    def from_api_response(cls, response_data:Dict[str, Any], topic:str)->'ContentPlan':
        try:
            if isinstance(response_data, str):
                response_data = json.loads(response_data)
            sections_data = response_data.get('sections', [])
            filtered_sections = [
                section for section in sections_data 
                if 'introduction' not in section.get('title', '').lower() and 'conclusion' not in section.get('title', '').lower()
            ]
            sections = [
                Section(
                    title = section.get("title"),
                    description= section.get('description'),
                    index= idx
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
    def _create_default(cls, topic:str)->'ContentPlan':
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
            