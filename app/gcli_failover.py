"""Runtime model failover for Anthropic requests sent to gcli2api."""

from __future__ import annotations

import threading
import time
import secrets
from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Optional, Tuple

import requests


@dataclass(frozen=True)
class GcliFailoverEvent:
    from_model: str = ""
    to_model: str = ""
    reason: str = ""
    timestamp: int = 0


@dataclass(frozen=True)
class _GcliFailoverSnapshot:
    """One immutable routing generation used for an entire forwarded request."""

    generation: int
    base_url: str
    api_key: str
    models: Tuple[str, ...]
    quota: Tuple[Tuple[str, float], ...]
    preferred: str
    cooldown_until: Tuple[Tuple[str, float], ...]


class GcliModelFailover:
    """Select gcli2api models using quota hints and authoritative 429 results."""

    def __init__(self, timeout: float = 45, max_models: int = 3,
                 total_timeout: float = 90,
                 clock=time.monotonic) -> None:
        self.timeout = max(1.0, float(timeout))
        self.total_timeout = max(self.timeout, float(total_timeout))
        self.max_models = max(1, max_models)
        self._clock = clock
        self._lock = threading.RLock()
        self._base_url = ""
        self._api_key = ""
        self._models: Tuple[str, ...] = ()
        self._quota: Dict[str, float] = {}
        self._preferred = ""
        self._cooldown_until: Dict[str, float] = {}
        self._rate_limit_count: Dict[str, int] = {}
        self._last_event = GcliFailoverEvent()
        self._generation = 0

    def configure(self, base_url: str, api_key: str, models: Iterable[str],
                  quota_percent: Optional[Mapping[str, float]] = None,
                  preferred_model: str = "") -> None:
        clean = []
        for value in models:
            model = str(value).strip()
            lowered = model.lower()
            incompatible = any(marker in lowered for marker in (
                "image", "tab_", "chat_", "-agent", "_agent",
            ))
            is_text_model = any(marker in lowered for marker in ("gemini", "claude", "gpt-oss"))
            if model and is_text_model and not incompatible and model not in clean:
                clean.append(model)
        with self._lock:
            self._generation += 1
            self._base_url = str(base_url or "").strip().rstrip("/")
            self._api_key = str(api_key or "")
            self._models = tuple(clean)
            self._quota = {
                str(model): max(0.0, min(100.0, float(remaining)))
                for model, remaining in (quota_percent or {}).items()
                if str(model).strip()
            }
            self._preferred = preferred_model if preferred_model in clean else ""
            valid = set(clean)
            self._cooldown_until = {
                model: until for model, until in self._cooldown_until.items() if model in valid
            }
            self._rate_limit_count = {
                model: count for model, count in self._rate_limit_count.items() if model in valid
            }

    def is_configured(self) -> bool:
        with self._lock:
            return bool(self._base_url and self._api_key and self._models)

    def verify_client_key(self, value: str) -> bool:
        with self._lock:
            expected = self._api_key
        return bool(expected and value and secrets.compare_digest(expected, value))

    @staticmethod
    def _capability_rank(model: str) -> int:
        name = model.lower()
        if "claude" in name:
            return 0
        if "pro" in name:
            return 1
        if "flash" in name:
            return 2
        return 3

    @staticmethod
    def _family(model: str) -> str:
        name = model.lower()
        for family in ("gemini", "claude", "gpt-oss"):
            if family in name:
                return family
        return "other"

    def _snapshot(self) -> _GcliFailoverSnapshot:
        with self._lock:
            return _GcliFailoverSnapshot(
                generation=self._generation,
                base_url=self._base_url,
                api_key=self._api_key,
                models=self._models,
                quota=tuple(self._quota.items()),
                preferred=self._preferred,
                cooldown_until=tuple(self._cooldown_until.items()),
            )

    def _candidates_from_snapshot(self, snapshot: _GcliFailoverSnapshot,
                                  requested_model: str, now: float) -> List[str]:
        quota = dict(snapshot.quota)
        cooldown_until = dict(snapshot.cooldown_until)
        available = [
            model for model in snapshot.models
            if cooldown_until.get(model, 0) <= now
        ]
        preferred = requested_model if requested_model in available else snapshot.preferred
        preferred_family = self._family(preferred or requested_model)
        return sorted(
            available,
            key=lambda model: (
                0 if model == preferred else 1,
                0 if self._family(model) == preferred_family else 1,
                -quota.get(model, -1),
                self._capability_rank(model),
                model.lower(),
            ),
        )

    def candidates(self, requested_model: str = "") -> List[str]:
        snapshot = self._snapshot()
        return self._candidates_from_snapshot(snapshot, requested_model, self._clock())

    def report_rate_limit(self, model: str, generation: Optional[int] = None) -> int:
        with self._lock:
            if generation is not None and generation != self._generation:
                return 0
            count = self._rate_limit_count.get(model, 0) + 1
            self._rate_limit_count[model] = count
            seconds = min(240, 60 * (2 ** (count - 1)))
            self._cooldown_until[model] = self._clock() + seconds
            return seconds

    def report_success(self, model: str, generation: Optional[int] = None) -> None:
        with self._lock:
            if generation is not None and generation != self._generation:
                return
            self._rate_limit_count.pop(model, None)
            self._cooldown_until.pop(model, None)

    def status(self) -> Dict:
        now = self._clock()
        with self._lock:
            return {
                "configured": self.is_configured(),
                "models": [
                    {
                        "model": model,
                        "quota_percent": self._quota.get(model),
                        "cooldown_seconds": max(
                            0, int(self._cooldown_until.get(model, 0) - now)),
                    }
                    for model in self._models
                ],
                "last_event": self._last_event,
            }

    def forward(self, payload: Dict, stream: bool = False) -> Tuple[requests.Response, str]:
        """Try up to three distinct models; streaming switches only before bytes are exposed."""
        snapshot = self._snapshot()
        if not snapshot.base_url or not snapshot.api_key:
            raise RuntimeError("Gemini 自动切换尚未配置")
        requested = str(payload.get("model") or "")
        candidates = self._candidates_from_snapshot(
            snapshot, requested, self._clock())[:self.max_models]
        if not candidates:
            raise RuntimeError("所有 Gemini 候选模型均在冷却中")
        url = (snapshot.base_url if snapshot.base_url.endswith("/v1/messages")
               else f"{snapshot.base_url}/v1/messages")
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream" if stream else "application/json",
            "x-api-key": snapshot.api_key,
            "anthropic-version": "2023-06-01",
        }
        last_response = None
        last_exception = None
        last_model = ""
        first_model = candidates[0]
        started = self._clock()
        for model in candidates:
            remaining = self.total_timeout - (self._clock() - started)
            if remaining <= 0:
                break
            request_payload = dict(payload)
            request_payload["model"] = model
            try:
                response = requests.post(
                    url, headers=headers, json=request_payload,
                    timeout=min(self.timeout, remaining), stream=stream,
                    allow_redirects=False,
                )
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
                last_exception = exc
                continue
            if last_response is not None:
                last_response.close()
            last_response = response
            last_model = model
            if response.status_code == 200:
                self.report_success(model, snapshot.generation)
                if model != first_model:
                    with self._lock:
                        if snapshot.generation == self._generation:
                            self._last_event = GcliFailoverEvent(
                                from_model=first_model, to_model=model,
                                reason="429 额度耗尽后自动切换", timestamp=int(time.time()))
                return response, model
            if response.status_code == 429:
                self.report_rate_limit(model, snapshot.generation)
                continue
            if response.status_code >= 500:
                continue
            # Authentication and request-shape failures must not be hidden by another model.
            return response, model
        if last_response is not None:
            return last_response, last_model
        if last_exception is not None:
            raise last_exception
        raise RuntimeError("没有可用的 Gemini 候选模型")
