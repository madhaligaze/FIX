from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class Instance2D:
    label: str
    score: float
    mask_u8: np.ndarray


class InstanceSeg2D:
    def __init__(self, model_path: str | None = None) -> None:
        self.model_path = model_path
        self.available = bool(model_path)

    def predict(self, rgb_bgr: np.ndarray) -> tuple[list[Instance2D], dict[str, Any]]:
        if not self.available:
            return [], {"available": False, "reason": "no_model_configured"}
        return [], {"available": True, "reason": "stub"}
