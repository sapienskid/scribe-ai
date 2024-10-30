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