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

class BaseAgent:
    def __init__(self, role:AgentRole, api, ratelimiter=None):
        self.role = role
        self.api = api
        self.rate_limiter = ratelimiter
        self.memory: List[Dict[str, Any]]=[]
    async def think(self, context:str, )-> str:
        prompt=f"""
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
    def remember(self, information:Dict[str, Any]):
        self.memory.append(information)
    def recall(self, context:str)-> List[Dict[str, Any]]:
        return [m for m in self.memory if context.lower() in str(m).lower()]
    
class QueryAgent(BaseAgent):
    def __init__(self, api):
        super().__init__(AgentRole.QUERY_SPECIALIST, api)
    async def generate_queries(self, content_plan:str)-> List[ResearchQuery]:
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
            research_queries=[]
            for query_data in queries_data:
                try:
                    if not all(key in query_data for key in ["text", 'type', 'priority', 'agent']):
                        logger.error(f"Missing required fields in query data: {query_data}")
                        continue
                    if query_data['type'] not in ['web', 'fact-check', 'deep-dive']:
                        logger.error(f"Invalid query type: {query_data['type']}")
                        continue
                    if not (1<= query_data["priority"]<=5):
                        logger.error(f"Invalid priority vlaue: {query_data["priority"]}")
                        continue
                    try:
                        agent_role= next(role for role in AgentRole if role.value == query_data["agent"])
                    except StopIteration:
                        logger.error(f"Invalid agent role: {query_data["agent"]}")
                        continue
                    research_queries.append(ResearchQuery(text=query_data["text"],
                                                          type= query_data["type"], priority=query_data["priority"], agent=agent_role, context=content_plan))
                    
                except Exception as e:
                    logger.error(f"Error processing query data: {str(e)}")
            return research_queries
        except Exception as e:
            logger.error(f"Error generating queries: {str(e)}")
            return []
            
