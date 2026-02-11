import os

import pytest

# Ensure encryption key is set before import
os.environ.setdefault("ENCRYPTION_KEY", "dGVzdGtleS0xMjM0NTY3ODkwMTIzNDU2")

from src.services.encryption import decrypt_key, encrypt_key


def test_encrypt_decrypt_roundtrip():
    plaintext = "sk-ant-api03-test-key"
    encrypted = encrypt_key(plaintext)
    assert encrypted != plaintext
    decrypted = decrypt_key(encrypted)
    assert decrypted == plaintext


def test_encrypt_different_values_produce_different_ciphertexts():
    a = encrypt_key("key-a")
    b = encrypt_key("key-b")
    assert a != b


def test_decrypt_wrong_ciphertext_fails():
    with pytest.raises(Exception):
        decrypt_key("not-a-valid-ciphertext")


def test_encrypt_empty_string():
    encrypted = encrypt_key("")
    decrypted = decrypt_key(encrypted)
    assert decrypted == ""


def test_encrypt_long_key():
    long_key = "sk-" + "x" * 500
    encrypted = encrypt_key(long_key)
    assert decrypt_key(encrypted) == long_key
