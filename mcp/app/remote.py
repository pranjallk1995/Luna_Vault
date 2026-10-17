"""Resolve chat-supplied image sources into Base64 image content."""

import base64
import ipaddress
import socket
from urllib.parse import urlparse

import httpx


class ImageSourceResolver:
    """Accept Base64, an image data URL, or a public HTTPS URL (SSRF-guarded)."""

    def __init__(self, max_bytes: int, max_redirects: int) -> None:
        self.max_bytes = max_bytes
        self.max_redirects = max_redirects

    def resolve(self, content_base64: str | None, image_url: str | None) -> str:
        """Return Base64 image bytes from exactly one supported chat source."""
        supplied = sum(
            value is not None and bool(value.strip()) for value in (content_base64, image_url)
        )
        if supplied != 1:
            raise ValueError("Provide exactly one of content_base64, image_url, or file_path.")
        if content_base64 and content_base64.strip():
            return content_base64.strip()
        source = image_url.strip()
        if source.startswith("data:image/"):
            return self._data_url_payload(source)
        return base64.b64encode(self._download(source)).decode("ascii")

    @staticmethod
    def _data_url_payload(source: str) -> str:
        header, separator, payload = source.partition(",")
        if not separator or not header.casefold().endswith(";base64"):
            raise ValueError("Image data URLs must contain Base64-encoded data.")
        return payload

    @staticmethod
    def validate_public_https_url(url: str) -> None:
        """Reject non-HTTPS and private-network upload sources."""
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("image_url must be a public HTTPS URL or image data URL.")
        try:
            addresses = {
                entry[4][0] for entry in socket.getaddrinfo(parsed.hostname, parsed.port or 443)
            }
        except socket.gaierror as error:
            raise ValueError("image_url hostname could not be resolved.") from error
        if not addresses or any(not ipaddress.ip_address(value).is_global for value in addresses):
            raise ValueError("image_url must resolve only to public internet addresses.")

    def _download(self, url: str) -> bytes:
        """Follow a bounded number of validated redirects and stream the image."""
        current = url
        with httpx.Client(timeout=30.0, follow_redirects=False) as client:
            for redirect_count in range(self.max_redirects + 1):
                self.validate_public_https_url(current)
                with client.stream("GET", current) as response:
                    if response.is_redirect:
                        if redirect_count == self.max_redirects:
                            raise ValueError("image_url redirected too many times.")
                        location = response.headers.get("location")
                        if not location:
                            raise ValueError("image_url returned an invalid redirect.")
                        current = str(response.url.join(location))
                        continue
                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "").casefold()
                    if not content_type.startswith("image/"):
                        raise ValueError("image_url did not return image content.")
                    data = bytearray()
                    for chunk in response.iter_bytes():
                        data.extend(chunk)
                        if len(data) > self.max_bytes:
                            raise ValueError("Image content exceeds the 50 MiB limit.")
                    if not data:
                        raise ValueError("image_url returned an empty image.")
                    return bytes(data)
        raise ValueError("image_url could not be downloaded.")
