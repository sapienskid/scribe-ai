# config_manager.py

import json
from cryptography.fernet import Fernet
from .config import ENCRYPTION_KEY, api_manager, api_parameters
import os

