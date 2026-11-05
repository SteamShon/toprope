"""Declarations: models, loading, structural validation and the domain interface."""

from __future__ import annotations

from pathlib import Path

from .interface import Element, InterfaceDiff, ReviewDiff, diff_interface, interface, review_contents, review_diff, review_elements
from .models import Domain
from .validate import Issue, check_handoffs, validate_domain
from .yamlio import load_yaml


def load_domain(path: str | Path) -> Domain:
    """Load and parse a `*.domain.yaml`. Raises pydantic.ValidationError on shape errors."""
    with open(path) as f:
        return Domain.model_validate(load_yaml(f.read()))


__all__ = ["Domain", "Element", "ReviewDiff", "check_handoffs", "review_contents", "review_diff", "review_elements", "Issue", "InterfaceDiff", "diff_interface", "interface",
           "load_domain", "load_yaml", "validate_domain"]
