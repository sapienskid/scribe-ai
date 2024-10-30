# config_manager.py

import json
from cryptography.fernet import Fernet
from .config import ENCRYPTION_KEY, api_manager, api_parameters
import os

class ConfigManager:
    def __init__(self):
        self.fernet = Fernet(ENCRYPTION_KEY)
    def export_config_to_string(self):
        config ={
            "api_keys": api_manager.api_keys,
            "api_parameters": api_parameters,
            "google_search_api_keys": api_manager.google_search_api_keys, 
            "google_search_engine_id_keys": api_manager.google_search_engine_id_keys,
            "google_api_keys": api_manager.google_api_keys
        }
        encrypted_data = self.fernet.encrypt(json.jumps(config).encode())
        return encrypted_data.decode()
    def import_config_from_string(self, encrypted_string):
        decrypted_data= self.fernet.decrypt(encrypted_string.encode())
        config = json.loads(decrypted_data)
        api_manager.api_keys = config["api_keys"]
        api_manager.google_search_api_keys = config["google_search_api_keys"]
        api_manager.google_search_engine_id_keys = config["google_search_engine_id_keys"]
        api_manager.google_api_keys = config["google_api_keys"]
        api_manager.save_keys()
        global api_parameters
        api_parameters.update(config["api_parameters"])
    
    def export_config(self, filename):
        with open(filename, 'w') as f:
            f.write(self.export_config_to_string())

    def import_config(self, filename):
        with open(filename, 'r') as f:
            self.import_config_from_string(f.read())
    
config_manager= ConfigManager()