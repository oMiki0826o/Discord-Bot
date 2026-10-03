"""
bot/mod/ai/provider/runtime.py

Modification():

- 集中處理 Provider timeout、有限重試、429 cooldown 與 model fallback。

本檔案是所有前景與背景生成的唯一 Provider 執行層。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Callable, Protocol

from .errors import ProviderEmptyResponseError, ProviderError, ProviderQuotaError, ProviderTimeoutError, ProviderUnavailableError
from .models import GenerationRequest, ProviderResponse
from .quota import QuotaManager


class ProviderTransport(Protocol):
    async def generate(self, request: GenerationRequest, model: str) -> ProviderResponse: ...
    async def close(self) -> None: ...


class StreamingProviderTransport(ProviderTransport, Protocol):
    def stream(self, request: GenerationRequest, model: str) -> AsyncIterator[str]: ...


class ProviderRuntime:
    def __init__(self, transport: ProviderTransport, *, quota: QuotaManager, usage_recorder: Callable[[str, str, str, str], None] | None = None, error_recorder: Callable[[str, str, str], None] | None = None, trace_recorder: Callable[[str, str, str, str], None] | None = None) -> None:
        self.transport = transport
        self.quota = quota
        self._usage_recorder = usage_recorder
        self._error_recorder = error_recorder
        self._trace_recorder = trace_recorder

    async def generate(self, request: GenerationRequest) -> ProviderResponse:
        last_error: ProviderError | None = None
        skipped_quota = False
        candidates = request.model_candidates if request.policy.allow_fallback else request.model_candidates[:1]
        for model in candidates:
            if self.quota.remaining(model) > 0:
                skipped_quota = True
                continue
            for _attempt in range(request.policy.retries_per_model):
                try:
                    async with asyncio.timeout(request.policy.timeout_seconds):
                        response = await self.transport.generate(request, model)
                    if not response.text.strip() and not response.tool_calls:
                        raise ProviderEmptyResponseError("Provider returned an empty response")
                except TimeoutError as exc:
                    last_error = ProviderTimeoutError("Provider request timed out")
                    last_error.__cause__ = exc
                    self._record_error(request, model, "timeout")
                    self._record_trace(request, model, "timeout")
                    continue
                except ProviderQuotaError as exc:
                    self.quota.mark_exhausted(model, exc.retry_after_seconds)
                    last_error = exc
                    self._record_error(request, model, "quota")
                    self._record_trace(request, model, "quota")
                    break
                except ProviderUnavailableError as exc:
                    last_error = exc
                    self._record_error(request, model, "unavailable")
                    self._record_trace(request, model, "unavailable")
                    continue
                except ProviderError:
                    self._record_error(request, model, "provider_error")
                    self._record_trace(request, model, "provider_error")
                    raise
                else:
                    self.quota.clear(model)
                    if self._usage_recorder is not None:
                        self._usage_recorder(request.user_id, response.model or model, request.prompt, response.text)
                    self._record_trace(request, response.model or model, "success")
                    return response
        if last_error is not None:
            raise last_error
        if skipped_quota:
            raise ProviderQuotaError("All candidate models are in quota cooldown")
        raise ProviderUnavailableError("No available model")

    async def stream(self, request: GenerationRequest) -> AsyncIterator[str]:
        """Run a native text stream with the same fallback and trace semantics."""

        stream = getattr(self.transport, "stream", None)
        if not callable(stream):
            raise ProviderUnavailableError("Configured provider does not support streaming")
        last_error: ProviderError | None = None
        skipped_quota = False
        candidates = request.model_candidates if request.policy.allow_fallback else request.model_candidates[:1]
        for model in candidates:
            if self.quota.remaining(model) > 0:
                skipped_quota = True
                continue
            for _attempt in range(request.policy.retries_per_model):
                emitted = False
                parts: list[str] = []
                try:
                    async with asyncio.timeout(request.policy.timeout_seconds):
                        async for text in stream(request, model):
                            if text:
                                emitted = True
                                parts.append(text)
                                yield text
                    if not emitted:
                        raise ProviderEmptyResponseError("Provider returned an empty stream")
                except TimeoutError as exc:
                    last_error = ProviderTimeoutError("Provider stream timed out")
                    last_error.__cause__ = exc
                    self._record_error(request, model, "timeout")
                    self._record_trace(request, model, "timeout")
                    if emitted:
                        raise last_error
                    continue
                except ProviderQuotaError as exc:
                    self.quota.mark_exhausted(model, exc.retry_after_seconds)
                    last_error = exc
                    self._record_error(request, model, "quota")
                    self._record_trace(request, model, "quota")
                    if emitted:
                        raise
                    break
                except ProviderUnavailableError as exc:
                    last_error = exc
                    self._record_error(request, model, "unavailable")
                    self._record_trace(request, model, "unavailable")
                    if emitted:
                        raise
                    continue
                except ProviderError:
                    self._record_error(request, model, "provider_error")
                    self._record_trace(request, model, "provider_error")
                    raise
                else:
                    self.quota.clear(model)
                    response = "".join(parts)
                    if self._usage_recorder is not None:
                        self._usage_recorder(request.user_id, model, request.prompt, response)
                    self._record_trace(request, model, "success")
                    return
        if last_error is not None:
            raise last_error
        if skipped_quota:
            raise ProviderQuotaError("All candidate models are in quota cooldown")
        raise ProviderUnavailableError("No available model for streaming")

    async def close(self) -> None:
        await self.transport.close()

    def _record_error(self, request: GenerationRequest, model: str, error_type: str) -> None:
        if self._error_recorder is not None:
            self._error_recorder(request.user_id, model, error_type)

    def _record_trace(self, request: GenerationRequest, model: str, outcome: str) -> None:
        if self._trace_recorder is not None:
            self._trace_recorder(request.request_id, request.user_id, model, outcome)
