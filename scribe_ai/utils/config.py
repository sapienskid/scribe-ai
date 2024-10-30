#config.py

import os
from dotenv import load_dotenv
from cryptography.fernet import Fernet
from utils.api_storage import SecuredAPIStorage
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)