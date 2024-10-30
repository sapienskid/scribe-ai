#config.py

import os
from dotenv import load_dotenv
from cryptography.fernet import Fernet
from utils.api_storage import SecuredAPIStorage
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()
GOOGLE_SEARCH_API_KEY = os.getenv("GOOGLE_SEARCH_API_KEY")
GOOGGLE_SEARCH_ENGINE_ID = os.getenv("GOOGGLE_SEARCH_ENGINE_ID")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

ENCRYPTION_KEY = Fernet.generate_key()

api_storage = SecuredAPIStorage(ENCRYPTION_KEY)
class APIManager:
    def __init__(self):
        env_keys = self.load_env_keys("GEMINI_API_KEY")
        storage_keys = api_storage.load_keys()
        logger.info(f"Loaded {len(env_keys)} keys from env: {[k[:5] + '...' for k in env_keys]}")
        logger.info(f"Loaded {len(storage_keys)} keys from storage: {[k[:5] + '...' for k in storage_keys]}")
        self.api_keys = env_keys + storage_keys
        logger.info(f"Total keys: {len(self.api_keys)}")
        self.google_search_api_key = self.load_keys_from_env("GOOGLE_API_KEY")
    def load_keys_from_env(self, prefix):
        keys=[]
        main_key=os.getenv(prefix)
        if main_key:
            keys.append(main_key)

        for i in range(1, 6):
            key=os.getenv(f{prefix}_{i})
            if key:
                keys.append(key)
        return keys
    

    