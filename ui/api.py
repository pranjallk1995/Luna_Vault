"""UI-facing client for Luna Vault's HTTP routes."""

from typing import Any
from urllib.parse import quote

import httpx

from config import UIConfig


class LunaVaultAPI:
    """Keep backend routes and HTTP details out of Streamlit views."""

    def __init__(self, config: UIConfig) -> None:
        self.base_url = config.api_url
        self.headers = config.api_headers

    def request(
        self,
        method: str,
        path: str,
        *,
        timeout: float = 30.0,
        token: str | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        headers = self.headers.copy()
        if token:
            headers["X-Hidden-Vault-Token"] = token
        response = httpx.request(
            method,
            f"{self.base_url}{path}",
            headers=headers,
            timeout=timeout,
            **kwargs,
        )
        response.raise_for_status()
        return response

    def metadata(self) -> list[dict[str, Any]]:
        return self.request("GET", "/api/metadata", timeout=10.0).json()["images"]

    def upload_image(self, name: str, content_base64: str) -> dict[str, Any]:
        return self.request(
            "POST",
            "/api/images",
            json={"name": name, "content_base64": content_base64},
            timeout=360.0,
        ).json()

    def delete_image(self, name: str) -> None:
        self.request("DELETE", f"/api/images/{quote(name, safe='')}")

    def update_image_metadata(self, name: str, payload: dict) -> dict[str, Any]:
        return self.request(
            "POST", f"/api/images/{quote(name, safe='')}/metadata", json=payload
        ).json()

    def favorites(self) -> list[dict[str, Any]]:
        return self.request("GET", "/api/favorites", timeout=10.0).json()["images"]

    def set_favorites(self, names: list[str], favorite: bool) -> None:
        self.request(
            "POST",
            "/api/favorites",
            json={"names": names, "favorite": favorite},
        )

    def hidden_status(self) -> bool:
        return self.request("GET", "/api/hidden/status", timeout=10.0).json()[
            "configured"
        ]

    def hidden_setup(self, password: str, pin: str) -> dict[str, Any]:
        return self.request(
            "POST", "/api/hidden/setup", json={"password": password, "pin": pin}
        ).json()

    def hidden_login(self, password: str) -> dict[str, Any]:
        return self.request(
            "POST", "/api/hidden/login", json={"password": password}
        ).json()

    def hidden_reset(self, pin: str, new_password: str) -> dict[str, Any]:
        return self.request(
            "POST",
            "/api/hidden/reset",
            json={"pin": pin, "new_password": new_password},
        ).json()

    def hidden_logout(self, token: str) -> None:
        self.request("POST", "/api/hidden/logout", json={}, token=token)

    def hidden_images(self, token: str) -> list[dict[str, Any]]:
        return self.request(
            "GET", "/api/hidden/images", token=token, timeout=10.0
        ).json()["images"]

    def hide_images(self, names: list[str], token: str) -> None:
        self.request(
            "POST", "/api/hidden/hide", json={"names": names}, token=token
        )

    def restore_hidden_images(self, names: list[str], token: str) -> None:
        self.request(
            "POST", "/api/hidden/restore", json={"names": names}, token=token
        )

    def delete_hidden_images(self, names: list[str], token: str) -> None:
        self.request(
            "POST", "/api/hidden/delete", json={"names": names}, token=token
        )

    def update_hidden_metadata(
        self, name: str, payload: dict, token: str
    ) -> dict[str, Any]:
        return self.request(
            "POST",
            f"/api/hidden/images/{quote(name, safe='')}/metadata",
            json=payload,
            token=token,
        ).json()
