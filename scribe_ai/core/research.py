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
            result[key]=dataclass_to_dict(value)
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
    title:str
    content:str
    source:str
    relevance_score:float
    emotional_impact:float
    verification_status:str
    metadata: Dict[str, Any]
    border_themes: Optional[List[str]]=None
    narrative_elements: Optional[Dict[str, Any]]=None
    def to_dict(self):
        return dataclass_to_dict(self)

@dataclass
class ResearchQuery:
    text:str
    type:str
    priority:int
    agent:AgentRole
    context:Optional[str]=None

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
    query:ResearchQuery
    content:str
    sources:List[str]
    urls:List[str]
    confidence:float
    agent:AgentRole
    metadata:Dict[str,Any] =None
    stories: List[Story]=None
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
    def __init__(self, url:str, title:str, content:str, author:Optional[str]=None, published_date:Optional[str]=None):
        self.id = str(uuid.uuid4())
        self.url = url
        self.title = title
        self.content = content
        self.published_date = published_date
        self.used_sections =[]
        self.credibility_score =0.0
        self.verification_status = None

    def add_used_section(self, section:str):
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
    def to_citation(self)->str:
        """Generate a citation string for the source."""
        citation = f"[{self.title}] ({self.url})"
        if self.author:
            citation += f"by {self.author}"
        if self.published_date:
            citation +=f"({self.published_date})"
        return citation