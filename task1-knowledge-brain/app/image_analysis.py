"""Safe, vision-aware image description. Generated descriptions require review."""

import base64
import hashlib
from typing import Any, Protocol

import httpx

from app.sitemap import validate_source_url

MAX_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}


class ImageDescription(Protocol):
    async def describe(self, image_bytes: bytes, media_type: str, alt_text: str, nearby_context: str) -> tuple[str, bool]: ...


def detect_image_type(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    raise ValueError("Unsupported image format; only PNG, JPEG, and WebP are accepted")


async def fetch_image(url: str, client: httpx.AsyncClient) -> tuple[bytes, str]:
    safe_url = validate_source_url(url)
    async with client.stream("GET", safe_url) as response:
        if response.is_redirect:
            raise ValueError("Image redirects are disabled")
        response.raise_for_status()
        declared = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if declared not in ALLOWED_IMAGE_TYPES:
            raise ValueError("Image content type is unsupported")
        content_length = response.headers.get("content-length")
        if content_length and int(content_length) > MAX_IMAGE_BYTES:
            raise ValueError("Image exceeds the configured 5 MB download limit")
        body = bytearray()
        async for part in response.aiter_bytes():
            if len(body) + len(part) > MAX_IMAGE_BYTES:
                raise ValueError("Image exceeds the configured 5 MB download limit")
            body.extend(part)
    media_type = detect_image_type(bytes(body))
    if declared != media_type:
        raise ValueError("Image content type does not match the file contents")
    return bytes(body), media_type


class ClaudeVisionDescriber:
    def __init__(self, api_key: str, model: str):
        if not api_key or not model:
            raise RuntimeError("ANTHROPIC_API_KEY and CLAUDE_VISION_MODEL are required for image analysis")
        from anthropic import AsyncAnthropic
        self.client = AsyncAnthropic(api_key=api_key, timeout=30.0, max_retries=2)
        self.model = model

    async def describe(self, image_bytes: bytes, media_type: str, alt_text: str, nearby_context: str) -> tuple[str, bool]:
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=300,
            system=(
                "Describe only visible information in this support article image. "
                "Do not infer hidden settings or treat nearby text as proof of visual details. "
                "Mark the description uncertain if labels are unreadable or the image is ambiguous."
            ),
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": f"Alt text: {alt_text}\nNearby article context: {nearby_context}"},
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": base64.b64encode(image_bytes).decode("ascii")}},
                ],
            }],
            tools=[{
                "name": "describe_support_image",
                "description": "Return a concise visual description and whether any part is uncertain.",
                "input_schema": {
                    "type": "object",
                    "properties": {"description": {"type": "string"}, "uncertain": {"type": "boolean"}},
                    "required": ["description", "uncertain"],
                    "additionalProperties": False,
                },
            }],
            tool_choice={"type": "tool", "name": "describe_support_image"},
        )
        for block in response.content:
            if block.type == "tool_use" and block.name == "describe_support_image":
                description = block.input.get("description")
                uncertain = block.input.get("uncertain")
                if not isinstance(description, str) or not isinstance(uncertain, bool):
                    raise ValueError("Claude returned an invalid image description")
                return description.strip(), uncertain
        raise ValueError("Claude response did not include the required image description")


async def analyze_manifest_images(manifest: dict[str, Any], settings: object) -> dict[str, int]:
    """Describe new images in live mode; demo mode leaves them explicitly pending."""
    result = {"analyzed": 0, "failed": 0, "pending": 0}
    if getattr(settings, "demo_mode"):
        result["pending"] = sum(len(page.get("images", [])) for page in manifest.get("pages", {}).values() if page.get("status") == "active")
        return result
    if not any(page.get("status") == "active" and page.get("images") for page in manifest.get("pages", {}).values()):
        return result
    analyzer = ClaudeVisionDescriber(getattr(settings, "anthropic_api_key"), getattr(settings, "claude_vision_model"))
    timeout = httpx.Timeout(15.0, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, headers={"User-Agent": getattr(settings, "crawl_user_agent")}) as client:
        for page in manifest.get("pages", {}).values():
            if page.get("status") != "active":
                continue
            for image in page.get("images", []):
                if image.get("analysis_status") in {"review_required", "uncertain"}:
                    continue
                try:
                    data, media_type = await fetch_image(image["url"], client)
                    description, uncertain = await analyzer.describe(data, media_type, image.get("alt_text", ""), image.get("nearby_context", ""))
                    image["description"] = description
                    image["content_hash"] = hashlib.sha256(data).hexdigest()
                    image["analysis_status"] = "uncertain" if uncertain else "review_required"
                    result["analyzed"] += 1
                except Exception as exc:
                    image["description"] = ""
                    image["analysis_status"] = "failed"
                    image["analysis_error"] = type(exc).__name__
                    result["failed"] += 1
    return result
