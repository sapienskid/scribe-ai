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
    