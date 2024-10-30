#text_processing.py, this is the api wraper

import logging
import json
import google.generativeai as genai
from .config import api_manager, api_parameters

import google.api_core.exceptions 
