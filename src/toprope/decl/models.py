"""Declaration models (docs/domain-schema.md). Strict: unknown keys are errors, so typos surface."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


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
    id: str
    check: str
    reason: str


class ActorRule(Strict):
    role: str
    where: str | None = None


class Effect(Strict):
    set: dict[str, Any] | None = None
    create: str | None = None


class Action(Provenance):
    description: str
    actor: list[Union[str, ActorRule]]
    target: str | None = None
    creates: str | None = None
    params: dict[str, Param] = Field(default_factory=dict)
    preconditions: list[Precondition] = Field(default_factory=list)
    effects: list[Effect] = Field(default_factory=list)
    records_decision: bool = False
    event: str | None = None
    applies_in: list[str] | None = None
    requires: Literal["human"] | None = None

    @model_validator(mode="after")
    def _target_or_creates(self) -> Action:
        if (self.target is None) == (self.creates is None):
            raise ValueError("an action has exactly one of `target` or `creates`")
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
    id: str
    on: str
    check: str
    reason: str
    scope: Literal["aggregate", "cross"] = "aggregate"


class World(Strict):
    fixtures: list[dict[str, dict[str, Any]]] = Field(default_factory=list)
    actors: dict[str, list[str]] = Field(default_factory=dict)


class Step(Strict):
    actor: dict[str, Any]
    do: str | None = None
    read: dict[str, Any] | None = None
    target: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    expect: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _do_or_read(self) -> Step:
        if (self.do is None) == (self.read is None):
            raise ValueError("a step has exactly one of `do` or `read`")
        return self


class Scenario(Strict):
    id: str
    given: dict[str, Any] = Field(default_factory=dict)
    steps: list[Step]


class Domain(Strict):
    domain: str
    version: int
    owner: str | None = None
    glossary: dict[str, str] = Field(default_factory=dict)
    roles: list[str] = Field(default_factory=list)
    objects: dict[str, ObjectType] = Field(default_factory=dict)
    links: dict[str, Link] = Field(default_factory=dict)
    actions: dict[str, Action] = Field(default_factory=dict)
    transitions: dict[str, Transitions] = Field(default_factory=dict)
    invariants: list[Invariant] = Field(default_factory=list)
    world: World = Field(default_factory=World)
    scenarios: list[Scenario] = Field(default_factory=list)
