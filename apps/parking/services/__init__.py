"""
Parking services module exports.
"""

from apps.parking.services.check_in import check_in_vehicle
from apps.parking.services.check_out import check_out_vehicle
from apps.parking.services.ocr import (
    BoundingBox,
    DummyPlateRecognizer,
    FastAlprPlateRecognizer,
    PlateCandidate,
    PlateRecognizer,
    PlateScanResult,
    get_plate_recognizer,
    set_global_recognizer,
)
from apps.parking.services.session_code import generate_session_code
from apps.parking.services.tariff import calculate_parking_fee
from apps.parking.services.upload import (
    ProcessedImage,
    UploadResult,
    process_uploaded_image,
    save_processed_image,
    validate_and_save_image,
)

__all__ = [
    "BoundingBox",
    "DummyPlateRecognizer",
    "FastAlprPlateRecognizer",
    "PlateCandidate",
    "PlateRecognizer",
    "PlateScanResult",
    "ProcessedImage",
    "UploadResult",
    "calculate_parking_fee",
    "check_in_vehicle",
    "check_out_vehicle",
    "generate_session_code",
    "get_plate_recognizer",
    "process_uploaded_image",
    "save_processed_image",
    "set_global_recognizer",
    "validate_and_save_image",
]
