"""Client cho LLM on-prem theo chuẩn OpenAI-compatible (/v1/chat/completions).

Tương thích vLLM, Ollama (>=0.1.24), TGI, LiteLLM proxy... Không gửi dữ liệu ra Internet.
Trả None khi LLM tắt/lỗi để tầng trên dùng phương án dự phòng (rule-based).
"""
from __future__ import annotations

import json
import logging
import re

import httpx

from app.core.config import Settings, get_settings

log = logging.getLogger(__name__)
_JSON_BLOCK = re.compile(r"\{.*\}", re.S)


class LlmClient:
    def __init__(self, settings: Settings | None = None, http: httpx.Client | None = None):
        self.s = settings or get_settings()
        self.http = http

    @property
    def enabled(self) -> bool:
        return bool(self.s.llm_enabled and self.s.llm_base_url)

    def chat(self, system: str, user: str, temperature: float = 0.2, max_tokens: int = 1200) -> str | None:
        if not self.enabled:
            return None
        headers = {"Content-Type": "application/json"}
        if self.s.llm_api_key:
            headers["Authorization"] = f"Bearer {self.s.llm_api_key}"
        payload = {
            "model": self.s.llm_model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        url = self.s.llm_base_url.rstrip("/") + "/v1/chat/completions"
        try:
            http = self.http or httpx.Client(verify=self.s.tls_verify, timeout=self.s.llm_timeout_seconds)
            r = http.post(url, json=payload, headers=headers)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
            log.warning("LLM lỗi: %s", exc)
            return None

    def chat_json(self, system: str, user: str, **kw) -> dict | None:
        raw = self.chat(system, user, **kw)
        if raw is None:
            return None
        m = _JSON_BLOCK.search(raw)
        if not m:
            log.warning("LLM không trả JSON hợp lệ")
            return None
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            log.warning("LLM trả JSON hỏng")
            return None
