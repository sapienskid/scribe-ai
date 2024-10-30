#text_processing.py, this is the api wraper

import logging
import json
import google.generativeai as genai
from .config import api_manager, api_parameters

import google.api_core.exceptions 

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def configure_api(api_key):
    current_key = api_manager.get_current_key()

    try:
        genai.configure(api_key=current_key)
        logger.info(f"Configured API with key: {current_key[:5] + '...'}")
    except Exception as e:
        logger.error(f"Error configuring API with key {current_key[:5]}...: {str(e)}")
        raise

configure_api()