import base64
import secrets
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

class EncryptionManager:
    @staticmethod
    def generate_key():
        """Generate a new encryption key for an environment."""
        return Fernet.generate_key().decode()
    
    @staticmethod
    def derive_key_from_password(password: str, salt: bytes = None):
        """Derive an encryption key from a password using PBKDF2."""
        if salt is None:
            salt = secrets.token_bytes(32)
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key, salt
    
    @staticmethod
    def encrypt_value(value: str, key: str):
        """Encrypt a value using the provided key."""
        try:
            fernet = Fernet(key.encode() if isinstance(key, str) else key)
            encrypted_value = fernet.encrypt(value.encode())
            return base64.b64encode(encrypted_value).decode()
        except Exception as e:
            raise ValueError(f"Encryption failed: {str(e)}")
    
    @staticmethod
    def decrypt_value(encrypted_value: str, key: str):
        """Decrypt a value using the provided key."""
        try:
            fernet = Fernet(key.encode() if isinstance(key, str) else key)
            decoded_value = base64.b64decode(encrypted_value.encode())
            decrypted_value = fernet.decrypt(decoded_value)
            return decrypted_value.decode()
        except Exception as e:
            raise ValueError(f"Decryption failed: {str(e)}")
    
    @staticmethod
    def generate_api_token():
        """Generate a secure API token."""
        return secrets.token_urlsafe(32)
    
    @staticmethod
    def verify_key_format(key: str):
        """Verify that a key is in the correct format for Fernet."""
        try:
            Fernet(key.encode() if isinstance(key, str) else key)
            return True
        except:
            return False