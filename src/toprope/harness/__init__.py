"""The generated harness (ADR-0010): small world, cell/precondition/create tests, invariant
checks, parity across levels, replay parity, race tests, bounded exploration, example flows
and coverage. Levels in M0a: the model interpreter, Execution and MCP (A2UI views in M0b)."""

from .run import DEFAULT_LEVELS, Finding, Harness, Report, run_harness
from .world import SmallWorld, grow_world

__all__ = ["DEFAULT_LEVELS", "Finding", "Harness", "Report", "SmallWorld", "grow_world", "run_harness"]
