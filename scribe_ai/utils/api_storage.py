import json
from cryptography.fernet import Fernet

class SecuredAPIStorage:
    def __init__(self, encryption_key):
        self.fernet= Fernet(encryption_key)
        self.filename="api_keys.enc"
    def save_keys(self, api_keys):
        encrypted_data=self.fernet.encrypt(json.dumps(api_keys).encode())
        with open(self.filename, 'wb') as file:
            file.write(encrypted_data)
    def load_keys(self):
        try:
            with open(self.filename, 'rb') as file:
                encrypted_data=file.read()
            decrypted_data=self.fernet.decrypt(encrypted_data)
            return json.loads(decrypted_data)
        except FileNotFoundError:
            return {}
    
    def all_key(self, new_key):
        keys= self.load_keys()
        if new_key not in keys:
            keys.append(new_key)
            self.save_keys(keys)
    
    def remove_key(self,key_to_remove):
        keys=self.load_keys()
        if key_to_remove in keys:
            keys.remove(key_to_remove)
            self.save_keys(keys)

    def update_key(self, old_key, new_key):
        keys=self.load_keys()
        if old_key in keys:
            index=keys.index(old_key)
            keys[index]=new_key
            self.save_keys(keys)