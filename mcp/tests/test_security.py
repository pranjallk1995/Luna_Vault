"""Tests for test security behavior."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from config import AppConfig
from security import HiddenVaultAuth


class FakeSecurityRepository:
    """Provide an in-memory securityrepository test double."""
    def __init__(self):
        """Initialize this component and its required dependencies."""
        self.credentials = None

    def security_credentials(self):
        """Return stored credential material from the test repository."""
        return self.credentials

    def create_security_credentials(self, password_salt, password_hash,
                                    pin_salt, pin_hash, iterations):
        """Persist Hidden Vault credentials only when none exist."""
        if self.credentials is not None:
            return False
        self.credentials = (password_salt, password_hash, pin_salt, pin_hash, iterations)
        return True

    def update_password(self, password_salt, password_hash, iterations):
        """Replace the stored password-derived credential material."""
        _, _, pin_salt, pin_hash, _ = self.credentials
        self.credentials = (password_salt, password_hash, pin_salt, pin_hash, iterations)


class HiddenVaultAuthTests(unittest.TestCase):
    """Exercise HiddenVaultAuth behavior."""
    def setUp(self):
        """Create isolated dependencies for each test case."""
        self.repository = FakeSecurityRepository()
        config = AppConfig(Path("/tmp"), "postgresql://test", "http://ollama:11434", "test")
        self.auth = HiddenVaultAuth(self.repository, config)

    def test_setup_login_and_session(self):
        """Verify setup login and session."""
        token = self.auth.setup("strong-password", "12345678")
        self.auth.require(token)
        self.auth.logout(token)
        with self.assertRaises(PermissionError):
            self.auth.require(token)
        self.auth.require(self.auth.login("strong-password"))

    def test_pin_must_be_exactly_eight_digits(self):
        """Verify pin must be exactly eight digits."""
        for pin in ("1234567", "123456789", "abcdefgh"):
            with self.assertRaises(ValueError):
                self.auth.setup("strong-password", pin)

    def test_reset_requires_pin_and_replaces_password(self):
        """Verify reset requires pin and replaces password."""
        self.auth.setup("old-password", "12345678")
        with self.assertRaises(PermissionError):
            self.auth.reset("87654321", "new-password")
        token = self.auth.reset("12345678", "new-password")
        self.auth.require(token)
        with self.assertRaises(PermissionError):
            self.auth.login("old-password")
        self.auth.require(self.auth.login("new-password"))


if __name__ == "__main__":
    unittest.main()
