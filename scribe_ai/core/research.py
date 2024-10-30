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