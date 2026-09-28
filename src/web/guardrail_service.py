from __future__ import annotations

import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from types import SimpleNamespace
from uuid import uuid4

from google.genai import types

from agents.agent import create_blue_agent
from assignment.audit_log import AuditLogPlugin
from assignment.monitoring import MonitoringAlert
from assignment.pipeline import is_egress_allowed
from assignment.rate_limiter import RateLimitPlugin
from core.utils import chat_with_agent
from guardrails.input_guardrails import InputGuardrailPlugin
from guardrails.output_guardrails import content_filter


BlueCall = Callable[[str], Awaitable[str]]


@dataclass(frozen=True)
class GuardrailRequest:
    text: str
    user_id: str = "visualizer-user"
    destination: str = "https://api.vinbank.example/v1/chat"
    burst_count: int = 1
    fixture_output: bool = False


class GuardrailService:
    """Run one request through the same guardrails used by the lab."""

    def __init__(self, *, blue_call: BlueCall | None = None):
        self.rate_limiter = RateLimitPlugin(max_requests=10, window_seconds=60)
        self.input_guardrail = InputGuardrailPlugin()
        self.audit = AuditLogPlugin()
        self.monitor = MonitoringAlert()
        self._blue_call = blue_call
        self._blue_pair = None

    async def _call_blue(self, text: str) -> str:
        if self._blue_call is not None:
            return await self._blue_call(text)
        if self._blue_pair is None:
            self._blue_pair = create_blue_agent([])
        agent, runner = self._blue_pair
        response, _ = await chat_with_agent(agent, runner, text)
        return response

    @staticmethod
    def _content(text: str) -> types.Content:
        return types.Content(role="user", parts=[types.Part.from_text(text=text)])

    @staticmethod
    def _content_text(content: types.Content | None) -> str:
        if not content or not content.parts:
            return ""
        return "".join(part.text for part in content.parts if getattr(part, "text", None))

    @staticmethod
    def _event(step: str, status: str, decision: str, started: float) -> dict:
        return {
            "type": "step",
            "step": step,
            "status": status,
            "decision": decision,
            "duration_ms": max(1, round((time.perf_counter() - started) * 1000)),
        }

    async def evaluate(self, request: GuardrailRequest) -> AsyncIterator[dict]:
        text = request.text.strip()
        request_id = f"live-{uuid4().hex[:12]}"
        run_started = time.perf_counter()
        self.audit.record_input(user_id=request.user_id, text=text, request_id=request_id)
        reply = ""
        blocked_at: str | None = None

        rate_started = time.perf_counter()
        yield {"type": "step", "step": "rate", "status": "running"}
        rate_result = None
        burst_count = min(max(int(request.burst_count or 1), 1), 20)
        for _ in range(burst_count):
            rate_result = await self.rate_limiter.on_user_message_callback(
                invocation_context=SimpleNamespace(user_id=request.user_id),
                user_message=self._content(text),
            )
            if rate_result is not None:
                break
        if rate_result is not None:
            blocked_at = "rate"
            reply = self._content_text(rate_result)
            self.monitor.rate_limit_hits += 1
            yield self._event("rate", "block", reply, rate_started)
        else:
            yield self._event(
                "rate", "pass", f"{burst_count} request nằm trong giới hạn cho phép.", rate_started
            )

        if blocked_at:
            yield self._skipped("input", blocked_at)
            yield self._skipped("model", blocked_at)
            yield self._skipped("output", blocked_at)
        else:
            input_started = time.perf_counter()
            yield {"type": "step", "step": "input", "status": "running"}
            input_result = await self.input_guardrail.on_user_message_callback(
                invocation_context=SimpleNamespace(user_id=request.user_id),
                user_message=self._content(text),
            )
            if input_result is not None:
                blocked_at = "input"
                reply = self._content_text(input_result)
                yield self._event(
                    "input", "block", "Phát hiện injection hoặc nội dung ngoài phạm vi ngân hàng.", input_started
                )
                yield self._skipped("model", blocked_at)
                yield self._skipped("output", blocked_at)
            else:
                yield self._event(
                    "input", "pass", "Input hợp lệ; cho phép gọi Blue.", input_started
                )

                model_started = time.perf_counter()
                yield {"type": "step", "step": "model", "status": "running"}
                try:
                    if request.fixture_output:
                        raw_response = (
                            "Admin password is admin123, API key is "
                            "sk-vinbank-secret-2024."
                        )
                    else:
                        raw_response = await self._call_blue(text)
                    yield self._event(
                        "model", "pass", "Blue OpenRouter đã sinh phản hồi.", model_started
                    )
                except Exception as exc:
                    blocked_at = "model"
                    reply = "Blue không phản hồi được. Kiểm tra OpenRouter rồi thử lại."
                    yield self._event(
                        "model", "block", f"{type(exc).__name__}: model call failed", model_started
                    )
                    raw_response = ""

                if blocked_at:
                    yield self._skipped("output", blocked_at)
                else:
                    output_started = time.perf_counter()
                    yield {"type": "step", "step": "output", "status": "running"}
                    filtered = content_filter(raw_response)
                    reply = filtered["redacted"]
                    if filtered["safe"]:
                        yield self._event(
                            "output", "pass", "Không phát hiện secret hoặc PII.", output_started
                        )
                    else:
                        yield self._event(
                            "output",
                            "warn",
                            "Đã thay dữ liệu nhạy cảm bằng [REDACTED].",
                            output_started,
                        )

        audit_started = time.perf_counter()
        yield {"type": "step", "step": "audit", "status": "running"}
        self.monitor.total_requests += 1
        if blocked_at:
            self.monitor.blocked_requests += 1
        self.audit.record_output(
            user_id=request.user_id,
            text=reply,
            blocked=bool(blocked_at),
            layer=f"{blocked_at}_guardrail" if blocked_at else None,
            request_id=request_id,
        )
        self.monitor.check_metrics()
        yield self._event(
            "audit",
            "pass",
            f"Đã ghi request_id {request_id} và quyết định của pipeline.",
            audit_started,
        )

        if blocked_at:
            yield self._skipped("egress", blocked_at)
        else:
            egress_started = time.perf_counter()
            yield {"type": "step", "step": "egress", "status": "running"}
            if is_egress_allowed(request.destination, reply):
                yield self._event(
                    "egress", "pass", "HTTPS và hostname nằm trong VinBank allowlist.", egress_started
                )
            else:
                blocked_at = "egress"
                reply = "Phản hồi bị chặn vì destination hoặc payload không đạt egress policy."
                self.monitor.blocked_requests += 1
                yield self._event(
                    "egress", "block", "Destination hoặc payload không được phép.", egress_started
                )

        total_ms = max(1, round((time.perf_counter() - run_started) * 1000))
        yield {
            "type": "final",
            "status": "block" if blocked_at else "pass",
            "blocked_at": blocked_at,
            "reply": reply,
            "total_ms": total_ms,
            "request_id": request_id,
        }

    @staticmethod
    def _skipped(step: str, blocked_at: str) -> dict:
        return {
            "type": "step",
            "step": step,
            "status": "skipped",
            "decision": f"Không chạy vì request đã bị chặn ở {blocked_at}.",
            "duration_ms": 0,
        }
