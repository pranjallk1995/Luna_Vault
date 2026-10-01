import hashlib
import hmac
import re
import secrets
import threading
import time

from config import AppConfig
from database import MetadataRepository


class HiddenVaultAuth:
    """Persist hashed credentials and issue short-lived in-memory sessions."""

    def __init__(self, repository: MetadataRepository, config: AppConfig) -> None:
        self.repository = repository
        self.iterations = config.password_hash_iterations
        self.session_seconds = config.hidden_session_seconds
        self._sessions: dict[str, float] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _hash(value: str, salt: bytes, iterations: int) -> bytes:
        return hashlib.pbkdf2_hmac("sha256", value.encode(), salt, iterations)

    @staticmethod
    def validate_password(password: str) -> None:
        if len(password) < 8:
            raise ValueError("Password must contain at least 8 characters.")

    @staticmethod
    def validate_pin(pin: str) -> None:
        if not re.fullmatch(r"\d{8}", pin):
            raise ValueError("Reset PIN must be exactly 8 digits.")

    def configured(self) -> bool:
        return self.repository.security_credentials() is not None

    def _new_session(self) -> str:
        token = secrets.token_urlsafe(32)
        now = time.monotonic()
        with self._lock:
            self._sessions = {key: expiry for key, expiry in self._sessions.items() if expiry > now}
            self._sessions[token] = now + self.session_seconds
        return token

    def setup(self, password: str, pin: str) -> str:
        self.validate_password(password)
        self.validate_pin(pin)
        password_salt, pin_salt = secrets.token_bytes(16), secrets.token_bytes(16)
        created = self.repository.create_security_credentials(
            password_salt, self._hash(password, password_salt, self.iterations),
            pin_salt, self._hash(pin, pin_salt, self.iterations), self.iterations,
        )
        if not created:
            raise ValueError("A hidden-vault password has already been created.")
        return self._new_session()

    def login(self, password: str) -> str:
        credentials = self.repository.security_credentials()
        if credentials is None:
            raise ValueError("Create a hidden-vault password first.")
        password_salt, password_hash, _, _, iterations = credentials
        if not hmac.compare_digest(self._hash(password, password_salt, iterations), password_hash):
            raise PermissionError("Incorrect password.")
        return self._new_session()

    def reset(self, pin: str, new_password: str) -> str:
        self.validate_pin(pin)
        self.validate_password(new_password)
        credentials = self.repository.security_credentials()
        if credentials is None:
            raise ValueError("Create a hidden-vault password first.")
        _, _, pin_salt, pin_hash, iterations = credentials
        if not hmac.compare_digest(self._hash(pin, pin_salt, iterations), pin_hash):
            raise PermissionError("Incorrect reset PIN.")
        password_salt = secrets.token_bytes(16)
        self.repository.update_password(
            password_salt, self._hash(new_password, password_salt, self.iterations), self.iterations
        )
        with self._lock:
            self._sessions.clear()
        return self._new_session()

    def require(self, token: str | None) -> None:
        now = time.monotonic()
        with self._lock:
            expiry = self._sessions.get(token or "", 0)
            if expiry <= now:
                self._sessions.pop(token or "", None)
                raise PermissionError("Hidden-vault session is missing or expired.")
            self._sessions[token] = now + self.session_seconds

    def logout(self, token: str | None) -> None:
        with self._lock:
            self._sessions.pop(token or "", None)
