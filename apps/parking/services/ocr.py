"""
OCR Service & PlateRecognizer Interface for Parking Management Backend.
Provides clean abstraction for license-plate detection & character recognition.
Default engine: FastAlprPlateRecognizer (Dual-OCR Ensemble: CCT-xs-v2 + Mobile-ViT-v2, MIT, ONNX).
Test double: DummyPlateRecognizer for deterministic unit testing.
Plate OCR recognition service using offline ONNX Runtime dual-ensemble model.
"""

from __future__ import annotations

import abc
import io
import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from django.conf import settings
from PIL import Image

logger = logging.getLogger(__name__)

# Named constants for OCR execution and adaptive ensemble calibration (J6)
DEFAULT_OCR_ADAPTIVE_THRESHOLD: float = 94.0
DEFAULT_OCR_LEADING_CHAR_THRESHOLD: float = 99.2
DEFAULT_OCR_ADAPTIVE_AVG_THRESHOLD: float = 96.0
DEFAULT_OCR_CROP_MARGIN: int = 4


@dataclass(frozen=True)
class BoundingBox:
    """Tọa độ hộp bao biển số xe (pixel)."""

    x1: int
    y1: int
    x2: int
    y2: int

    def to_dict(self) -> dict[str, int]:
        return {"x1": self.x1, "y1": self.y1, "x2": self.x2, "y2": self.y2}


@dataclass(frozen=True)
class PlateCandidate:
    """Ứng viên biển số xe nhận dạng được."""

    plate_text: str  # Chuỗi ký tự thô do OCR đọc (vd: "51K-992.14")
    plate_normalized: str  # Chuỗi chuẩn hóa (vd: "51K99214")
    confidence: float  # Độ tin cậy trung bình thang điểm 0.00 .. 100.00
    char_confidences: list[float] | None = (
        None  # Độ tin cậy từng ký tự (0.00 .. 100.00)
    )
    min_char_confidence: float | None = (
        None  # Độ tin cậy ký tự thấp nhất (0.00 .. 100.00)
    )
    bounding_box: BoundingBox | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "plate_text": self.plate_text,
            "plate_normalized": self.plate_normalized,
            "confidence": round(self.confidence, 2),
            "char_confidences": (
                [round(c, 2) for c in self.char_confidences]
                if self.char_confidences is not None
                else None
            ),
            "min_char_confidence": (
                round(self.min_char_confidence, 2)
                if self.min_char_confidence is not None
                else None
            ),
            "bounding_box": self.bounding_box.to_dict() if self.bounding_box else None,
        }


@dataclass(frozen=True)
class PlateScanResult:
    """Kết quả quét biển số tổng thể từ hình ảnh (Dual-OCR Ensemble)."""

    candidates: list[PlateCandidate]
    best_candidate: PlateCandidate | None
    engine_name: str
    raw_text: str
    latency_ms: float
    model_agreement: bool = True
    used_detection_fallback: bool = False
    cct_plate: str = ""
    mv2_plate: str = ""
    cct_min_conf: float = 0.0
    mv2_min_conf: float = 0.0
    review_status: str = "AUTO"
    review_reasons: list[str] = field(default_factory=list)
    corrections: list[dict[str, Any]] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    detect_ms: float = 0.0
    ocr1_ms: float = 0.0
    ocr2_ms: float = 0.0


class PlateRecognizer(abc.ABC):
    """Abstract Base Class định nghĩa giao tiếp nhận dạng biển số xe."""

    @abc.abstractmethod
    def recognize(self, image_data: bytes | Image.Image) -> PlateScanResult:
        """Nhận dạng biển số xe từ dữ liệu ảnh và trả về danh sách candidates."""
        pass

    @staticmethod
    def normalize_plate(raw_text: str) -> str:
        """Chuẩn hóa biển số xe tương đương hàm PostgreSQL fn_normalize_license_plate."""
        return re.sub(r"[^A-Za-z0-9]", "", (raw_text or "")).upper()


class FastAlprPlateRecognizer(PlateRecognizer):
    """
    Triển khai nhận dạng biển số xe Dual-OCR Ensemble (MIT License, ONNX Runtime).
    Detector: YOLOv9-t 384 ONNX (với cơ chế Fallback Detection retry conf_thresh=0.02).
    Dual-OCR Models:
      1. CCT-xs-v2 Global (RGB 3 kênh).
      2. Mobile-ViT-v2 Global (Grayscale 1 kênh).
    Cấu hình SessionOptions tối ưu chống CPU thread oversubscription.
    """

    def __init__(self) -> None:
        self._detector: Any = None
        self._fallback_detector: Any = None
        self._ocr_cct: Any = None
        self._ocr_mv2: Any = None
        self._init_error: Exception | None = None
        self._is_ready: bool = False
        self._warmup_lock = threading.Lock()
        self._initialize()

    def _initialize(self) -> None:
        try:
            import fast_plate_ocr
            import onnxruntime as ort
            import open_image_models

            opts = ort.SessionOptions()
            opts.log_severity_level = 3
            opts.intra_op_num_threads = int(settings.ONNX_INTRA_OP_THREADS)
            opts.inter_op_num_threads = int(settings.ONNX_INTER_OP_THREADS)
            # Official ONNX Runtime Thread Management:
            # session.intra_op.allow_spinning: "0" disables busy-waiting spin loops in the intra-op thread pool,
            # preventing CPU starvation and excessive core thrashing in multi-worker / multi-threaded environments.
            allow_spinning = bool(settings.ONNX_ALLOW_SPINNING)
            opts.add_session_config_entry(
                "session.intra_op.allow_spinning", "1" if allow_spinning else "0"
            )
            opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            opts.enable_cpu_mem_arena = True
            opts.enable_mem_pattern = True
            opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL

            # Resolved OCR models directory from settings (Standard 4, H4d & H8a)
            models_dir = Path(settings.PARKING_OCR_MODELS_DIR)

            # 1. Primary & Fallback Detectors
            det384_file = models_dir / "yolo-v9-t-384-license-plates-end2end.onnx"
            det640_file = models_dir / "yolo-v9-t-640-license-plates-end2end.onnx"

            if det384_file.is_file():
                self._detector = open_image_models.create_detector(
                    model=det384_file,
                    backend="yolo_v9",
                    class_labels=["license-plate"],
                    conf_thresh=0.40,
                    sess_options=opts,
                )
            else:
                self._detector = open_image_models.create_detector(
                    model="yolo-v9-t-384-license-plate-end2end",
                    conf_thresh=0.40,
                    sess_options=opts,
                )

            # Fallback detector (A4): Lower threshold retry or 640
            if det640_file.is_file():
                self._fallback_detector = open_image_models.create_detector(
                    model=det640_file,
                    backend="yolo_v9",
                    class_labels=["license-plate"],
                    conf_thresh=0.20,
                    sess_options=opts,
                )
            elif det384_file.is_file():
                self._fallback_detector = open_image_models.create_detector(
                    model=det384_file,
                    backend="yolo_v9",
                    class_labels=["license-plate"],
                    conf_thresh=0.02,
                    sess_options=opts,
                )
            else:
                self._fallback_detector = open_image_models.create_detector(
                    model="yolo-v9-t-384-license-plate-end2end",
                    conf_thresh=0.02,
                    sess_options=opts,
                )

            # 2. CCT-xs-v2 Model (RGB 3 channels)
            cct_model_file = models_dir / "cct_xs_v2_global.onnx"
            cct_cfg_file = models_dir / "cct_xs_v2_global_plate_config.yaml"
            if cct_model_file.is_file() and cct_cfg_file.is_file():
                self._ocr_cct = fast_plate_ocr.LicensePlateRecognizer(
                    onnx_model_path=cct_model_file,
                    plate_config_path=cct_cfg_file,
                    sess_options=opts,
                )
            else:
                self._ocr_cct = fast_plate_ocr.LicensePlateRecognizer(
                    hub_ocr_model="cct-xs-v2-global-model",
                    sess_options=opts,
                )

            # 3. Mobile-ViT-v2 Model (Grayscale 1 channel)
            mv2_model_file = models_dir / "global_mobile_vit_v2_ocr.onnx"
            mv2_cfg_file = models_dir / "global_mobile_vit_v2_ocr_config.yaml"
            if mv2_model_file.is_file() and mv2_cfg_file.is_file():
                self._ocr_mv2 = fast_plate_ocr.LicensePlateRecognizer(
                    onnx_model_path=mv2_model_file,
                    plate_config_path=mv2_cfg_file,
                    sess_options=opts,
                )
            else:
                self._ocr_mv2 = fast_plate_ocr.LicensePlateRecognizer(
                    hub_ocr_model="global-plates-mobile-vit-v2-model",
                    sess_options=opts,
                )

            logger.info(
                "FastAlprPlateRecognizer (Dual-OCR Ensemble) initialized successfully."
            )
        except Exception as exc:
            self._init_error = exc
            logger.exception("FastAlprPlateRecognizer initialization failed: %s", exc)

    def warmup(self) -> bool:
        """Khởi động bộ cấp phát bộ nhớ ONNX trên ảnh synthetic để triệt tiêu cold-start."""
        with self._warmup_lock:
            if self._is_ready:
                return True
            if self._detector is None or self._ocr_cct is None or self._ocr_mv2 is None:
                return False
            try:
                import cv2

                dummy_full = np.zeros((480, 640, 3), dtype=np.uint8)
                self._detector.predict(dummy_full)
                if self._fallback_detector is not None:
                    self._fallback_detector.predict(dummy_full)

                dummy_crop = np.zeros((48, 140, 3), dtype=np.uint8)
                dummy_rgb = cv2.cvtColor(dummy_crop, cv2.COLOR_BGR2RGB)
                dummy_gray = cv2.cvtColor(dummy_crop, cv2.COLOR_BGR2GRAY)

                self._ocr_cct.run_one(dummy_rgb, return_confidence=True)
                self._ocr_mv2.run_one(dummy_gray, return_confidence=True)

                self._is_ready = True
                logger.info("Dual-OCR Ensemble ONNX warm-up completed successfully.")
                return True
            except Exception as exc:
                logger.warning("Dual-OCR Ensemble ONNX warm-up failed: %s", exc)
                return False

    @property
    def is_ready(self) -> bool:
        return (
            self._is_ready
            and self._detector is not None
            and self._ocr_cct is not None
            and self._ocr_mv2 is not None
        )

    def recognize(self, image_data: bytes | Image.Image) -> PlateScanResult:
        start_time = time.perf_counter()

        if not self.is_ready and self._detector is None:
            raise RuntimeError(f"FastAlpr initialization failed: {self._init_error}")

        import cv2

        # Chuyển đổi dữ liệu ảnh sang mảng NumPy BGR
        if isinstance(image_data, bytes):
            with Image.open(io.BytesIO(image_data)) as pil_img:
                img_rgb = np.asarray(
                    pil_img if pil_img.mode == "RGB" else pil_img.convert("RGB")
                )
                img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)
        elif isinstance(image_data, Image.Image):
            img_rgb = np.asarray(
                image_data if image_data.mode == "RGB" else image_data.convert("RGB")
            )
            img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)
        else:
            raise TypeError("image_data must be bytes or PIL.Image.Image")

        # 1. Chạy detector chính (384, conf=0.40)
        t_det0 = time.perf_counter()
        detections = self._detector.predict(img_bgr)
        used_fallback = False

        # 2. Fallback Detection (A4): Khi lần 1 không tìm thấy biển số, retry với fallback detector
        if not detections and self._fallback_detector is not None:
            detections = self._fallback_detector.predict(img_bgr)
            if detections:
                used_fallback = True
        detect_ms = (time.perf_counter() - t_det0) * 1000.0

        candidates: list[PlateCandidate] = []
        raw_texts: list[str] = []
        model_agreement_overall = True
        cct_primary_plate = ""
        mv2_primary_plate = ""
        cct_primary_min_conf = 0.0
        mv2_primary_min_conf = 0.0
        ocr1_ms_total = 0.0
        ocr2_ms_total = 0.0

        for detection in detections:
            bbox_raw = detection.bounding_box
            if bbox_raw.x2 <= bbox_raw.x1 or bbox_raw.y2 <= bbox_raw.y1:
                continue

            margin = int(settings.PARKING_OCR_CROP_MARGIN)
            x1 = max(int(bbox_raw.x1) - margin, 0)
            y1 = max(int(bbox_raw.y1) - margin, 0)
            x2 = min(int(bbox_raw.x2) + margin, img_bgr.shape[1])
            y2 = min(int(bbox_raw.y2) + margin, img_bgr.shape[0])

            if x2 <= x1 or y2 <= y1:
                continue

            cropped_bgr = img_bgr[y1:y2, x1:x2]
            if cropped_bgr.size == 0:
                continue

            # Model 1: CCT-xs-v2 (RGB 3 channels)
            t_ocr1 = time.perf_counter()
            cropped_rgb = cv2.cvtColor(cropped_bgr, cv2.COLOR_BGR2RGB)
            pred_cct = self._ocr_cct.run_one(cropped_rgb, return_confidence=True)
            ocr1_ms_total += (time.perf_counter() - t_ocr1) * 1000.0
            cct_text = pred_cct.plate.strip()
            cct_probs_arr = (
                pred_cct.char_probs[: len(cct_text)]
                if pred_cct.char_probs is not None
                else np.array([])
            )
            cct_char_confs = [float(p) * 100.0 for p in cct_probs_arr]
            cct_min_conf = (
                float(np.min(cct_probs_arr)) * 100.0 if len(cct_probs_arr) > 0 else 0.0
            )
            cct_avg_conf = (
                float(np.mean(cct_probs_arr)) * 100.0 if len(cct_probs_arr) > 0 else 0.0
            )
            cct_norm = self.normalize_plate(cct_text)

            # Adaptive Ensemble Evaluation (H4c):
            # Run Model 2 (Mobile-ViT-v2) ONLY when Model 1 (CCT-xs-v2) has
            # min_char_confidence < T_high, leading province digit confidence < 99.2,
            # or fails the Vietnamese car plate format check.
            from apps.parking.data.vn_plate_rules import is_valid_vietnamese_car_plate

            adaptive_enabled = bool(settings.PARKING_OCR_ADAPTIVE_ENSEMBLE)
            adaptive_threshold = float(settings.PARKING_OCR_ADAPTIVE_THRESHOLD)
            leading_threshold = float(settings.PARKING_OCR_LEADING_CHAR_THRESHOLD)
            adaptive_avg_threshold = float(settings.PARKING_OCR_ADAPTIVE_AVG_THRESHOLD)
            leading_char_ok = (
                bool(cct_char_confs) and cct_char_confs[0] >= leading_threshold
            )
            is_cct_high_conf = (
                cct_min_conf >= adaptive_threshold
                and leading_char_ok
                and cct_avg_conf >= adaptive_avg_threshold
                and is_valid_vietnamese_car_plate(cct_norm)
            )

            if adaptive_enabled and is_cct_high_conf:
                mv2_text = ""
                mv2_norm = ""
                mv2_min_conf = 0.0
                mv2_avg_conf = 0.0
                mv2_char_confs = None
                is_agreed = True
                chosen_text = cct_text
                chosen_norm = cct_norm
                chosen_conf = cct_avg_conf
                chosen_min_conf = cct_min_conf
                chosen_char_confs = cct_char_confs
            else:
                # Model 2: Mobile-ViT-v2 (Grayscale 1 channel)
                t_ocr2 = time.perf_counter()
                cropped_gray = cv2.cvtColor(cropped_bgr, cv2.COLOR_BGR2GRAY)
                pred_mv2 = self._ocr_mv2.run_one(cropped_gray, return_confidence=True)
                ocr2_ms_total += (time.perf_counter() - t_ocr2) * 1000.0
                mv2_text = pred_mv2.plate.strip()
                mv2_probs_arr = (
                    pred_mv2.char_probs[: len(mv2_text)]
                    if pred_mv2.char_probs is not None
                    else np.array([])
                )
                mv2_char_confs = [float(p) * 100.0 for p in mv2_probs_arr]
                mv2_min_conf = (
                    float(np.min(mv2_probs_arr)) * 100.0
                    if len(mv2_probs_arr) > 0
                    else 0.0
                )
                mv2_avg_conf = (
                    float(np.mean(mv2_probs_arr)) * 100.0
                    if len(mv2_probs_arr) > 0
                    else 0.0
                )
                mv2_norm = self.normalize_plate(mv2_text)

                # Agreement check between CCT and MV2
                is_agreed = bool(cct_norm and mv2_norm and cct_norm == mv2_norm)
                if not is_agreed:
                    model_agreement_overall = False

                # Candidate selection logic
                if is_agreed:
                    chosen_text = cct_text
                    chosen_norm = cct_norm
                    chosen_conf = max(cct_avg_conf, mv2_avg_conf)
                    chosen_min_conf = min(cct_min_conf, mv2_min_conf)
                    chosen_char_confs = cct_char_confs
                else:
                    if cct_avg_conf >= mv2_avg_conf:
                        chosen_text = cct_text
                        chosen_norm = cct_norm
                        chosen_conf = cct_avg_conf
                        chosen_min_conf = cct_min_conf
                        chosen_char_confs = cct_char_confs
                    else:
                        chosen_text = mv2_text
                        chosen_norm = mv2_norm
                        chosen_conf = mv2_avg_conf
                        chosen_min_conf = mv2_min_conf
                        chosen_char_confs = mv2_char_confs

            if not chosen_text:
                continue

            if not cct_primary_plate:
                cct_primary_plate = cct_norm
                mv2_primary_plate = mv2_norm
                cct_primary_min_conf = cct_min_conf
                mv2_primary_min_conf = mv2_min_conf

            raw_texts.append(chosen_text)
            candidates.append(
                PlateCandidate(
                    plate_text=chosen_text,
                    plate_normalized=chosen_norm,
                    confidence=round(chosen_conf, 2),
                    char_confidences=chosen_char_confs,
                    min_char_confidence=round(chosen_min_conf, 2),
                    bounding_box=BoundingBox(x1=x1, y1=y1, x2=x2, y2=y2),
                )
            )

        candidates.sort(key=lambda c: c.confidence, reverse=True)
        best_candidate = candidates[0] if candidates else None
        latency_ms = (time.perf_counter() - start_time) * 1000.0

        return PlateScanResult(
            candidates=candidates,
            best_candidate=best_candidate,
            engine_name="fast_alpr",
            raw_text="; ".join(raw_texts),
            latency_ms=round(latency_ms, 2),
            model_agreement=model_agreement_overall,
            used_detection_fallback=used_fallback,
            cct_plate=cct_primary_plate,
            mv2_plate=mv2_primary_plate,
            cct_min_conf=round(cct_primary_min_conf, 2),
            mv2_min_conf=round(mv2_primary_min_conf, 2),
            detect_ms=round(detect_ms, 2),
            ocr1_ms=round(ocr1_ms_total, 2),
            ocr2_ms=round(ocr2_ms_total, 2),
        )


class DummyPlateRecognizer(PlateRecognizer):
    """
    Test double cho Unit Test & Integration Test.
    Hỗ trợ cấu hình kết quả xác định để kiểm thử mọi kịch bản nghiệp vụ:
    - Biển số thành công (happy path, AUTO)
    - Biển số danh sách đen (blacklist)
    - Không nhận diện được biển số (empty candidates -> 422)
    - Độ tin cậy thấp (< 85.00 -> review_status='NEEDS_REVIEW')
    - Fallback detection retry -> review_status='NEEDS_REVIEW'
    """

    def __init__(
        self,
        default_plate: str = "51K-992.14",
        default_confidence: float = 95.50,
        preset_candidates: list[PlateCandidate] | None = None,
        preset_result: PlateScanResult | None = None,
        model_agreement: bool = True,
        used_detection_fallback: bool = False,
    ) -> None:
        self.default_plate = default_plate
        self.default_confidence = default_confidence
        self.preset_candidates = preset_candidates
        self.preset_result = preset_result
        self.model_agreement = model_agreement
        self.used_detection_fallback = used_detection_fallback

    def set_result(self, result: PlateScanResult | None) -> None:
        self.preset_result = result

    def set_candidates(self, candidates: list[PlateCandidate] | None) -> None:
        self.preset_candidates = candidates

    def recognize(self, image_data: bytes | Image.Image) -> PlateScanResult:
        if self.preset_result is not None:
            return self.preset_result

        if self.preset_candidates is not None:
            best = self.preset_candidates[0] if self.preset_candidates else None
            review_status = (
                "AUTO"
                if (best and best.confidence >= 85.0 and self.model_agreement)
                else "NEEDS_REVIEW"
            )
            review_reasons = [] if review_status == "AUTO" else ["LOW_CHAR_CONFIDENCE"]
            return PlateScanResult(
                candidates=self.preset_candidates,
                best_candidate=best,
                engine_name="dummy",
                raw_text="; ".join(c.plate_text for c in self.preset_candidates),
                latency_ms=1.0,
                model_agreement=self.model_agreement,
                used_detection_fallback=self.used_detection_fallback,
                review_status=review_status,
                review_reasons=review_reasons,
            )

        if not self.default_plate:
            return PlateScanResult(
                candidates=[],
                best_candidate=None,
                engine_name="dummy",
                raw_text="",
                latency_ms=1.0,
                model_agreement=self.model_agreement,
                used_detection_fallback=self.used_detection_fallback,
                review_status="NEEDS_REVIEW",
                review_reasons=["INVALID_FORMAT"],
            )

        norm = self.normalize_plate(self.default_plate)
        char_confs = [self.default_confidence] * len(norm)
        cand = PlateCandidate(
            plate_text=self.default_plate,
            plate_normalized=norm,
            confidence=self.default_confidence,
            char_confidences=char_confs,
            min_char_confidence=self.default_confidence,
            bounding_box=BoundingBox(x1=50, y1=50, x2=350, y2=150),
        )

        review_status = (
            "AUTO"
            if self.default_confidence >= 85.0 and not self.used_detection_fallback
            else "NEEDS_REVIEW"
        )
        reasons_list: list[str] = []
        if review_status == "NEEDS_REVIEW":
            if self.default_confidence < 85.0:
                reasons_list.append("LOW_CHAR_CONFIDENCE")
            if self.used_detection_fallback:
                reasons_list.append("NO_DETECTION_RETRY")
            if not self.model_agreement:
                reasons_list.append("MODEL_DISAGREEMENT")

        return PlateScanResult(
            candidates=[cand],
            best_candidate=cand,
            engine_name="dummy",
            raw_text=self.default_plate,
            latency_ms=1.0,
            model_agreement=self.model_agreement,
            used_detection_fallback=self.used_detection_fallback,
            review_status=review_status,
            review_reasons=reasons_list,
        )


_GLOBAL_RECOGNIZER: PlateRecognizer | None = None
_RECOGNIZER_LOCK = threading.Lock()


def get_plate_recognizer() -> PlateRecognizer:
    """
    Factory function trả về recognizer theo cấu hình settings.PARKING_OCR_ENGINE.
    Cache singleton thread-safe để tái sử dụng ONNX model runtime.
    """
    global _GLOBAL_RECOGNIZER

    if _GLOBAL_RECOGNIZER is not None:
        if isinstance(_GLOBAL_RECOGNIZER, DummyPlateRecognizer):
            current_settings = os.environ.get("DJANGO_SETTINGS_MODULE", "")
            if current_settings != "config.settings.test":
                from django.core.exceptions import ImproperlyConfigured

                raise ImproperlyConfigured(
                    "PARKING_OCR_ENGINE='dummy' is only permitted when "
                    "DJANGO_SETTINGS_MODULE='config.settings.test'. "
                    f"Attempted with DJANGO_SETTINGS_MODULE='{current_settings}'."
                )
        return _GLOBAL_RECOGNIZER

    with _RECOGNIZER_LOCK:
        if _GLOBAL_RECOGNIZER is not None:
            return _GLOBAL_RECOGNIZER

        engine_name = settings.PARKING_OCR_ENGINE
        if engine_name == "dummy":
            current_settings = os.environ.get("DJANGO_SETTINGS_MODULE", "")
            if current_settings != "config.settings.test":
                from django.core.exceptions import ImproperlyConfigured

                raise ImproperlyConfigured(
                    "PARKING_OCR_ENGINE='dummy' is only permitted when "
                    "DJANGO_SETTINGS_MODULE='config.settings.test'. "
                    f"Attempted with DJANGO_SETTINGS_MODULE='{current_settings}'."
                )
            _GLOBAL_RECOGNIZER = DummyPlateRecognizer()
        elif engine_name in ("fast_alpr", "dual_ensemble"):
            _GLOBAL_RECOGNIZER = FastAlprPlateRecognizer()
        else:
            raise ValueError(f"Unsupported PARKING_OCR_ENGINE: {engine_name}")

        return _GLOBAL_RECOGNIZER


def set_global_recognizer(recognizer: PlateRecognizer | None) -> None:
    """Hỗ trợ test suite ghi đè engine nhận dạng biển số (thread-safe)."""
    global _GLOBAL_RECOGNIZER
    with _RECOGNIZER_LOCK:
        _GLOBAL_RECOGNIZER = recognizer


def warmup_ocr() -> bool:
    """
    Thực hiện warm-up mô hình OCR khi worker khởi động (gunicorn post_fork).
    Bỏ qua nếu đang chạy dummy engine trong test.
    """
    engine_name = settings.PARKING_OCR_ENGINE
    if engine_name == "dummy":
        return True
    recognizer = get_plate_recognizer()
    if hasattr(recognizer, "warmup"):
        return bool(recognizer.warmup())
    return True


def is_ocr_ready() -> bool:
    """Kiểm tra trạng thái sẵn sàng của mô hình OCR mà không làm lộ thông tin nội bộ."""
    recognizer = get_plate_recognizer()
    if hasattr(recognizer, "is_ready"):
        return bool(recognizer.is_ready)
    return bool(isinstance(recognizer, DummyPlateRecognizer))
