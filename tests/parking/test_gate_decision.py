"""
Unit tests for pure gate decision policy (decide_gate_action).
Verifies all 12 truth-table branches from ADR-0011 Section 2.5 and TL-69.
"""

from decimal import Decimal

import pytest

from apps.parking.services.gate_decision import (
    ACTION_AUTO_CHECK_IN,
    ACTION_AUTO_CHECK_OUT,
    ACTION_HOLD,
    AUDIT_GATE_AUTO_CHECK_IN,
    AUDIT_GATE_AUTO_CHECK_OUT,
    AUDIT_GATE_AUTO_NEEDS_STAFF,
    AUDIT_GATE_AUTO_PAYMENT_REQUIRED,
    REASON_AUTO_SCAN_DISABLED,
    REASON_BLACKLISTED,
    REASON_FEE_PAYMENT_REQUIRED,
    REASON_GATE_INACTIVE,
    REASON_LOW_CONFIDENCE,
    REASON_NEEDS_REVIEW,
    REASON_NO_AVAILABLE_SLOT,
    REASON_NO_OPEN_SESSION,
    REASON_OPEN_SESSION_ALREADY_EXISTS,
    REASON_PLATE_UNSTABLE,
    REASON_UNREGISTERED_VEHICLE,
    REASON_VALID_FEE_ZERO,
    REASON_VALID_REGISTERED,
    REASON_VALID_WALLET_PAID,
    REASON_WALLET_INSUFFICIENT,
    DecisionResult,
    decide_gate_action,
)

# Standard fixtures for table testing
MOCK_REGISTERED_VEHICLE = {
    "vehicle_id": 101,
    "license_plate": "51A-897.14",
    "is_registered": True,
    "is_blacklisted": False,
}
MOCK_UNREGISTERED_VEHICLE = {
    "vehicle_id": None,
    "license_plate": "43A-999.88",
    "is_registered": False,
    "is_blacklisted": False,
}
MOCK_BLACKLISTED_VEHICLE = {
    "vehicle_id": 102,
    "license_plate": "29X-666.77",
    "is_registered": True,
    "is_blacklisted": True,
}
MOCK_OPEN_SESSION = {
    "session_id": 5001,
    "session_code": "SES-20261108-0001",
    "license_plate": "51A-897.14",
}
MOCK_SLOT = {
    "slot_id": 12,
    "slot_code": "A-01",
}


# ==============================================================================
# Comprehensive 12-Row Truth Table Parameterized Tests (ADR-0011 Section 2.5)
# ==============================================================================
TRUTH_TABLE_CASES = [
    # Row 1a: Gate inactive -> HOLD, None, GATE_INACTIVE
    (
        "Row 1a: Gate inactive",
        "IN",
        False,
        True,
        "AUTO",
        95.0,
        90.0,
        True,
        MOCK_REGISTERED_VEHICLE,
        None,
        MOCK_SLOT,
        None,
        ACTION_HOLD,
        None,
        REASON_GATE_INACTIVE,
    ),
    # Row 1b: Auto scan disabled -> HOLD, None, AUTO_SCAN_DISABLED
    (
        "Row 1b: Auto scan disabled",
        "IN",
        True,
        False,
        "AUTO",
        95.0,
        90.0,
        True,
        MOCK_REGISTERED_VEHICLE,
        None,
        MOCK_SLOT,
        None,
        ACTION_HOLD,
        None,
        REASON_AUTO_SCAN_DISABLED,
    ),
    # Row 2: Unstable voting (< 3/4) -> HOLD, None, PLATE_UNSTABLE
    (
        "Row 2: Plate unstable",
        "IN",
        True,
        True,
        "AUTO",
        95.0,
        90.0,
        False,
        MOCK_REGISTERED_VEHICLE,
        None,
        MOCK_SLOT,
        None,
        ACTION_HOLD,
        None,
        REASON_PLATE_UNSTABLE,
    ),
    # Row 3: Review status != AUTO -> HOLD, GATE_AUTO_NEEDS_STAFF, NEEDS_REVIEW
    (
        "Row 3: Needs review status",
        "IN",
        True,
        True,
        "NEEDS_REVIEW",
        95.0,
        90.0,
        True,
        MOCK_REGISTERED_VEHICLE,
        None,
        MOCK_SLOT,
        None,
        ACTION_HOLD,
        AUDIT_GATE_AUTO_NEEDS_STAFF,
        REASON_NEEDS_REVIEW,
    ),
    # Row 4: Low confidence (< threshold) -> HOLD, None, LOW_CONFIDENCE
    (
        "Row 4: Low OCR confidence",
        "IN",
        True,
        True,
        "AUTO",
        88.5,
        90.0,
        True,
        MOCK_REGISTERED_VEHICLE,
        None,
        MOCK_SLOT,
        None,
        ACTION_HOLD,
        None,
        REASON_LOW_CONFIDENCE,
    ),
    # Row 5: Blacklisted plate -> HOLD, GATE_AUTO_NEEDS_STAFF, BLACKLISTED
    (
        "Row 5: Blacklisted vehicle",
        "IN",
        True,
        True,
        "AUTO",
        95.0,
        90.0,
        True,
        MOCK_BLACKLISTED_VEHICLE,
        None,
        MOCK_SLOT,
        None,
        ACTION_HOLD,
        AUDIT_GATE_AUTO_NEEDS_STAFF,
        REASON_BLACKLISTED,
    ),
    # Row 6: IN, Open session exists -> HOLD, GATE_AUTO_NEEDS_STAFF, OPEN_SESSION_ALREADY_EXISTS (wildcard)
    (
        "Row 6: Open session duplicate entry",
        "IN",
        True,
        True,
        "AUTO",
        95.0,
        90.0,
        True,
        MOCK_REGISTERED_VEHICLE,
        MOCK_OPEN_SESSION,
        MOCK_SLOT,
        None,
        ACTION_HOLD,
        AUDIT_GATE_AUTO_NEEDS_STAFF,
        REASON_OPEN_SESSION_ALREADY_EXISTS,
    ),
    # Row 7: IN, Unregistered vehicle -> HOLD, GATE_AUTO_NEEDS_STAFF, UNREGISTERED_VEHICLE
    (
        "Row 7: Unregistered casual vehicle",
        "IN",
        True,
        True,
        "AUTO",
        95.0,
        90.0,
        True,
        MOCK_UNREGISTERED_VEHICLE,
        None,
        MOCK_SLOT,
        None,
        ACTION_HOLD,
        AUDIT_GATE_AUTO_NEEDS_STAFF,
        REASON_UNREGISTERED_VEHICLE,
    ),
    # Row 8: IN, Registered but no slot -> HOLD, GATE_AUTO_NEEDS_STAFF, NO_AVAILABLE_SLOT
    (
        "Row 8: No parking slot available",
        "IN",
        True,
        True,
        "AUTO",
        95.0,
        90.0,
        True,
        MOCK_REGISTERED_VEHICLE,
        None,
        None,
        None,
        ACTION_HOLD,
        AUDIT_GATE_AUTO_NEEDS_STAFF,
        REASON_NO_AVAILABLE_SLOT,
    ),
    # Row 9: IN, Registered + slot -> AUTO_CHECK_IN, GATE_AUTO_CHECK_IN, VALID_REGISTERED
    (
        "Row 9: Valid auto check-in",
        "IN",
        True,
        True,
        "AUTO",
        95.0,
        90.0,
        True,
        MOCK_REGISTERED_VEHICLE,
        None,
        MOCK_SLOT,
        None,
        ACTION_AUTO_CHECK_IN,
        AUDIT_GATE_AUTO_CHECK_IN,
        REASON_VALID_REGISTERED,
    ),
    # Row 10: OUT, No open session -> HOLD, GATE_AUTO_NEEDS_STAFF, NO_OPEN_SESSION
    (
        "Row 10: Exit without open session",
        "OUT",
        True,
        True,
        "AUTO",
        95.0,
        90.0,
        True,
        MOCK_REGISTERED_VEHICLE,
        None,
        None,
        None,
        ACTION_HOLD,
        AUDIT_GATE_AUTO_NEEDS_STAFF,
        REASON_NO_OPEN_SESSION,
    ),
    # Row 11: OUT, Open session + Fee > 0 -> HOLD, GATE_AUTO_PAYMENT_REQUIRED, FEE_PAYMENT_REQUIRED
    (
        "Row 11: Exit fee payment required",
        "OUT",
        True,
        True,
        "AUTO",
        95.0,
        90.0,
        True,
        MOCK_REGISTERED_VEHICLE,
        MOCK_OPEN_SESSION,
        None,
        Decimal("10000.00"),
        ACTION_HOLD,
        AUDIT_GATE_AUTO_PAYMENT_REQUIRED,
        REASON_FEE_PAYMENT_REQUIRED,
    ),
    # Row 12: OUT, Open session + Fee == 0 -> AUTO_CHECK_OUT, GATE_AUTO_CHECK_OUT, VALID_FEE_ZERO
    (
        "Row 12: Valid auto check-out zero fee",
        "OUT",
        True,
        True,
        "AUTO",
        95.0,
        90.0,
        True,
        MOCK_REGISTERED_VEHICLE,
        MOCK_OPEN_SESSION,
        None,
        Decimal("0.00"),
        ACTION_AUTO_CHECK_OUT,
        AUDIT_GATE_AUTO_CHECK_OUT,
        REASON_VALID_FEE_ZERO,
    ),
]


@pytest.mark.parametrize(
    (
        "case_name",
        "direction",
        "gate_active",
        "is_auto_scan",
        "review_status",
        "confidence",
        "confidence_threshold",
        "is_plate_stable",
        "vehicle_match",
        "open_session",
        "available_slot",
        "fee_preview",
        "expected_action",
        "expected_audit_action",
        "expected_reason_code",
    ),
    TRUTH_TABLE_CASES,
)
def test_all_12_truth_table_rows(
    case_name,
    direction,
    gate_active,
    is_auto_scan,
    review_status,
    confidence,
    confidence_threshold,
    is_plate_stable,
    vehicle_match,
    open_session,
    available_slot,
    fee_preview,
    expected_action,
    expected_audit_action,
    expected_reason_code,
):
    """Verifies that every branch of ADR-0011 Section 2.5 returns expected outcome."""
    result = decide_gate_action(
        direction=direction,
        gate_active=gate_active,
        is_auto_scan=is_auto_scan,
        review_status=review_status,
        confidence=confidence,
        confidence_threshold=confidence_threshold,
        is_plate_stable=is_plate_stable,
        vehicle_match=vehicle_match,
        open_session=open_session,
        available_slot=available_slot,
        fee_preview=fee_preview,
    )

    assert isinstance(result, DecisionResult)
    assert result.action == expected_action, f"{case_name}: unexpected action"
    assert result.audit_action == expected_audit_action, (
        f"{case_name}: unexpected audit_action"
    )
    assert result.reason_code == expected_reason_code, (
        f"{case_name}: unexpected reason_code"
    )


# ==============================================================================
# Specific Deep-Dive Tests for Edge Cases & Wildcard Behaviors
# ==============================================================================


def test_wildcard_row_6_open_session_ignores_registration_and_slot():
    """
    ADR-0011 Row 6 Wildcard:
    When an open session already exists on entry, HOLD with OPEN_SESSION_ALREADY_EXISTS
    regardless of whether the vehicle is registered, unregistered, or has a slot.
    """
    # Unregistered vehicle with open session
    res_unreg = decide_gate_action(
        direction="IN",
        gate_active=True,
        is_auto_scan=True,
        review_status="AUTO",
        confidence=95.0,
        is_plate_stable=True,
        vehicle_match=MOCK_UNREGISTERED_VEHICLE,
        open_session=MOCK_OPEN_SESSION,
        available_slot=MOCK_SLOT,
    )
    assert res_unreg.action == ACTION_HOLD
    assert res_unreg.audit_action == AUDIT_GATE_AUTO_NEEDS_STAFF
    assert res_unreg.reason_code == REASON_OPEN_SESSION_ALREADY_EXISTS

    # Registered vehicle without available slot but with open session
    res_no_slot = decide_gate_action(
        direction="IN",
        gate_active=True,
        is_auto_scan=True,
        review_status="AUTO",
        confidence=95.0,
        is_plate_stable=True,
        vehicle_match=MOCK_REGISTERED_VEHICLE,
        open_session=MOCK_OPEN_SESSION,
        available_slot=None,
    )
    assert res_no_slot.action == ACTION_HOLD
    assert res_no_slot.reason_code == REASON_OPEN_SESSION_ALREADY_EXISTS


def test_fee_preview_boundary_values():
    """
    Verifies fee 0.00 vs fee > 0.00 with various numeric formats
    (Decimal, float, integer, None).
    """
    # Exact 0.00 Decimal -> AUTO_CHECK_OUT
    res_dec_zero = decide_gate_action(
        direction="OUT",
        gate_active=True,
        is_auto_scan=True,
        review_status="AUTO",
        confidence=92.0,
        is_plate_stable=True,
        open_session=MOCK_OPEN_SESSION,
        fee_preview=Decimal("0.00"),
    )
    assert res_dec_zero.action == ACTION_AUTO_CHECK_OUT
    assert res_dec_zero.audit_action == AUDIT_GATE_AUTO_CHECK_OUT
    assert res_dec_zero.reason_code == REASON_VALID_FEE_ZERO
    assert res_dec_zero.is_approved is True

    # Float 0.0 -> AUTO_CHECK_OUT
    res_float_zero = decide_gate_action(
        direction="OUT",
        gate_active=True,
        is_auto_scan=True,
        review_status="AUTO",
        confidence=92.0,
        is_plate_stable=True,
        open_session=MOCK_OPEN_SESSION,
        fee_preview=0.0,
    )
    assert res_float_zero.action == ACTION_AUTO_CHECK_OUT
    assert res_float_zero.reason_code == REASON_VALID_FEE_ZERO

    # Smallest positive fee -> FEE_PAYMENT_REQUIRED
    res_penny = decide_gate_action(
        direction="OUT",
        gate_active=True,
        is_auto_scan=True,
        review_status="AUTO",
        confidence=92.0,
        is_plate_stable=True,
        open_session=MOCK_OPEN_SESSION,
        fee_preview=Decimal("0.01"),
    )
    assert res_penny.action == ACTION_HOLD
    assert res_penny.audit_action == AUDIT_GATE_AUTO_PAYMENT_REQUIRED
    assert res_penny.reason_code == REASON_FEE_PAYMENT_REQUIRED
    assert res_penny.payment_required is True

    # None fee preview (uncalculated fee) -> FEE_PAYMENT_REQUIRED
    res_none_fee = decide_gate_action(
        direction="OUT",
        gate_active=True,
        is_auto_scan=True,
        review_status="AUTO",
        confidence=92.0,
        is_plate_stable=True,
        open_session=MOCK_OPEN_SESSION,
        fee_preview=None,
    )
    assert res_none_fee.action == ACTION_HOLD
    assert res_none_fee.audit_action == AUDIT_GATE_AUTO_PAYMENT_REQUIRED
    assert res_none_fee.reason_code == REASON_FEE_PAYMENT_REQUIRED


def test_confidence_threshold_exact_boundary():
    """
    Confidence strictly below threshold triggers LOW_CONFIDENCE.
    Confidence at or above threshold proceeds.
    """
    # 89.99% < 90.0% -> LOW_CONFIDENCE
    res_below = decide_gate_action(
        direction="IN",
        gate_active=True,
        is_auto_scan=True,
        review_status="AUTO",
        confidence=89.99,
        confidence_threshold=90.0,
        is_plate_stable=True,
        vehicle_match=MOCK_REGISTERED_VEHICLE,
        open_session=None,
        available_slot=MOCK_SLOT,
    )
    assert res_below.action == ACTION_HOLD
    assert res_below.audit_action is None
    assert res_below.reason_code == REASON_LOW_CONFIDENCE

    # 90.00% >= 90.0% -> VALID_REGISTERED
    res_exact = decide_gate_action(
        direction="IN",
        gate_active=True,
        is_auto_scan=True,
        review_status="AUTO",
        confidence=90.0,
        confidence_threshold=90.0,
        is_plate_stable=True,
        vehicle_match=MOCK_REGISTERED_VEHICLE,
        open_session=None,
        available_slot=MOCK_SLOT,
    )
    assert res_exact.action == ACTION_AUTO_CHECK_IN
    assert res_exact.reason_code == REASON_VALID_REGISTERED


def test_direction_normalization_and_unrecognized_direction():
    """Direction values are normalized ('in', 'In', 'IN') and invalid values handled."""
    # Lowercase 'in'
    res_lower = decide_gate_action(
        direction="in",
        gate_active=True,
        is_auto_scan=True,
        review_status="AUTO",
        confidence=95.0,
        is_plate_stable=True,
        vehicle_match=MOCK_REGISTERED_VEHICLE,
        open_session=None,
        available_slot=MOCK_SLOT,
    )
    assert res_lower.action == ACTION_AUTO_CHECK_IN

    # Unrecognized direction 'SIDEWAY'
    res_invalid = decide_gate_action(
        direction="SIDEWAY",
        gate_active=True,
        is_auto_scan=True,
        review_status="AUTO",
        confidence=95.0,
        is_plate_stable=True,
    )
    assert res_invalid.action == ACTION_HOLD
    assert res_invalid.reason_code == REASON_GATE_INACTIVE


def test_decision_result_tuple_unpacking_and_properties():
    """DecisionResult supports tuple unpacking and helper properties."""
    result = decide_gate_action(
        direction="IN",
        gate_active=True,
        is_auto_scan=True,
        review_status="AUTO",
        confidence=95.0,
        is_plate_stable=True,
        vehicle_match=MOCK_REGISTERED_VEHICLE,
        open_session=None,
        available_slot=MOCK_SLOT,
    )

    # Tuple unpacking
    action, audit_action, reason_code = result
    assert action == ACTION_AUTO_CHECK_IN
    assert audit_action == AUDIT_GATE_AUTO_CHECK_IN
    assert reason_code == REASON_VALID_REGISTERED

    # Properties
    assert result.is_approved is True
    assert result.needs_staff is False
    assert result.payment_required is False


def test_vehicle_match_alternative_keys_and_default():
    """vehicle_match supports 'registered' key and default dict presence."""
    # Key 'registered' instead of 'is_registered'
    res_alt_key = decide_gate_action(
        direction="IN",
        gate_active=True,
        is_auto_scan=True,
        review_status="AUTO",
        confidence=95.0,
        is_plate_stable=True,
        vehicle_match={"registered": True, "blacklisted": False},
        open_session=None,
        available_slot=MOCK_SLOT,
    )
    assert res_alt_key.action == ACTION_AUTO_CHECK_IN
    assert res_alt_key.reason_code == REASON_VALID_REGISTERED

    # Dict without explicit registration flag treats dict presence as registered
    res_dict_only = decide_gate_action(
        direction="IN",
        gate_active=True,
        is_auto_scan=True,
        review_status="AUTO",
        confidence=95.0,
        is_plate_stable=True,
        vehicle_match={"vehicle_id": 999},
        open_session=None,
        available_slot=MOCK_SLOT,
    )
    assert res_dict_only.action == ACTION_AUTO_CHECK_IN


def test_fee_preview_invalid_and_negative():
    """Invalid fee_preview string or negative fee defaults safely to FEE_PAYMENT_REQUIRED."""
    # Invalid string fee
    res_invalid = decide_gate_action(
        direction="OUT",
        gate_active=True,
        is_auto_scan=True,
        review_status="AUTO",
        confidence=95.0,
        is_plate_stable=True,
        open_session=MOCK_OPEN_SESSION,
        fee_preview="not_a_valid_decimal",
    )
    assert res_invalid.action == ACTION_HOLD
    assert res_invalid.audit_action == AUDIT_GATE_AUTO_PAYMENT_REQUIRED
    assert res_invalid.reason_code == REASON_FEE_PAYMENT_REQUIRED

    # Negative fee
    res_negative = decide_gate_action(
        direction="OUT",
        gate_active=True,
        is_auto_scan=True,
        review_status="AUTO",
        confidence=95.0,
        is_plate_stable=True,
        open_session=MOCK_OPEN_SESSION,
        fee_preview=Decimal("-5000.00"),
    )
    assert res_negative.action == ACTION_HOLD
    assert res_negative.audit_action == AUDIT_GATE_AUTO_PAYMENT_REQUIRED
    assert res_negative.reason_code == REASON_FEE_PAYMENT_REQUIRED


def test_decide_gate_action_confidence_none_and_invalid():
    """
    Khi confidence là None hoặc giá trị không thể ép kiểu sang float,
    decide_gate_action an toàn coi confidence = 0.0 (< 90.0),
    trả về ACTION_HOLD và REASON_LOW_CONFIDENCE mà không gây TypeError (Fix Finding 3).
    """
    # 1. confidence = None
    res_none = decide_gate_action(
        direction="IN",
        gate_active=True,
        is_auto_scan=True,
        review_status="AUTO",
        confidence=None,
    )
    assert res_none.action == ACTION_HOLD
    assert res_none.audit_action is None
    assert res_none.reason_code == REASON_LOW_CONFIDENCE

    # 2. confidence = string invalid
    res_str = decide_gate_action(
        direction="IN",
        gate_active=True,
        is_auto_scan=True,
        review_status="AUTO",
        confidence="invalid_confidence",
    )
    assert res_str.action == ACTION_HOLD
    assert res_str.audit_action is None
    assert res_str.reason_code == REASON_LOW_CONFIDENCE

    # 3. confidence_threshold = None -> defaults to 90.0 safely
    res_thresh_none = decide_gate_action(
        direction="IN",
        gate_active=True,
        is_auto_scan=True,
        review_status="AUTO",
        confidence=85.0,
        confidence_threshold=None,
    )
    assert res_thresh_none.action == ACTION_HOLD
    assert res_thresh_none.audit_action is None
    assert res_thresh_none.reason_code == REASON_LOW_CONFIDENCE


def test_row_11_wallet_decision_branches():
    """
    WP4 D6 / ADR-0011 Row 11:
    - fee > 0 & customer_has_wallet & ACTIVE & balance >= fee -> AUTO_CHECK_OUT / VALID_WALLET_PAID
    - fee > 0 & customer_has_wallet & (balance < fee or LOCKED) -> HOLD / WALLET_INSUFFICIENT
    - fee > 0 & not customer_has_wallet -> HOLD / FEE_PAYMENT_REQUIRED
    """
    # 11a: Wallet covers exact fee -> AUTO_CHECK_OUT / VALID_WALLET_PAID
    res_exact = decide_gate_action(
        direction="OUT",
        gate_active=True,
        is_auto_scan=True,
        review_status="AUTO",
        confidence=96.0,
        is_plate_stable=True,
        vehicle_match=MOCK_REGISTERED_VEHICLE,
        open_session=MOCK_OPEN_SESSION,
        fee_preview=Decimal("20000.00"),
        customer_has_wallet=True,
        wallet_balance=Decimal("20000.00"),
        wallet_status="ACTIVE",
    )
    assert res_exact.action == ACTION_AUTO_CHECK_OUT
    assert res_exact.audit_action == AUDIT_GATE_AUTO_CHECK_OUT
    assert res_exact.reason_code == REASON_VALID_WALLET_PAID
    assert res_exact.is_approved is True
    assert res_exact.payment_required is False

    # 11b: Wallet balance insufficient -> HOLD / WALLET_INSUFFICIENT
    res_short = decide_gate_action(
        direction="OUT",
        gate_active=True,
        is_auto_scan=True,
        review_status="AUTO",
        confidence=96.0,
        is_plate_stable=True,
        vehicle_match=MOCK_REGISTERED_VEHICLE,
        open_session=MOCK_OPEN_SESSION,
        fee_preview=Decimal("20000.00"),
        customer_has_wallet=True,
        wallet_balance=Decimal("19999.99"),
        wallet_status="ACTIVE",
    )
    assert res_short.action == ACTION_HOLD
    assert res_short.audit_action == AUDIT_GATE_AUTO_PAYMENT_REQUIRED
    assert res_short.reason_code == REASON_WALLET_INSUFFICIENT
    assert res_short.payment_required is True

    # 11b (locked wallet): HOLD / WALLET_INSUFFICIENT
    res_locked = decide_gate_action(
        direction="OUT",
        gate_active=True,
        is_auto_scan=True,
        review_status="AUTO",
        confidence=96.0,
        is_plate_stable=True,
        vehicle_match=MOCK_REGISTERED_VEHICLE,
        open_session=MOCK_OPEN_SESSION,
        fee_preview=Decimal("20000.00"),
        customer_has_wallet=True,
        wallet_balance=Decimal("500000.00"),
        wallet_status="LOCKED",
    )
    assert res_locked.action == ACTION_HOLD
    assert res_locked.audit_action == AUDIT_GATE_AUTO_PAYMENT_REQUIRED
    assert res_locked.reason_code == REASON_WALLET_INSUFFICIENT

    # 11c: No wallet -> HOLD / FEE_PAYMENT_REQUIRED
    res_no_wallet = decide_gate_action(
        direction="OUT",
        gate_active=True,
        is_auto_scan=True,
        review_status="AUTO",
        confidence=96.0,
        is_plate_stable=True,
        vehicle_match=MOCK_REGISTERED_VEHICLE,
        open_session=MOCK_OPEN_SESSION,
        fee_preview=Decimal("20000.00"),
        customer_has_wallet=False,
        wallet_balance=None,
    )
    assert res_no_wallet.action == ACTION_HOLD
    assert res_no_wallet.audit_action == AUDIT_GATE_AUTO_PAYMENT_REQUIRED
    assert res_no_wallet.reason_code == REASON_FEE_PAYMENT_REQUIRED
