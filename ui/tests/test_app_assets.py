"""Regression tests for UI assets required at application startup."""

import unittest

from app import LunaVaultApp


class LunaVaultAppAssetTests(unittest.TestCase):
    """Ensure startup-critical assets are packaged with the UI."""

    def test_logo_exists(self) -> None:
        self.assertTrue(
            LunaVaultApp.LOGO_PATH.is_file(),
            f"Missing Luna Vault logo: {LunaVaultApp.LOGO_PATH}",
        )


if __name__ == "__main__":
    unittest.main()
