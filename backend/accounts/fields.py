from django.db import models
from django.conf import settings
from cryptography.fernet import Fernet, InvalidToken


# helper cipher based on configured key
def _get_fernet():
    key = getattr(settings, 'FIELD_ENCRYPTION_KEY', None)
    if not key:
        raise ValueError('FIELD_ENCRYPTION_KEY must be set in settings')
    return Fernet(key)


def _encrypt_bytes(value: bytes) -> bytes:
    return _get_fernet().encrypt(value)


def _decrypt_bytes(value: bytes) -> bytes:
    try:
        return _get_fernet().decrypt(value)
    except InvalidToken:
        # not encrypted or wrong key
        return value


class EncryptedCharField(models.CharField):
    """CharField that encrypts its value before saving to the database."""

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value is None:
            return value
        encrypted = _encrypt_bytes(value.encode('utf-8'))
        return encrypted.decode('utf-8')

    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        data = value.encode('utf-8')
        decrypted = _decrypt_bytes(data)
        return decrypted.decode('utf-8')

    def to_python(self, value):
        if isinstance(value, str):
            data = value.encode('utf-8')
            try:
                return _decrypt_bytes(data).decode('utf-8')
            except Exception:
                return value
        return value


class EncryptedTextField(models.TextField):
    """TextField that encrypts its value."""

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value is None:
            return value
        encrypted = _encrypt_bytes(value.encode('utf-8'))
        return encrypted.decode('utf-8')

    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        data = value.encode('utf-8')
        decrypted = _decrypt_bytes(data)
        return decrypted.decode('utf-8')

    def to_python(self, value):
        if isinstance(value, str):
            data = value.encode('utf-8')
            try:
                return _decrypt_bytes(data).decode('utf-8')
            except Exception:
                return value
        return value
