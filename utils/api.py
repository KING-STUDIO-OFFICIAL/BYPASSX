import asyncio
from typing import Any

import aiohttp

import config as cfg
from utils.logger import logger
from utils.helpers import get_hostname


class BypassAPI:

    def __init__(self, base_url: str = cfg.API_BASE_URL) -> None:
        self.base_url = base_url.rstrip("/")
        self.bypass_url = cfg.BYPASS_ENDPOINT
        self.supported_url = cfg.SUPPORTED_ENDPOINT

    async def _request(
        self, url: str, params: dict[str, str] | None = None
    ) -> tuple[int, str]:
        timeout = aiohttp.ClientTimeout(total=cfg.API_TIMEOUT)
        last_exc: Exception | None = None
        for attempt in range(cfg.API_RETRIES + 1):
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url, params=params) as resp:
                        text = await resp.text()
                        return resp.status, text
            except asyncio.TimeoutError as exc:
                last_exc = exc
                logger.warning("API timeout (attempt %s/%s): %s", attempt + 1, cfg.API_RETRIES + 1, url)
            except aiohttp.ClientConnectorError as exc:
                last_exc = exc
                logger.warning("API connection error (attempt %s/%s): %s", attempt + 1, cfg.API_RETRIES + 1, exc)
            except aiohttp.ClientError as exc:
                last_exc = exc
                logger.warning("API client error (attempt %s/%s): %s", attempt + 1, cfg.API_RETRIES + 1, exc)
            except Exception as exc:
                last_exc = exc
                logger.warning("API unexpected error (attempt %s/%s): %s", attempt + 1, cfg.API_RETRIES + 1, exc)
            if attempt < cfg.API_RETRIES:
                await asyncio.sleep(1)
        raise BypassAPIError(f"API request failed: {last_exc}")

    @staticmethod
    def _parse_response(text: str) -> str:
        if not text:
            return ""
        stripped = text.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            import json

            try:
                data = json.loads(stripped)
            except json.JSONDecodeError:
                return stripped
            if isinstance(data, dict):
                for key in ("result", "bypass", "link", "url", "output", "data", "value"):
                    if key in data and isinstance(data[key], str):
                        return data[key]
                if "success" in data and "message" in data and isinstance(data["message"], str):
                    return data["message"]
                return json.dumps(data, indent=2)
            if isinstance(data, list):
                return json.dumps(data, indent=2)
            return str(data)
        return stripped

    async def bypass(self, link: str) -> dict[str, Any]:
        logger.info("API bypass request for: %s", get_hostname(link) or link)
        try:
            status, text = await self._request(self.bypass_url, {"link": link})
        except BypassAPIError as exc:
            return {"success": False, "result": "", "service": "", "error": str(exc)}

        if status >= 500:
            logger.error("API server error %s for bypass", status)
            return {"success": False, "result": "", "service": "", "error": f"API server error (HTTP {status})"}
        if status == 404:
            return {"success": False, "result": "", "service": "", "error": "Service not found or unsupported."}
        if status >= 400:
            parsed = self._parse_response(text)
            return {"success": False, "result": "", "service": "", "error": parsed or f"API error (HTTP {status})"}

        parsed = self._parse_response(text)
        if not parsed:
            return {"success": False, "result": "", "service": "", "error": "Empty API response."}

        service = get_hostname(link)
        return {"success": True, "result": parsed, "service": service, "error": ""}

    async def get_supported(self) -> dict[str, Any]:
        logger.info("API supported request")
        try:
            status, text = await self._request(self.supported_url, {"link": ""})
        except BypassAPIError as exc:
            return {"success": False, "services": [], "error": str(exc)}

        if status >= 400:
            logger.error("API supported endpoint error: %s", status)
            return {"success": False, "services": [], "error": f"API error (HTTP {status})"}

        services = self._parse_supported(text)
        if not services:
            return {"success": False, "services": [], "error": "Could not parse supported services from API response."}
        return {"success": True, "services": services, "error": ""}

    @staticmethod
    def _parse_supported(text: str) -> list[str]:
        if not text:
            return []
        stripped = text.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            import json

            try:
                data = json.loads(stripped)
            except json.JSONDecodeError:
                return []
            if isinstance(data, list):
                return [str(item) for item in data]
            if isinstance(data, dict):
                for key in ("supported", "services", "list", "data", "results"):
                    if key in data:
                        value = data[key]
                        if isinstance(value, list):
                            return [str(item) for item in value]
                        if isinstance(value, dict):
                            return list(value.keys())
                        if isinstance(value, str):
                            return [item.strip() for item in value.split(",") if item.strip()]
                return list(data.keys())
            return []
        lines = [line.strip() for line in stripped.splitlines() if line.strip()]
        if lines:
            return lines
        items = [item.strip() for item in stripped.split(",") if item.strip()]
        return items


class BypassAPIError(Exception):
    pass
