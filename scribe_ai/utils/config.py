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
        self.google_search_api_keys = self.load_keys_from_env("GOOGLE_SEARCH_API_KEY")
        self.google_search_engine_id_keys = self.load_keys_from_env("GOOGLE_SEARCH_ENGINE_ID")
        self.google_api_keys= self.load_keys_from_env("GOOGLE_API_KEY")
    def load_keys_from_env(self, prefix):
        keys=[]
        main_key=os.getenv(prefix)
        if main_key:
            keys.append(main_key)

        for i in range(1, 6):
            key=os.getenv(f'{prefix}_{i}')
            if key:
                keys.append(key)
        return keys
    def get_current_key(self):
        return self.api_keys[0] if self.api_keys else None
    def switch_key(self):
        if len(self.api_keys)>1:
            current_key=self.api_keys[0]
            self.api_keys=self.api_keys[1:]+[self.api_keys[0]]
            new_key = self.api_keys[0]
            logger.info(f"Switched from {current_key[:5] + '...'} to {new_key[:5] + '...'}")
        else:
            logger.warning("No keys available for switching.")

    def add_key(self, new_key):
        if new_key not in self.api_keys:
            self.api_keys.append(new_key)
            self.save_keys()
    
    def remove_key(self, key_to_remove):
        if key_to_remove in self.api_keys:
            self.api_keys.remove(key_to_remove)
            self.save_keys()
    def update_key(self, old_key, new_key):
        if old_key in self.api_keys:
            index=self.api_keys.index(old_key)
            self.api_keys[index]=new_key
            self.save_keys()
    
    def save_keys(self):
        env_keys = set(self.load_keys_from_env("GEMINI_API_KEY"))
        keys_to_save =[key for key in self.api_keys if key not in env_keys]
        api_storage.save_keys(keys_to_save)
        api_storage.save_keys({
            'google_search_api_key': self.google_search_api_keys,
            'google_search_engine_id':self.google_search_engine_id_keys,
            'google_api_keys': self.google_api_keys

        })
    def add_google_key(self, key_type, new_key):
        if key_type =='search_api':
            if new_key not in self.google_search_api_keys:
                self.google_search_api_keys.append(new_key)
        elif key_type =='search_engine_id':
            if new_key not in self.google_search_engine_id_keys:
                self.google_search_engine_id_keys.append(new_key)
        elif key_type == 'api':
            if new_key not in self.google_api_keys:
                self.google_api_keys.append(new_key)
    def remove_google_key(self, key_type, key_to_remove):
        if key_type == 'search_api':
            if key_to_remove in self.google_search_api_keys:
                self.google_search_api_keys.remove(key_to_remove)
        elif key_type == 'search_engine_id':
            if key_to_remove in self.google_search_engine_id_keys:
                self.google_search_engine_id_keys.remove(key_to_remove)
        elif key_type == "api":
            if key_to_remove in self.google_api_keys:
                self.google_api_keys.remove(key_to_remove)

api_manager = APIManager()
api_parameters = {
    "temperature": 1.0,
    "top_p": 0.95,
    "top_k": 0.64,
}

def get_google_api_key():
    return api_manager.google_api_keys[0] if api_manager.google_api_keys else GOOGLE_API_KEY

def get_google_search_api_key():
    return api_manager.google_search_api_keys[0] if api_manager.google_search_api_keys else GOOGLE_SEARCH_API_KEY

def get_google_search_engine_id():
    return api_manager.google_search_engine_id_keys[0] if api_manager.google_search_engine_id_keys else GOOGGLE_SEARCH_ENGINE_ID
    