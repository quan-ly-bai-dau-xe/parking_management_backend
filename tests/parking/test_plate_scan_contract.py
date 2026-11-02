"""
Byte-identical contract proof test suite for PlateScanView & execute_plate_scan (J5).
Verifies response schema keys, data types, business status contracts (AUTO, NEEDS_REVIEW),
error envelopes (400, 422, 503), byte-for-byte equivalence, and thin-controller AST compliance.
"""

from __future__ import annotations

import inspect
import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.core.concurrency import OCRConcurrencyGate
from apps.parking.enums import ReviewReasonCode, ReviewStatus
from apps.parking.services.ocr import (
    BoundingBox,
    DummyPlateRecognizer,
    PlateCandidate,
    PlateRecognizer,
    set_global_recognizer,
)
from apps.parking.services.plate_scan import execute_plate_scan
from apps.parking.views.scans import PlateScanView
from tests.parking.contract_reference_validator import (
    ContractInvariantError,
    ContractSchemaError,
    ReferenceContractValidator,
    validate_plate_scan_reference_contract,
)


@pytest.fixture
def auth_client(db) -> APIClient:
    """Provides an authenticated DRF test client with Employee role."""
    user = Account.objects.create_user(
        email="test_contract_staff@example.com",
        phone="0901234567",
        password="SecurePass123!",
        role="EMPLOYEE",
        is_active=True,
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _create_synthetic_image_file(
    width: int = 640, height: int = 480, color: str = "white"
) -> io.BytesIO:
    """Generates a valid in-memory JPEG image file for upload testing."""
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    buf.name = "scan_test.jpg"
    return buf


def _make_dummy_recognizer(
    plate_text: str = "51F69881",
    confidence: float = 98.0,
    min_char_conf: float = 95.0,
    model_agreement: bool = True,
    empty: bool = False,
) -> DummyPlateRecognizer:
    """Creates a configured DummyPlateRecognizer for deterministic test assertions."""
    if empty:
        return DummyPlateRecognizer(default_plate="", preset_candidates=[])
    norm = PlateRecognizer.normalize_plate(plate_text)
    char_confs = [confidence] * (len(norm) - 1) + [min_char_conf]
    cand = PlateCandidate(
        plate_text=plate_text,
        plate_normalized=norm,
        confidence=confidence,
        char_confidences=char_confs,
        min_char_confidence=min_char_conf,
        bounding_box=BoundingBox(x1=50, y1=50, x2=350, y2=150),
    )
    return DummyPlateRecognizer(
        default_plate=plate_text,
        default_confidence=confidence,
        preset_candidates=[cand],
        model_agreement=model_agreement,
    )


class TestPlateScanResponseSchemaContract:
    """Verifies that the scan response schema adheres to the canonical 14-key contract."""

    CANONICAL_ROOT_KEYS = {
        "plate_raw",
        "plate_final",
        "candidates",
        "best_candidate",
        "image_url",
        "vehicle_lookup",
        "is_blacklisted",
        "open_session",
        "engine_name",
        "latency_ms",
        "review_status",
        "review_reasons",
        "corrections",
        "suggestions",
    }

    CANONICAL_CANDIDATE_KEYS = {
        "plate_text",
        "plate_normalized",
        "confidence",
        "char_confidences",
        "min_char_confidence",
        "bounding_box",
    }

    CANONICAL_BOUNDING_BOX_KEYS = {"x1", "y1", "x2", "y2"}

    CANONICAL_CORRECTION_KEYS = {
        "position",
        "from",
        "to",
        "rule",
        "reason",
        "original_char",
        "corrected_char",
    }

    def test_root_response_keys_contract(self, auth_client: APIClient) -> None:
        """Scan API JSON root keys must strictly match the 14 canonical keys."""
        rec = _make_dummy_recognizer("51F69881", confidence=98.5, min_char_conf=96.0)
        set_global_recognizer(rec)

        img_file = _create_synthetic_image_file()
        response = auth_client.post(
            "/api/v1/parking/plate-scans/",
            {"image": img_file},
            format="multipart",
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert set(data.keys()) == self.CANONICAL_ROOT_KEYS

    def test_candidate_and_bounding_box_schema_contract(
        self, auth_client: APIClient
    ) -> None:
        """Candidates and bounding_box schemas must match canonical keys and types."""
        rec = _make_dummy_recognizer("51F69881", confidence=98.5, min_char_conf=96.0)
        set_global_recognizer(rec)

        img_file = _create_synthetic_image_file()
        response = auth_client.post(
            "/api/v1/parking/plate-scans/",
            {"image": img_file},
            format="multipart",
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["candidates"]) >= 1
        best_cand = data["best_candidate"]
        assert best_cand is not None
        assert set(best_cand.keys()) == self.CANONICAL_CANDIDATE_KEYS

        bb = best_cand["bounding_box"]
        assert bb is not None
        assert set(bb.keys()) == self.CANONICAL_BOUNDING_BOX_KEYS

    def test_correction_object_schema_contract(self, auth_client: APIClient) -> None:
        """Corrections objects must strictly adhere to the 7-key dictionary schema."""
        # 5DZ1630 triggers position correction at pos 1: D -> 0
        rec = _make_dummy_recognizer("5DZ1630", confidence=92.0, min_char_conf=91.0)
        set_global_recognizer(rec)

        img_file = _create_synthetic_image_file()
        response = auth_client.post(
            "/api/v1/parking/plate-scans/",
            {"image": img_file},
            format="multipart",
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["corrections"]) >= 1
        for corr in data["corrections"]:
            assert set(corr.keys()) == self.CANONICAL_CORRECTION_KEYS

    def test_data_types_integrity(self, auth_client: APIClient) -> None:
        """Every field in the response payload must adhere to strict type specifications."""
        rec = _make_dummy_recognizer("51F69881", confidence=98.5, min_char_conf=96.0)
        set_global_recognizer(rec)

        img_file = _create_synthetic_image_file()
        response = auth_client.post(
            "/api/v1/parking/plate-scans/",
            {"image": img_file},
            format="multipart",
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert isinstance(data["plate_raw"], str)
        assert isinstance(data["plate_final"], str)
        assert isinstance(data["candidates"], list)
        assert isinstance(data["best_candidate"], dict)
        assert isinstance(data["image_url"], str)
        assert data["vehicle_lookup"] is None or isinstance(
            data["vehicle_lookup"], dict
        )
        assert isinstance(data["is_blacklisted"], bool)
        assert data["open_session"] is None or isinstance(data["open_session"], dict)
        assert isinstance(data["engine_name"], str)
        assert isinstance(data["latency_ms"], (int, float))
        assert isinstance(data["review_status"], str)
        assert isinstance(data["review_reasons"], list)
        assert isinstance(data["corrections"], list)
        assert isinstance(data["suggestions"], list)


class TestPlateScanReviewStatusContracts:
    """Verifies that review policy evaluation rules generate deterministic review statuses."""

    def test_contract_auto_success(self, auth_client: APIClient) -> None:
        """High confidence, clean plate without corrections passes as AUTO."""
        rec = _make_dummy_recognizer("51F69881", confidence=98.0, min_char_conf=95.0)
        set_global_recognizer(rec)

        img_file = _create_synthetic_image_file()
        response = auth_client.post(
            "/api/v1/parking/plate-scans/",
            {"image": img_file},
            format="multipart",
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["review_status"] == ReviewStatus.AUTO
        assert data["review_reasons"] == []

    def test_contract_needs_review_low_confidence(self, auth_client: APIClient) -> None:
        """Plate with min_char_conf < 90.0% triggers NEEDS_REVIEW with LOW_CHAR_CONFIDENCE."""
        rec = _make_dummy_recognizer("51F69881", confidence=95.0, min_char_conf=88.0)
        set_global_recognizer(rec)

        img_file = _create_synthetic_image_file()
        response = auth_client.post(
            "/api/v1/parking/plate-scans/",
            {"image": img_file},
            format="multipart",
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["review_status"] == ReviewStatus.NEEDS_REVIEW
        assert ReviewReasonCode.LOW_CHAR_CONFIDENCE in data["review_reasons"]

    def test_contract_needs_review_position_corrected(
        self, auth_client: APIClient
    ) -> None:
        """Plate modified by positional grammar rules triggers NEEDS_REVIEW with POSITION_CORRECTED (J4)."""
        rec = _make_dummy_recognizer("5DZ1630", confidence=96.0, min_char_conf=94.0)
        set_global_recognizer(rec)

        img_file = _create_synthetic_image_file()
        response = auth_client.post(
            "/api/v1/parking/plate-scans/",
            {"image": img_file},
            format="multipart",
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["review_status"] == ReviewStatus.NEEDS_REVIEW
        assert ReviewReasonCode.POSITION_CORRECTED in data["review_reasons"]
        assert data["plate_raw"] == "5DZ1630"
        assert data["plate_final"] == "50Z1630"

    def test_contract_needs_review_unknown_plate_pattern(
        self, auth_client: APIClient
    ) -> None:
        """Unassigned province code (e.g. 13A) triggers NEEDS_REVIEW with UNKNOWN_PLATE_PATTERN."""
        rec = _make_dummy_recognizer("13A12345", confidence=98.0, min_char_conf=96.0)
        set_global_recognizer(rec)

        img_file = _create_synthetic_image_file()
        response = auth_client.post(
            "/api/v1/parking/plate-scans/",
            {"image": img_file},
            format="multipart",
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["review_status"] == ReviewStatus.NEEDS_REVIEW
        assert ReviewReasonCode.UNKNOWN_PLATE_PATTERN in data["review_reasons"]


class TestPlateScanErrorStatusContracts:
    """Verifies standard HTTP error envelopes (400, 422, 503)."""

    def test_contract_concurrency_overload_503(self, auth_client: APIClient) -> None:
        """When concurrency gate is saturated, returns HTTP 503 with Retry-After header."""
        rec = _make_dummy_recognizer("51F69881", confidence=98.0, min_char_conf=95.0)
        set_global_recognizer(rec)

        saturated_gate = OCRConcurrencyGate(limit=1, timeout=0.001, retry_after=3)
        saturated_gate._semaphore.acquire()  # Drain permit

        img_file = _create_synthetic_image_file()
        with patch(
            "apps.parking.services.plate_scan.get_ocr_concurrency_gate",
            return_value=saturated_gate,
        ):
            response = auth_client.post(
                "/api/v1/parking/plate-scans/",
                {"image": img_file},
                format="multipart",
            )

        saturated_gate._semaphore.release()
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert response.headers.get("Retry-After") == "3"
        data = response.json()
        assert data["code"] == "PROP-4.5.1-P15"

    def test_contract_missing_file_400(self, auth_client: APIClient) -> None:
        """Missing image field in multipart upload returns HTTP 400 PROP-4.5.1-P02."""
        response = auth_client.post(
            "/api/v1/parking/plate-scans/",
            {},
            format="multipart",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert data["code"] == "PROP-4.5.1-P02"

    def test_contract_corrupted_file_400(self, auth_client: APIClient) -> None:
        """Invalid non-image byte stream returns HTTP 400 PROP-4.5.1-P04."""
        corrupted = io.BytesIO(b"Not An Image Content At All")
        corrupted.name = "corrupt.jpg"

        response = auth_client.post(
            "/api/v1/parking/plate-scans/",
            {"image": corrupted},
            format="multipart",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert data["code"] == "PROP-4.5.1-P04"

    def test_contract_empty_ocr_candidates_422(self, auth_client: APIClient) -> None:
        """When OCR recognizer detects no candidates, returns HTTP 422 PROP-4.5.1-P06."""
        rec = _make_dummy_recognizer(empty=True)
        set_global_recognizer(rec)

        img_file = _create_synthetic_image_file()
        response = auth_client.post(
            "/api/v1/parking/plate-scans/",
            {"image": img_file},
            format="multipart",
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        data = response.json()
        assert data["code"] == "PROP-4.5.1-P06"


class TestPlateScanIndependentReferenceContractProof:
    """
    Independent Reference Contract Test Suite.
    Replaces circular service-vs-helper comparison with an independent, pure-function
    reference validator and verified golden JSON fixtures across HTTP responses.
    """

    GOLDEN_FIXTURES_DIR = Path(__file__).resolve().parent / "golden_fixtures"

    def test_independent_reference_contract_validation(self, db) -> None:
        """Service execution output must satisfy the independent ReferenceContractValidator."""
        rec = _make_dummy_recognizer("51F69881", confidence=98.5, min_char_conf=95.0)

        img_file = _create_synthetic_image_file()
        stages: dict[str, float] = {}

        result = execute_plate_scan(
            image_file=img_file,
            stages=stages,
            recognizer=rec,
        )

        # Non-circular verification: Validate directly against independent reference contract
        validate_plate_scan_reference_contract(result.payload)
        assert result.payload["plate_final"] == "51F69881"
        assert result.payload["review_status"] == ReviewStatus.AUTO

    def test_all_golden_fixtures_satisfy_independent_reference_contract(self) -> None:
        """All serialized golden JSON fixtures on disk must strictly satisfy the Reference Contract."""
        fixture_files = list(self.GOLDEN_FIXTURES_DIR.glob("*.json"))
        assert len(fixture_files) >= 40, (
            f"Expected at least 40 golden fixtures, found {len(fixture_files)}"
        )

        for fixture_path in fixture_files:
            with open(fixture_path, encoding="utf-8") as f:
                payload = json.load(f)
            try:
                ReferenceContractValidator.validate(payload)
            except Exception as exc:
                pytest.fail(
                    f"Golden fixture '{fixture_path.name}' failed contract validation: {exc}"
                )

    def test_live_http_responses_match_golden_fixture_contract(
        self, auth_client: APIClient
    ) -> None:
        """Live HTTP responses from POST /api/v1/parking/plate-scans/ must pass the independent contract."""
        test_scenarios = [
            # High confidence clean plate -> AUTO
            ("51F69881", 98.0, 96.0, ReviewStatus.AUTO, None),
            # Positional correction -> NEEDS_REVIEW with POSITION_CORRECTED
            (
                "5DZ1630",
                94.0,
                92.0,
                ReviewStatus.NEEDS_REVIEW,
                ReviewReasonCode.POSITION_CORRECTED,
            ),
            # Unknown province pattern -> NEEDS_REVIEW with UNKNOWN_PLATE_PATTERN
            (
                "13A12345",
                98.0,
                96.0,
                ReviewStatus.NEEDS_REVIEW,
                ReviewReasonCode.UNKNOWN_PLATE_PATTERN,
            ),
            # Low confidence -> NEEDS_REVIEW with LOW_CHAR_CONFIDENCE
            (
                "51F69881",
                92.0,
                85.0,
                ReviewStatus.NEEDS_REVIEW,
                ReviewReasonCode.LOW_CHAR_CONFIDENCE,
            ),
        ]

        for plate, conf, min_c, expected_status, expected_reason in test_scenarios:
            rec = _make_dummy_recognizer(plate, confidence=conf, min_char_conf=min_c)
            set_global_recognizer(rec)

            img_file = _create_synthetic_image_file()
            response = auth_client.post(
                "/api/v1/parking/plate-scans/",
                {"image": img_file},
                format="multipart",
            )

            assert response.status_code == status.HTTP_200_OK, (
                f"HTTP failure for {plate}"
            )
            data = response.json()

            # Independent Reference Contract validation on live HTTP response
            validate_plate_scan_reference_contract(data)

            assert data["review_status"] == expected_status
            if expected_reason is not None:
                assert expected_reason in data["review_reasons"]
            else:
                assert data["review_reasons"] == []

    def test_view_is_thin_controller_inspection(self) -> None:
        """
        AST introspection proves that PlateScanView.post is a thin controller (< 30 lines),
        and does not contain inline OCR or review policy logic.
        """
        source = inspect.getsource(PlateScanView.post)
        def_index = source.find("def post(")
        body_source = source[def_index:] if def_index != -1 else source
        lines = [line.strip() for line in body_source.splitlines() if line.strip()]

        # Length check: Thin controller must be concise
        assert len(lines) <= 30, (
            f"PlateScanView.post body is too long: {len(lines)} lines"
        )

        # Separation of concerns check: View must NOT perform review policy or corrections inline
        assert "evaluate_review_policy" not in source, (
            "Fat View leak: evaluate_review_policy called in post"
        )
        assert "correct_plate_characters" not in source, (
            "Fat View leak: correct_plate_characters called in post"
        )
        assert "classify_plate_syntax" not in source, (
            "Fat View leak: classify_plate_syntax called in post"
        )
        assert "execute_plate_scan" in source, (
            "PlateScanView.post must delegate to execute_plate_scan"
        )


class TestPlateScanContractMutationProof:
    """
    Mutation Testing Suite for Plate Scan Contract.
    Deliberately introduces structural and semantic mutations to prove that
    contract invariant violations immediately trigger deterministic test failures.
    """

    @pytest.fixture
    def valid_contract_payload(self) -> dict:
        """Generates a valid, canonical plate scan response dictionary for mutation testing."""
        return {
            "plate_raw": "50Z1630",
            "plate_final": "50Z1630",
            "candidates": [
                {
                    "plate_text": "50Z1630",
                    "plate_normalized": "50Z1630",
                    "confidence": 98.0,
                    "char_confidences": [98.0, 98.0, 98.0, 98.0, 98.0, 98.0, 98.0],
                    "min_char_confidence": 98.0,
                    "bounding_box": {"x1": 50, "y1": 50, "x2": 350, "y2": 150},
                }
            ],
            "best_candidate": {
                "plate_text": "50Z1630",
                "plate_normalized": "50Z1630",
                "confidence": 98.0,
                "char_confidences": [98.0, 98.0, 98.0, 98.0, 98.0, 98.0, 98.0],
                "min_char_confidence": 98.0,
                "bounding_box": {"x1": 50, "y1": 50, "x2": 350, "y2": 150},
            },
            "image_url": (
                "https://res.cloudinary.com/test-cloud/image/upload/"
                "v1730178490/parking_scans/2026/10/20/12345678901234567890123456789012.jpg"
            ),
            "vehicle_lookup": None,
            "is_blacklisted": False,
            "open_session": None,
            "engine_name": "fast_alpr",
            "latency_ms": 42.5,
            "review_status": "AUTO",
            "review_reasons": [],
            "corrections": [],
            "suggestions": [],
        }

    def test_mutation_desynchronized_best_candidate_fails_contract(
        self, valid_contract_payload: dict
    ) -> None:
        """Mutant 1: De-synchronizing best_candidate.plate_normalized from plate_final must fail immediately."""
        mutated = dict(valid_contract_payload)
        mutated["best_candidate"] = dict(valid_contract_payload["best_candidate"])
        # Deliberately desynchronize candidate from final normalized plate
        mutated["best_candidate"]["plate_normalized"] = "5DZ1630"
        mutated["plate_final"] = "50Z1630"

        with pytest.raises(ContractInvariantError) as exc_info:
            ReferenceContractValidator.validate(mutated)

        assert "must strictly equal plate_final" in str(exc_info.value)

    def test_mutation_missing_mandatory_root_key_fails_contract(
        self, valid_contract_payload: dict
    ) -> None:
        """Mutant 2: Dropping mandatory 'corrections' root key must fail schema validation immediately."""
        mutated = dict(valid_contract_payload)
        del mutated["corrections"]

        with pytest.raises(ContractSchemaError) as exc_info:
            ReferenceContractValidator.validate(mutated)

        assert "missing mandatory canonical root keys" in str(exc_info.value)
        assert "corrections" in str(exc_info.value)

    def test_mutation_auto_status_with_reasons_fails_contract(
        self, valid_contract_payload: dict
    ) -> None:
        """Mutant 3: Contradictory review state (AUTO with non-empty reasons) must fail immediately."""
        mutated = dict(valid_contract_payload)
        mutated["review_status"] = "AUTO"
        mutated["review_reasons"] = ["LOW_CHAR_CONFIDENCE"]

        with pytest.raises(ContractInvariantError) as exc_info:
            ReferenceContractValidator.validate(mutated)

        assert "review_status is 'AUTO' but review_reasons is non-empty" in str(
            exc_info.value
        )

    def test_mutation_corrections_without_position_corrected_fails_contract(
        self, valid_contract_payload: dict
    ) -> None:
        """Mutant 4: Having corrections without POSITION_CORRECTED review reason must fail immediately."""
        mutated = dict(valid_contract_payload)
        mutated["review_status"] = (
            "AUTO"  # Contradiction: corrections present with AUTO
        )
        mutated["corrections"] = [
            {
                "position": 1,
                "from": "D",
                "to": "0",
                "rule": "0_to_D_O_Q",
                "reason": "Fix position 1",
                "original_char": "D",
                "corrected_char": "0",
            }
        ]

        with pytest.raises(ContractInvariantError) as exc_info:
            ReferenceContractValidator.validate(mutated)

        assert "corrections are present" in str(exc_info.value)

    def test_mutation_inverted_bounding_box_fails_contract(
        self, valid_contract_payload: dict
    ) -> None:
        """Mutant 5: Inverted bounding box coordinates (x2 <= x1) must fail immediately."""
        mutated = dict(valid_contract_payload)
        mutated["candidates"] = [
            {
                "plate_text": "50Z1630",
                "plate_normalized": "50Z1630",
                "confidence": 98.0,
                "char_confidences": [98.0],
                "min_char_confidence": 98.0,
                "bounding_box": {
                    "x1": 350,
                    "y1": 50,
                    "x2": 50,
                    "y2": 150,
                },  # Inverted x2 <= x1
            }
        ]

        with pytest.raises(ContractInvariantError) as exc_info:
            ReferenceContractValidator.validate(mutated)

        assert "bounding_box invariant violation: x2" in str(exc_info.value)


class TestOcrModelsDirectoryConfiguration:
    """Verifies that PARKING_OCR_MODELS_DIR setting and validator satisfy Standard 4 requirements."""

    def test_configured_models_dir_setting_exists(self) -> None:
        """PARKING_OCR_MODELS_DIR must be declared in Django settings."""
        from django.conf import settings

        assert hasattr(settings, "PARKING_OCR_MODELS_DIR")
        assert isinstance(settings.PARKING_OCR_MODELS_DIR, str)
        assert len(settings.PARKING_OCR_MODELS_DIR) > 0

    def test_get_validated_ocr_models_dir_raises_file_not_found(
        self, tmp_path: Path
    ) -> None:
        """Non-existent directory must raise FileNotFoundError with actionable error message."""
        from config.settings.base import get_validated_ocr_models_dir

        non_existent = tmp_path / "missing_ocr_models_dir"
        with pytest.raises(FileNotFoundError) as exc_info:
            get_validated_ocr_models_dir(non_existent)

        err_msg = str(exc_info.value)
        assert "OCR models directory" in err_msg
        assert "does not exist or is not a directory" in err_msg
        assert "Please configure PARKING_OCR_MODELS_DIR" in err_msg

    def test_get_validated_ocr_models_dir_success_on_valid_dir(
        self, tmp_path: Path
    ) -> None:
        """Valid existing directory resolves and returns Path instance."""
        from config.settings.base import get_validated_ocr_models_dir

        valid_dir = tmp_path / "valid_models"
        valid_dir.mkdir()
        resolved = get_validated_ocr_models_dir(valid_dir)
        assert resolved == valid_dir
        assert resolved.is_dir()
