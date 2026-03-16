from __future__ import annotations

import hashlib
import json
import socket
import threading
import time
from pathlib import Path
from urllib.parse import urlparse
from typing import Any, Callable, Dict, List, Optional, TypeVar

import requests

from config import (
    LLM_API_BASE,
    LLM_API_KEY,
    LLM_CACHE_DIR,
    LLM_DISABLE_RESPONSE_STORAGE,
    LLM_ENABLE_CACHE,
    LLM_MAX_RETRIES,
    LLM_MAX_OUTPUT_TOKENS,
    LLM_MODEL,
    LLM_PREFLIGHT,
    LLM_PREFLIGHT_TIMEOUT_SECONDS,
    LLM_REASONING_EFFORT,
    LLM_RETRY_BACKOFF_SECONDS,
    LLM_TEMPERATURE,
    LLM_TIMEOUT_SECONDS,
    LLM_WIRE_API,
)

_T = TypeVar("_T")

_PREFLIGHT_LOCK = threading.Lock()
_PREFLIGHT_DONE = False
_PREFLIGHT_ERROR: Optional[str] = None


class LlmHttpError(RuntimeError):
    def __init__(self, *, status_code: int, url: str, detail: str):
        self.status_code = status_code
        self.url = url
        self.detail = detail
        super().__init__(f"HTTP {status_code} from {url}: {detail}")


class BaseAgent:
    def __init__(
        self,
        tools: Optional[List[object]] = None,
        system_prompt: str = "",
        *,
        wire_api: Optional[str] = None,
        expects_json: bool = False,
        context_version: str = "",
        log_hook: Optional[Callable[[str], None]] = None,
    ):
        self.tools = tools or []
        self.system_prompt = system_prompt
        self.wire_api_override = wire_api
        self.expects_json = expects_json
        self.context_version = context_version
        self.log_hook = log_hook

    def _run_single_tool(self, user_input: str) -> str:
        tool = self.tools[0]
        tool_fn: Callable[[str], str] = getattr(tool, "func")
        return tool_fn(user_input)

    def _log(self, message: str) -> None:
        if self.log_hook is not None:
            self.log_hook(message)
            return
        print(message)

    def _preflight_base_url(self) -> None:
        global _PREFLIGHT_DONE, _PREFLIGHT_ERROR
        if not LLM_PREFLIGHT:
            return

        with _PREFLIGHT_LOCK:
            if _PREFLIGHT_DONE:
                if _PREFLIGHT_ERROR:
                    raise RuntimeError(_PREFLIGHT_ERROR)
                return
            _PREFLIGHT_DONE = True

        parsed = urlparse(LLM_API_BASE)
        host = parsed.hostname
        if not host:
            return
        port = parsed.port
        if port is None:
            port = 443 if parsed.scheme == "https" else 80

        candidate_hosts = [host]
        if host.lower() == "localhost":
            candidate_hosts = ["127.0.0.1", "localhost"]

        last_exc: Optional[OSError] = None
        for candidate_host in candidate_hosts:
            try:
                with socket.create_connection(
                    (candidate_host, port), timeout=LLM_PREFLIGHT_TIMEOUT_SECONDS
                ):
                    return
            except OSError as exc:
                last_exc = exc

        message = (
            "Cannot connect to LLM gateway. "
            f"LLM_API_BASE={LLM_API_BASE!r}, host={host!r}, port={port}. "
            f"Error: {last_exc}. "
            "Start the local gateway or set LLM_PREFLIGHT=false to skip this check."
        )
        with _PREFLIGHT_LOCK:
            _PREFLIGHT_ERROR = message
        raise RuntimeError(message) from last_exc

    def _candidate_api_bases(self) -> List[str]:
        base = (LLM_API_BASE or "").strip().rstrip("/")
        if not base:
            return []

        parsed = urlparse(base)
        hostname = (parsed.hostname or "").lower()
        if not parsed.scheme or not parsed.netloc or hostname != "localhost":
            return [base]

        port = parsed.port
        ipv4_netloc = "127.0.0.1" + (f":{port}" if port else "")
        ipv4_base = parsed._replace(netloc=ipv4_netloc).geturl().rstrip("/")

        candidates: List[str] = []
        for item in (ipv4_base, base):
            if item and item not in candidates:
                candidates.append(item)

        expanded: List[str] = []
        for item in candidates:
            parsed = urlparse(item)
            needs_v1_first = (parsed.path in ("", "/")) and not item.endswith("/v1")
            if needs_v1_first:
                variant = f"{item}/v1"
                if variant not in expanded:
                    expanded.append(variant)
            if item not in expanded:
                expanded.append(item)
            if not item.endswith("/v1"):
                variant = f"{item}/v1"
                if variant not in expanded:
                    expanded.append(variant)
        return expanded

    def _post_json(self, *, path: str, payload: Dict[str, Any], label: str) -> Dict[str, Any]:
        if not LLM_API_KEY:
            raise RuntimeError("Missing LLM_API_KEY (or OPENAI_API_KEY / DEEPSEEK_API_KEY).")

        self._preflight_base_url()

        connect_timeout = float(LLM_PREFLIGHT_TIMEOUT_SECONDS) if LLM_PREFLIGHT_TIMEOUT_SECONDS else 2.0
        connect_timeout = max(0.5, min(connect_timeout, 10.0))
        timeout = (connect_timeout, float(LLM_TIMEOUT_SECONDS))

        headers = {
            "Authorization": f"Bearer {LLM_API_KEY}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        last_exc: Optional[Exception] = None
        for api_base in self._candidate_api_bases():
            url = f"{api_base}{path}"

            def _call() -> Dict[str, Any]:
                response = requests.post(url, headers=headers, json=payload, timeout=timeout)
                if response.status_code >= 400:
                    detail = ""
                    try:
                        body = response.json()
                        if isinstance(body, dict):
                            error_obj = body.get("error")
                            if isinstance(error_obj, dict) and error_obj.get("message"):
                                detail = str(error_obj.get("message"))
                            elif body.get("detail"):
                                detail = str(body.get("detail"))
                    except Exception:
                        detail = ""

                    if not detail:
                        detail = (response.text or "").strip()
                    detail = detail.replace("\r", " ").replace("\n", " ").strip() or "empty response"
                    if response.status_code == 404 and "/v1" not in url:
                        detail = (
                            f"{detail} (hint: LLM_API_BASE may need a /v1 suffix, "
                            "e.g. http://host:port/v1)"
                        )
                    if len(detail) > 600:
                        detail = detail[:600] + "..."
                    raise LlmHttpError(status_code=response.status_code, url=url, detail=detail)

                try:
                    data = response.json()
                except Exception as exc:
                    snippet = (response.text or "").strip()
                    if len(snippet) > 600:
                        snippet = snippet[:600] + "..."
                    raise RuntimeError(f"Non-JSON response from {url}: {snippet}") from exc

                if not isinstance(data, dict):
                    raise RuntimeError(f"Unexpected JSON response from {url}: {type(data).__name__}")
                return data

            try:
                return self._with_retries(_call, label=f"{label} ({api_base})")
            except Exception as exc:
                last_exc = exc
                continue

        assert last_exc is not None
        raise last_exc

    def _cache_key(self, *, wire_api: str, user_input: str) -> str:
        payload = {
            "wire_api": wire_api,
            "base_url": LLM_API_BASE,
            "model": LLM_MODEL,
            "system_prompt": self.system_prompt,
            "user_input": user_input,
            "reasoning_effort": LLM_REASONING_EFFORT if wire_api == "responses" else "",
            "temperature": LLM_TEMPERATURE if wire_api != "responses" else None,
            "store": (not LLM_DISABLE_RESPONSE_STORAGE),
            "expects_json": self.expects_json,
            "context_version": self.context_version,
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def _cache_path(self, key: str) -> Path:
        return Path(LLM_CACHE_DIR) / f"{key}.json"

    def _read_cache(self, key: str) -> Optional[str]:
        if not LLM_ENABLE_CACHE:
            return None

        path = self._cache_path(key)
        if not path.exists():
            return None

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

        text = data.get("text")
        return text if isinstance(text, str) else None

    def _write_cache(self, key: str, text: str) -> None:
        if not LLM_ENABLE_CACHE:
            return

        path = self._cache_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(".json.tmp")
        payload = {"text": text, "created_at": time.time()}

        try:
            tmp_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            tmp_path.replace(path)
        except Exception:
            # Cache is best-effort.
            return

    def _with_retries(self, fn: Callable[[], _T], *, label: str) -> _T:
        last_exc: Optional[Exception] = None
        attempts = max(0, int(LLM_MAX_RETRIES)) + 1
        for attempt in range(attempts):
            try:
                return fn()
            except Exception as exc:
                last_exc = exc
                if isinstance(exc, LlmHttpError) and exc.status_code in {400, 401, 403, 404}:
                    self._log(f"[error] {label} failed: {exc} (no retry)")
                    break
                if attempt >= attempts - 1:
                    break
                sleep_s = LLM_RETRY_BACKOFF_SECONDS * (2**attempt)
                self._log(
                    f"[warning] {label} failed (attempt {attempt + 1}/{attempts}): {exc}"
                )
                time.sleep(sleep_s)
        assert last_exc is not None
        raise last_exc

    def _run_responses(self, user_input: str) -> str:
        payload: Dict[str, Any] = {"model": LLM_MODEL, "input": user_input}
        if self.system_prompt:
            payload["instructions"] = self.system_prompt
        if LLM_REASONING_EFFORT:
            payload["reasoning"] = {"effort": LLM_REASONING_EFFORT}
        if LLM_DISABLE_RESPONSE_STORAGE:
            payload["store"] = False
        if LLM_MAX_OUTPUT_TOKENS:
            payload["max_output_tokens"] = int(LLM_MAX_OUTPUT_TOKENS)
        if self.expects_json:
            payload["response_format"] = {"type": "json_object"}

        try:
            response = self._post_json(path="/responses", payload=payload, label="responses.create")
        except Exception as exc:
            message = str(exc).lower()
            looks_like_param_error = any(
                token in message
                for token in (
                    "unknown parameter",
                    "unrecognized request argument",
                    "unexpected",
                    "not permitted",
                    "invalid request",
                )
            )
            if looks_like_param_error and any(
                k in payload
                for k in (
                    "reasoning",
                    "store",
                    "instructions",
                    "max_output_tokens",
                    "response_format",
                )
            ):
                fallback_payload = dict(payload)
                fallback_payload.pop("reasoning", None)
                fallback_payload.pop("store", None)
                fallback_payload.pop("instructions", None)
                fallback_payload.pop("max_output_tokens", None)
                fallback_payload.pop("response_format", None)
                response = self._post_json(
                    path="/responses",
                    payload=fallback_payload,
                    label="responses.create(fallback)",
                )
            else:
                raise

        text = response.get("output_text")
        if isinstance(text, str) and text.strip():
            return text.strip()

        # Fallback for older client versions / non-standard backends.
        output = response.get("output") or []
        if isinstance(output, list):
            for item in output:
                if not isinstance(item, dict) or item.get("type") != "message":
                    continue
                contents = item.get("content") or []
                if not isinstance(contents, list):
                    continue
                for content in contents:
                    if not isinstance(content, dict):
                        continue
                    if content.get("type") == "output_text":
                        value = content.get("text", "")
                        if value:
                            return str(value).strip()

        # Some backends return chat.completions-like output on /responses.
        choices = response.get("choices") or []
        if isinstance(choices, list) and choices:
            first = choices[0] if isinstance(choices[0], dict) else {}
            message_obj = first.get("message") if isinstance(first, dict) else None
            if isinstance(message_obj, dict):
                content = message_obj.get("content", "")
                if isinstance(content, str) and content.strip():
                    return content.strip()

        return json.dumps(response, ensure_ascii=False)

    def _run_chat_completions(self, user_input: str) -> str:
        messages = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        messages.append({"role": "user", "content": user_input})

        payload: Dict[str, Any] = {
            "model": LLM_MODEL,
            "messages": messages,
            "temperature": LLM_TEMPERATURE,
        }
        if LLM_DISABLE_RESPONSE_STORAGE:
            payload["store"] = False
        if LLM_MAX_OUTPUT_TOKENS:
            payload["max_tokens"] = int(LLM_MAX_OUTPUT_TOKENS)
        if self.expects_json:
            payload["response_format"] = {"type": "json_object"}

        try:
            response = self._post_json(
                path="/chat/completions",
                payload=payload,
                label="chat.completions.create",
            )
        except Exception as exc:
            message = str(exc).lower()
            looks_like_param_error = any(
                token in message
                for token in (
                    "unknown parameter",
                    "unrecognized request argument",
                    "unexpected",
                    "not permitted",
                    "invalid request",
                )
            )
            if looks_like_param_error and any(
                k in payload for k in ("store", "max_tokens", "response_format")
            ):
                fallback_payload = dict(payload)
                fallback_payload.pop("store", None)
                fallback_payload.pop("max_tokens", None)
                fallback_payload.pop("response_format", None)
                response = self._post_json(
                    path="/chat/completions",
                    payload=fallback_payload,
                    label="chat.completions.create(fallback)",
                )
            else:
                raise

        choices = response.get("choices") or []
        if not choices:
            return ""
        first = choices[0] if isinstance(choices[0], dict) else {}
        message_obj = first.get("message") if isinstance(first, dict) else None
        if not isinstance(message_obj, dict):
            return ""
        content = message_obj.get("content", "")
        return content.strip() if isinstance(content, str) else str(content)

    def _run_llm(self, user_input: str) -> str:
        wire = (self.wire_api_override or LLM_WIRE_API or "").strip().lower()
        wire = wire if wire in {"responses", "chat_completions"} else "responses"

        cache_key = self._cache_key(wire_api=wire, user_input=user_input)
        cached = self._read_cache(cache_key)
        if cached is not None:
            return cached

        if wire == "responses":
            result = self._run_responses(user_input)
        else:
            result = self._run_chat_completions(user_input)

        self._write_cache(cache_key, result)
        return result

    def run(self, user_input: str) -> str:
        # If a single tool is attached, call it directly for deterministic behavior.
        if len(self.tools) == 1:
            return self._run_single_tool(user_input)
        return self._run_llm(user_input)
