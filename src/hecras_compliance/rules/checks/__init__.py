"""Registry of custom check handlers.

Each handler has the signature::

    (rule: dict, model_data: ModelData) -> list[dict]

The returned dicts are converted to :class:`RuleResult` by the engine.
"""

from __future__ import annotations

from typing import Any, Callable

from .profiles import check_profile_exists, check_100yr_profile_exists
from .boundaries import check_boundary_conditions_defined
from .review import flag_for_manual_review

HANDLER_REGISTRY: dict[str, Callable[..., list[dict]]] = {
    "check_profile_exists": check_profile_exists,
    "check_100yr_profile_exists": check_100yr_profile_exists,
    "check_boundary_conditions_defined": check_boundary_conditions_defined,
    "flag_for_manual_review": flag_for_manual_review,
}
