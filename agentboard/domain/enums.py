"""Stable browser-v0 domain enumerations."""

from __future__ import annotations

from enum import Enum


class PlanningStage(str, Enum):
    inbox = "inbox"
    clarifying = "clarifying"
    spec = "spec"
    evals = "evals"
    design = "design"
    design_review = "design_review"


class EngineeringState(str, Enum):
    """Schema vocabulary only; derivation belongs to the next feature slice."""

    ready_for_engineering = "ready_for_engineering"
    working = "working"
    in_review = "in_review"
    human_review = "human_review"
    ready_to_merge = "ready_to_merge"
    done = "done"


class SprintState(str, Enum):
    planned = "planned"
    active = "active"
    completed = "completed"
