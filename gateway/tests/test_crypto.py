import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cryptography.fernet import Fernet

# Set a fixed key before import so the module uses it consistently
_TEST_KEY = Fernet.generate_key().decode()
os.environ["FERNET_SECRET"] = _TEST_KEY

from crypto import encrypt_key, decrypt_key


def test_encrypt_decrypt_roundtrip():
    plain = "sk-ant-test-1234567890abcdef"
    enc = encrypt_key(plain)
    assert enc != plain
    assert decrypt_key(enc) == plain


def test_different_plaintexts_decrypt_correctly():
    assert decrypt_key(encrypt_key("key-A-value")) == "key-A-value"
    assert decrypt_key(encrypt_key("key-B-value")) == "key-B-value"
    assert encrypt_key("key-A-value") != encrypt_key("key-B-value")
