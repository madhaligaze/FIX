from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LayherLikeSpec:
    """MVP dimensional rules for a Layher-like frame system."""

    ledger_lengths_m: tuple[float, ...] = (0.73, 1.09, 1.57, 2.07, 2.57, 3.07)
    transom_lengths_m: tuple[float, ...] = (0.73, 1.09, 1.57, 2.07)
    min_bay_m: float = 1.57
    max_bay_m: float = 3.07
    post_radius_m: float = 0.03
    ledger_radius_m: float = 0.02
    brace_radius_m: float = 0.02
    default_height_m: float = 4.0


DEFAULT_SPEC = LayherLikeSpec()
