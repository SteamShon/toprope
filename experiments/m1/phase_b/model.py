"""The model every Phase B role talks to (ADR-0040 §1, §7), and the cost cap (§2).

The model under test is experiment data: its id comes from the environment (`M1_MODEL`), never
from code. `AnthropicModel` calls the Messages API over HTTPS with the standard library, so the
harness adds no dependency; `FakeModel` replays a script, for tests.

Prices are the researcher's, per million tokens, from the environment:
`M1_PRICES="input,output,cache_write,cache_read"`. The cap is `M1_COST_CAP_USD`.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"


class BudgetExceeded(RuntimeError):
    """The run reached the researcher's cost cap; nothing more is sent."""


class ModelError(RuntimeError):
    pass


@dataclass
class Usage:
    input: int = 0
    output: int = 0
    cache_write: int = 0
    cache_read: int = 0

    @classmethod
    def of(cls, u: dict[str, Any]) -> Usage:
        return cls(int(u.get("input_tokens") or 0), int(u.get("output_tokens") or 0),
                   int(u.get("cache_creation_input_tokens") or 0), int(u.get("cache_read_input_tokens") or 0))

    def __add__(self, o: Usage) -> Usage:
        return Usage(self.input + o.input, self.output + o.output, self.cache_write + o.cache_write,
                     self.cache_read + o.cache_read)


@dataclass
class Budget:
    """Counts tokens and dollars; refuses a call once the cap is reached."""
    prices: tuple[float, float, float, float]          # USD per million: input, output, cache write, read
    cap_usd: float
    used: Usage = field(default_factory=Usage)

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> Budget:
        env = os.environ if env is None else env
        try:
            prices = tuple(float(x) for x in env["M1_PRICES"].split(","))
            cap = float(env["M1_COST_CAP_USD"])
        except KeyError as e:
            raise SystemExit(f"set {e.args[0]} (ADR-0040 §2)") from None
        except ValueError:
            raise SystemExit("M1_PRICES is four numbers, M1_COST_CAP_USD one") from None
        if len(prices) != 4 or cap <= 0:
            raise SystemExit("M1_PRICES is input,output,cache_write,cache_read per million tokens; the cap is > 0")
        return cls(prices, cap)  # type: ignore[arg-type]

    def cost(self, u: Usage | None = None) -> float:
        u = self.used if u is None else u
        p = self.prices
        return (u.input * p[0] + u.output * p[1] + u.cache_write * p[2] + u.cache_read * p[3]) / 1e6

    def check(self) -> None:
        if self.cost() >= self.cap_usd:
            raise BudgetExceeded(f"spent ${self.cost():.2f} of the ${self.cap_usd:.2f} cap")

    def add(self, u: Usage) -> None:
        self.used = self.used + u

    def report(self) -> dict[str, Any]:
        return {"tokens": asdict(self.used), "usd": round(self.cost(), 4), "cap_usd": self.cap_usd}


# A model is called with (system, messages, tools) and answers with the API's reply:
# {"content": [blocks], "stop_reason": str, "usage": {...}}.
Model = Callable[[str, list[dict[str, Any]], list[dict[str, Any]]], dict[str, Any]]


class AnthropicModel:
    def __init__(self, model: str, api_key: str, budget: Budget, max_tokens: int = 8192,
                 url: str = API_URL, retries: int = 5):
        if not model:
            raise SystemExit("set M1_MODEL: the model under test (ADR-0040 §7)")
        self.model, self.key, self.budget = model, api_key, budget
        self.max_tokens, self.url, self.retries = max_tokens, url, retries

    @classmethod
    def from_env(cls, budget: Budget) -> AnthropicModel:
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            raise SystemExit("set ANTHROPIC_API_KEY (the `researcher` environment's secret)")
        return cls(os.environ.get("M1_MODEL", ""), key, budget)

    def __call__(self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        self.budget.check()
        body = {"model": self.model, "max_tokens": self.max_tokens, "messages": messages,
                "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]}
        if tools:
            body["tools"] = tools
        data = json.dumps(body).encode()
        for attempt in range(self.retries + 1):
            req = urllib.request.Request(self.url, data=data, method="POST", headers={
                "content-type": "application/json", "x-api-key": self.key, "anthropic-version": API_VERSION})
            try:
                with urllib.request.urlopen(req, timeout=600) as r:
                    reply = json.loads(r.read())
                break
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503, 529) and attempt < self.retries:
                    time.sleep(min(60, 2 ** (attempt + 1)))
                    continue
                raise ModelError(f"{e.code}: {e.read()[:500]!r}") from None
            except (urllib.error.URLError, TimeoutError) as e:
                if attempt < self.retries:
                    time.sleep(min(60, 2 ** (attempt + 1)))
                    continue
                raise ModelError(str(e)) from None
        self.budget.add(Usage.of(reply.get("usage") or {}))
        return reply


class FakeModel:
    """Answers from a script: a function of (system, messages, tools), or a list of replies in
    order. Each reply is the API's shape, or just a string (one text block)."""

    def __init__(self, script: Callable[..., Any] | list[Any], budget: Budget | None = None):
        self.script, self.budget, self.calls = script, budget, []

    def __call__(self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        if self.budget:
            self.budget.check()
        self.calls.append({"system": system, "messages": json.loads(json.dumps(messages)), "tools": tools})
        out = self.script(system, messages, tools) if callable(self.script) else self.script.pop(0)
        if isinstance(out, str):
            out = {"content": [{"type": "text", "text": out}], "stop_reason": "end_turn"}
        out.setdefault("usage", {"input_tokens": 100, "output_tokens": 10})
        if self.budget:
            self.budget.add(Usage.of(out["usage"]))
        return out


def tool_use(name: str, input: dict[str, Any], id: str = "t1") -> dict[str, Any]:
    """A fake reply that calls one tool."""
    return {"content": [{"type": "tool_use", "id": id, "name": name, "input": input}], "stop_reason": "tool_use"}
