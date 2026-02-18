# modules/detector_2d.py
"""
2D detector wrapper (Stage 2)
-----------------------------

Goal: provide a simple, optional 2D detector interface:

    detector = Detector2D(...)
    dets = detector.infer(image_bytes)

Output format (Det2D-like dicts):
    {class_label, bbox_xyxy, score, mask_rle(optional)=None}

Notes:
- This module must NOT hard-require cv2. It uses Pillow + numpy.
- If ultralytics is missing, returns [] (graceful fallback).
"""
from __future__ import annotations

import logging
import io
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np

try:
    from PIL import Image
    _PIL_OK = True
except Exception:
    Image = None
    _PIL_OK = False

try:
    from ultralytics import YOLO
    _YOLO_OK = True
except Exception:
    YOLO = None
    _YOLO_OK = False

logger = logging.getLogger(__name__)


@dataclass
class DetectorConfig:
    model_path: str = "yolov8n.pt"
    conf_thres: float = 0.25
    iou_thres: float = 0.45
    max_det: int = 50


class Detector2D:
    def __init__(self, cfg: Optional[DetectorConfig] = None) -> None:
        self.cfg = cfg or DetectorConfig()
        self.model = None
        if not _PIL_OK:
            logger.warning("Pillow is not available; Detector2D will be disabled.")
            return
        if not _YOLO_OK:
            logger.info("ultralytics is not available; Detector2D will run in fallback mode (no detections).")
            return
        try:
            self.model = YOLO(self.cfg.model_path)
            logger.info("2D detector loaded: %s", self.cfg.model_path)
        except Exception as e:
            logger.warning("Failed to load YOLO model (%s): %s", self.cfg.model_path, e)
            self.model = None

    @property
    def available(self) -> bool:
        return self.model is not None

    def infer(self, image_bytes: bytes) -> List[Dict[str, Any]]:
        if self.model is None:
            return []
        if not _PIL_OK:
            return []

        # Load image as RGB numpy
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")

        img_np = np.array(img)  # H,W,3 RGB

        try:
            results = self.model.predict(
                source=img_np,
                conf=self.cfg.conf_thres,
                iou=self.cfg.iou_thres,
                max_det=self.cfg.max_det,
                verbose=False,
            )
        except Exception as e:
            logger.warning("Detector2D inference failed: %s", e)
            return []

        dets: List[Dict[str, Any]] = []
        if not results:
            return dets

        r0 = results[0]
        names = getattr(r0, "names", {}) or {}
        boxes = getattr(r0, "boxes", None)
        if boxes is None:
            return dets

        xyxy = getattr(boxes, "xyxy", None)
        cls = getattr(boxes, "cls", None)
        conf = getattr(boxes, "conf", None)
        if xyxy is None or cls is None or conf is None:
            return dets

        xyxy = xyxy.cpu().numpy()
        cls = cls.cpu().numpy()
        conf = conf.cpu().numpy()

        for (x1, y1, x2, y2), c, s in zip(xyxy, cls, conf):
            c_int = int(c)
            label = names.get(c_int, f"class_{c_int}")
            dets.append(
                {
                    "class_label": str(label),
                    "bbox_xyxy": [float(x1), float(y1), float(x2), float(y2)],
                    "score": float(s),
                    "mask_rle": None,
                }
            )
        return dets
