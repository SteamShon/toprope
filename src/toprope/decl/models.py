"""Declaration models (docs/domain-schema.md). Strict: unknown keys are errors, so typos surface."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from typing import Annotated

Ident = Annotated[str, StringConstraints(pattern=r"^[A-Za-z_][A-Za-z0-9_-]*$")]
RESERVED_ACTORS = {"system", "external:kernel"}   # other `external:<source>` actors: M0b (ADR-0028)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


def not_yet(construct: str, milestone: str) -> ValueError:
    """A construct defined in schema v1 but not implemented by this kernel (ADR-0023)."""
    return ValueError(f"`{construct}` is defined in schema v1 (docs/domain-schema.md) but not "
                      f"implemented until {milestone}; refusing to run it silently")


class Status(str, Enum):
    proposed = "proposed"
    confirmed = "confirmed"
    unknown = "unknown"


class Source(Strict):
    kind: Literal["system", "record", "interview", "use"]
    ref: str | None = None
    quote: str | None = None


class Provenance(Strict):
    """Every element may carry where it came from and whether a human confirmed it (ADR-0004)."""

    source: Source | None = None
    status: Status | None = None


class Property(Strict):
    type: Literal["string", "integer", "number", "boolean", "datetime"] | None = None
    enum: list[str] | None = None
    optional: bool = False
    min: float | None = None
    max: float | None = None

    @model_validator(mode="after")
    def _one_kind(self) -> Property:
        if (self.type is None) == (self.enum is None):
            raise ValueError("a property has exactly one of `type` or `enum`")
        return self


class ObjectType(Provenance):
    description: str | None = None
    properties: dict[str, Property] = Field(default_factory=dict)


class Link(Provenance):
    from_: str = Field(alias="from")
    to: str
    cardinality: Literal["one-to-one", "one-to-many", "many-to-one", "many-to-many"]
    required: bool = False


class Param(Strict):
    type: Literal["string", "integer", "number", "boolean", "datetime"] | None = None
    enum: list[str] | None = None
    ref: str | None = None
    many: bool = False
    optional: bool = False

    @model_validator(mode="after")
    def _one_kind(self) -> Param:
        if sum(x is not None for x in (self.type, self.enum, self.ref)) != 1:
            raise ValueError("a param has exactly one of `type`, `enum` or `ref`")
        return self


class Precondition(Provenance):
    id: Ident
    check: str
    reason: str


class ActorRule(Strict):
    role: str
    where: str | None = None


class Effect(Strict):
    set: dict[str, Union[str, int, float, bool, None]] | None = None
    create: str | None = None   # not in v1: rejected at compile time (ADR-0021)
    call: str | None = None     # a kernel service (ADR-0028)
    with_: dict[str, str] = Field(default_factory=dict, alias="with")   # service input → expression
    reply: str | None = None    # the action that receives the service's result

    @model_validator(mode="after")
    def _one_kind(self) -> Effect:
        if sum(x is not None for x in (self.set, self.create, self.call)) != 1:
            raise ValueError("an effect is exactly one of `set`, `create` or `call`")
        if self.call is None and (self.with_ or self.reply):
            raise ValueError("`with` and `reply` belong to a `call` effect")
        if self.call is not None and not self.reply:
            raise ValueError("a `call` effect names the `reply` action that receives the result")
        return self


class Action(Provenance):
    description: str
    actor: Annotated[list[Union[str, ActorRule]], Field(min_length=1)]
    target: str | None = None
    creates: str | None = None
    params: dict[str, Param] = Field(default_factory=dict)
    preconditions: list[Precondition] = Field(default_factory=list)
    effects: list[Effect] = Field(default_factory=list)
    records_decision: bool = False
    event: str | None = None
    applies_in: list[str] | None = None
    requires: Literal["human"] | None = None
    approvals: dict[str, Any] | None = None

    @model_validator(mode="before")
    @classmethod
    def _rationale(cls, raw: Any) -> Any:
        """A decision action takes an optional `rationale` (ADR-0041, Resolved 2): the reason a
        person gives, stored with the decision. It is added here, so every surface offers it."""
        if isinstance(raw, dict) and raw.get("records_decision"):
            params = dict(raw.get("params") or {})
            if "rationale" in params:
                raise ValueError("`rationale` is reserved on a decision action: every one takes it")
            params["rationale"] = {"type": "string", "optional": True}
            raw = {**raw, "params": params}
        return raw

    @model_validator(mode="after")
    def _target_or_creates(self) -> Action:
        if (self.target is None) == (self.creates is None):
            raise ValueError("an action has exactly one of `target` or `creates`")
        if self.approvals is not None:
            raise not_yet("approvals", "M0b")
        for r in self.actor:
            if isinstance(r, str) and r.startswith("external:") and r != "external:kernel":
                raise not_yet("external actors other than `external:kernel` (ADR-0028)", "M0b")
        return self

    @property
    def object_type(self) -> str:
        return self.target or self.creates  # type: ignore[return-value]


class Deny(Provenance):
    deny: str


class Target(Provenance):
    to: str


class ByRole(Provenance):
    """Per-role outcome: {by_role: {approver: approved, eng: {deny: "..."}}}. Roles not listed
    are `n/a` for this cell (docs/semantics.md step 5 resolves the actor's role)."""

    by_role: dict[str, Union[str, Deny]]


# A matrix cell: "<state>" | "n/a" | "undecided" | {deny: reason} | {to: state, ...} | {by_role: {...}}
Cell = Union[str, Deny, Target, ByRole]


class Transitions(Strict):
    field: str
    initial: str | None = None
    matrix: dict[str, dict[str, Cell]]


class Invariant(Provenance):
    id: Ident
    on: str
    check: str
    reason: str
    scope: Literal["aggregate", "cross"] = "aggregate"
    enforced_by: str | None = None

    @model_validator(mode="after")
    def _cross_not_yet(self) -> Invariant:
        if self.enforced_by is not None and self.scope != "cross":
            raise ValueError("`enforced_by` is only valid on `scope: cross` invariants")
        if self.scope == "cross":   # would otherwise be skipped by the guard: fail closed
            raise not_yet("invariants[].scope: cross", "M0b")
        return self


class World(Strict):
    fixtures: list[dict[str, dict[str, Any]]] = Field(default_factory=list)
    actors: dict[str, list[str]] = Field(default_factory=dict)


class Step(Strict):
    actor: dict[str, Any] = Field(default_factory=dict)
    advance: dict[str, Any] | None = None
    do: str | None = None
    read: dict[str, Any] | None = None
    target: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    expect: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _do_or_read(self) -> Step:
        if self.advance is not None:
            raise not_yet("scenario `advance` steps", "M0b")
        if (self.do is None) == (self.read is None):
            raise ValueError("a step has exactly one of `do` or `read`")
        if not self.actor:
            raise ValueError("a `do` or `read` step needs an actor")
        return self


class Scenario(Strict):
    id: Ident
    given: dict[str, Any] = Field(default_factory=dict)
    steps: list[Step]


class SuccessMetric(Strict):
    name: str
    direction: Literal["up", "down"]
    definition: str | None = None


class Purpose(Strict):
    """Why the domain exists (metadata only; never changes behavior)."""

    problem: str
    success_metric: SuccessMetric | None = None
    announcement: str | None = None


NOT_YET = {"reservations": "M0b", "timers": "M0b", "functions": "M0b", "external": "M0b"}


class HandoffWhen(Strict):
    action: str
    outcome: Literal["ok"] = "ok"


class HandoffTo(Strict):
    domain: Ident
    interface: Annotated[str, StringConstraints(pattern=r"^[0-9]+\.x$")]   # a major range, e.g. "1.x"
    action: str


class Handoff(Provenance):
    """A typed request into another domain's published interface, sent from the outbox after
    the sender's action is appended (ADR-0022, docs/semantics.md step 12)."""

    when: HandoffWhen
    to: HandoffTo
    params: dict[str, str] = Field(default_factory=dict)   # receiver param → expression
    target: str                                              # expression: the receiver's target id


class Domain(Strict):
    domain: Ident
    version: Annotated[int, Field(ge=1)]
    owner: str | None = None
    purpose: Purpose | None = None
    handoffs: dict[str, Handoff] = Field(default_factory=dict)
    reservations: dict[str, Any] | None = None
    timers: dict[str, Any] | None = None
    functions: dict[str, Any] | None = None
    external: dict[str, Any] | None = None
    glossary: dict[str, str] = Field(default_factory=dict)
    roles: list[str] = Field(default_factory=list)
    objects: dict[str, ObjectType] = Field(default_factory=dict)
    links: dict[str, Link] = Field(default_factory=dict)
    actions: dict[str, Action] = Field(default_factory=dict)
    transitions: dict[str, Transitions] = Field(default_factory=dict)
    invariants: list[Invariant] = Field(default_factory=list)
    world: World = Field(default_factory=World)
    scenarios: list[Scenario] = Field(default_factory=list)

    @model_validator(mode="after")
    def _not_yet(self) -> Domain:
        for key, milestone in NOT_YET.items():
            if getattr(self, key):
                raise not_yet(key, milestone)
        return self
