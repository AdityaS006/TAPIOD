import os
from cryptography.fernet import Fernet


def _get_fernet() -> Fernet:
    secret = os.getenv("FERNET_SECRET")
    if not secret:
        secret = Fernet.generate_key().decode()
        os.environ["FERNET_SECRET"] = secret
        print(
            f"[WARNING] FERNET_SECRET not set — generated ephemeral key: {secret}\n"
            "[WARNING] Keys stored this session will not survive a restart. "
            "Set FERNET_SECRET in gateway/.env"
        )
    return Fernet(secret.encode() if isinstance(secret, str) else secret)


def encrypt_key(plain: str) -> str:
    return _get_fernet().encrypt(plain.encode()).decode()


def decrypt_key(enc: str) -> str:
    return _get_fernet().decrypt(enc.encode()).decode()
