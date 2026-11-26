"""
Pure gate decision policy service for autonomous barrier control.
Follows ADR-0011 Section 2.5 Decision Table strictly (TL-69).
Side-effect free, deterministic, shared contract between backend and frontend.
"""

from decimal import Decimal
from typing import Any, NamedTuple

# ==============================================================================
# Action & Audit Action Constants (ADR-0011 Section 2.5, TL-69)
# ==============================================================================
ACTION_AUTO_CHECK_IN = "AUTO_CHECK_IN"
ACTION_AUTO_CHECK_OUT = "AUTO_CHECK_OUT"
ACTION_HOLD = "HOLD"

AUDIT_GATE_AUTO_CHECK_IN = "GATE_AUTO_CHECK_IN"
AUDIT_GATE_AUTO_CHECK_OUT = "GATE_AUTO_CHECK_OUT"
AUDIT_GATE_AUTO_NEEDS_STAFF = "GATE_AUTO_NEEDS_STAFF"
AUDIT_GATE_AUTO_PAYMENT_REQUIRED = "GATE_AUTO_PAYMENT_REQUIRED"

# ==============================================================================
# Reason Code Constants (ADR-0011 Section 2.5, TL-69)
# ==============================================================================
REASON_GATE_INACTIVE = "GATE_INACTIVE"
REASON_AUTO_SCAN_DISABLED = "AUTO_SCAN_DISABLED"
REASON_PLATE_UNSTABLE = "PLATE_UNSTABLE"
REASON_NEEDS_REVIEW = "NEEDS_REVIEW"
REASON_LOW_CONFIDENCE = "LOW_CONFIDENCE"
REASON_BLACKLISTED = "BLACKLISTED"
REASON_OPEN_SESSION_ALREADY_EXISTS = "OPEN_SESSION_ALREADY_EXISTS"
REASON_UNREGISTERED_VEHICLE = "UNREGISTERED_VEHICLE"
REASON_NO_AVAILABLE_SLOT = "NO_AVAILABLE_SLOT"
REASON_VALID_REGISTERED = "VALID_REGISTERED"
REASON_NO_OPEN_SESSION = "NO_OPEN_SESSION"
REASON_FEE_PAYMENT_REQUIRED = "FEE_PAYMENT_REQUIRED"
REASON_VALID_FEE_ZERO = "VALID_FEE_ZERO"
REASON_VALID_WALLET_PAID = "VALID_WALLET_PAID"
REASON_WALLET_INSUFFICIENT = "WALLET_INSUFFICIENT"
REASON_EXECUTION_FAILED = "EXECUTION_FAILED"


class DecisionResult(NamedTuple):
    """
    Structured outcome of the gate auto-apply policy evaluation.
    Can be unpacked as (action, audit_action, reason_code) or accessed by attribute.
    """

    action: str
    audit_action: str | None
    reason_code: str

    @property
    def is_approved(self) -> bool:
        """True if the barrier should open automatically (check-in or check-out)."""
        return self.action in (ACTION_AUTO_CHECK_IN, ACTION_AUTO_CHECK_OUT)

    @property
    def needs_staff(self) -> bool:
        """True if manual staff intervention is required."""
        return self.audit_action == AUDIT_GATE_AUTO_NEEDS_STAFF

    @property
    def payment_required(self) -> bool:
        """True if exit requires payment collection prior to barrier release."""
        return self.audit_action == AUDIT_GATE_AUTO_PAYMENT_REQUIRED


def decide_gate_action(
    direction: str,
    gate_active: bool,
    is_auto_scan: bool,
    review_status: str,
    confidence: float | None,
    confidence_threshold: float = 90.0,
    is_plate_stable: bool = True,
    vehicle_match: dict[str, Any] | None = None,
    open_session: dict[str, Any] | None = None,
    available_slot: dict[str, Any] | None = None,
    fee_preview: Decimal | float | None = None,
    customer_has_wallet: bool = False,
    wallet_balance: Decimal | float | str | None = None,
    wallet_status: str = "ACTIVE",
) -> DecisionResult:
    """
    Pure, side-effect-free decision function implementing the 12-row truth table
    from ADR-0011 Section 2.5 (including WP4 Row 11 wallet debit branching).

    Evaluates camera scanning observations against gate configuration, plate recognition
    confidence, registration status, active sessions, fee calculations, and wallet state.

    Args:
        direction: 'IN' (entry barrier) or 'OUT' (exit barrier).
        gate_active: Operational status of the gate (True = active).
        is_auto_scan: Whether automatic scanning is enabled on the gate.
        review_status: 'AUTO' or 'NEEDS_REVIEW' from plate recognizer.
        confidence: Recognized character confidence percentage (0.0 to 100.0).
        confidence_threshold: Minimum character confidence threshold (default: 90.0).
        is_plate_stable: Whether 3 of last 4 frames yielded identical normalized plate.
        vehicle_match: Match dict for registered vehicle, blacklist flag, etc.
        open_session: Active open parking session for this license plate, if any.
        available_slot: Compatible available parking slot for entry, if any.
        fee_preview: Calculated exit parking fee (Decimal, float, or None).
        customer_has_wallet: True if vehicle owner has an active wallet record.
        wallet_balance: Owner's current wallet balance, if known.
        wallet_status: Owner's wallet status ('ACTIVE', 'LOCKED', 'CLOSED').

    Returns:
        DecisionResult containing action ('AUTO_CHECK_IN' | 'AUTO_CHECK_OUT' | 'HOLD'),
        audit_action ('GATE_AUTO_CHECK_IN' | 'GATE_AUTO_CHECK_OUT' |
                      'GATE_AUTO_NEEDS_STAFF' | 'GATE_AUTO_PAYMENT_REQUIRED' | None),
        and reason_code (string identifier for technical audit logging).
    """
    # --------------------------------------------------------------------------
    # Row 1: Gate inactive or auto-scan disabled -> HOLD, no audit spam
    # --------------------------------------------------------------------------
    if not gate_active:
        return DecisionResult(
            action=ACTION_HOLD,
            audit_action=None,
            reason_code=REASON_GATE_INACTIVE,
        )
    if not is_auto_scan:
        return DecisionResult(
            action=ACTION_HOLD,
            audit_action=None,
            reason_code=REASON_AUTO_SCAN_DISABLED,
        )

    # --------------------------------------------------------------------------
    # Row 2: Unstable temporal plate voting (< 3 of 4 frames) -> HOLD, no audit
    # --------------------------------------------------------------------------
    if not is_plate_stable:
        return DecisionResult(
            action=ACTION_HOLD,
            audit_action=None,
            reason_code=REASON_PLATE_UNSTABLE,
        )

    # --------------------------------------------------------------------------
    # Row 3: OCR Review Status is not AUTO -> HOLD, alert staff
    # --------------------------------------------------------------------------
    if review_status != "AUTO":
        return DecisionResult(
            action=ACTION_HOLD,
            audit_action=AUDIT_GATE_AUTO_NEEDS_STAFF,
            reason_code=REASON_NEEDS_REVIEW,
        )

    # --------------------------------------------------------------------------
    # Row 4: Confidence below required threshold -> HOLD, transient, no audit spam
    # --------------------------------------------------------------------------
    try:
        conf = float(confidence) if confidence is not None else 0.0
        thresh = (
            float(confidence_threshold) if confidence_threshold is not None else 90.0
        )
    except TypeError, ValueError:
        conf, thresh = 0.0, 90.0

    if conf < thresh:
        return DecisionResult(
            action=ACTION_HOLD,
            audit_action=None,
            reason_code=REASON_LOW_CONFIDENCE,
        )

    # --------------------------------------------------------------------------
    # Row 5: Plate or vehicle is blacklisted -> HOLD, alert staff immediately
    # --------------------------------------------------------------------------
    is_blacklisted = False
    if vehicle_match:
        is_blacklisted = bool(
            vehicle_match.get("is_blacklisted", False)
            or vehicle_match.get("blacklisted", False)
        )
    if is_blacklisted:
        return DecisionResult(
            action=ACTION_HOLD,
            audit_action=AUDIT_GATE_AUTO_NEEDS_STAFF,
            reason_code=REASON_BLACKLISTED,
        )

    norm_dir = str(direction).strip().upper()

    # ==========================================================================
    # ENTRY BARRIER RULES (Direction: IN)
    # ==========================================================================
    if norm_dir == "IN":
        # Row 6: Wildcard Row 6 - Active session already exists for this plate
        # Disallows re-entry regardless of registered status or slot availability.
        if open_session:
            return DecisionResult(
                action=ACTION_HOLD,
                audit_action=AUDIT_GATE_AUTO_NEEDS_STAFF,
                reason_code=REASON_OPEN_SESSION_ALREADY_EXISTS,
            )

        # Row 7: Unregistered visitor vehicle -> HOLD, requires manual staff assignment
        is_registered = False
        if vehicle_match:
            if "is_registered" in vehicle_match:
                is_registered = bool(vehicle_match["is_registered"])
            elif "registered" in vehicle_match:
                is_registered = bool(vehicle_match["registered"])
            else:
                is_registered = bool(vehicle_match)

        if not is_registered:
            return DecisionResult(
                action=ACTION_HOLD,
                audit_action=AUDIT_GATE_AUTO_NEEDS_STAFF,
                reason_code=REASON_UNREGISTERED_VEHICLE,
            )

        # Row 8: Registered vehicle but no compatible parking slot available
        if not available_slot:
            return DecisionResult(
                action=ACTION_HOLD,
                audit_action=AUDIT_GATE_AUTO_NEEDS_STAFF,
                reason_code=REASON_NO_AVAILABLE_SLOT,
            )

        # Row 9: Registered vehicle with available slot -> Automated barrier open
        return DecisionResult(
            action=ACTION_AUTO_CHECK_IN,
            audit_action=AUDIT_GATE_AUTO_CHECK_IN,
            reason_code=REASON_VALID_REGISTERED,
        )

    # ==========================================================================
    # EXIT BARRIER RULES (Direction: OUT)
    # ==========================================================================
    elif norm_dir == "OUT":
        # Row 10: No active open session found for vehicle -> HOLD, needs staff investigation
        if not open_session:
            return DecisionResult(
                action=ACTION_HOLD,
                audit_action=AUDIT_GATE_AUTO_NEEDS_STAFF,
                reason_code=REASON_NO_OPEN_SESSION,
            )

        # Parse and sanitize fee preview amount
        fee_amount: Decimal
        if fee_preview is None:
            # If fee preview calculation failed or is unavailable, payment is required
            fee_amount = Decimal("1.00")
        else:
            try:
                fee_amount = Decimal(str(fee_preview))
            except Exception:
                fee_amount = Decimal("1.00")

        # Row 11: Fee preview > 0.00 -> check customer wallet before holding
        if fee_amount > Decimal("0.00"):
            if customer_has_wallet:
                bal: Decimal | None = None
                if wallet_balance is not None:
                    try:
                        bal = Decimal(str(wallet_balance))
                    except Exception:
                        bal = None
                if (
                    str(wallet_status).upper() == "ACTIVE"
                    and bal is not None
                    and bal >= fee_amount
                ):
                    return DecisionResult(
                        action=ACTION_AUTO_CHECK_OUT,
                        audit_action=AUDIT_GATE_AUTO_CHECK_OUT,
                        reason_code=REASON_VALID_WALLET_PAID,
                    )
                return DecisionResult(
                    action=ACTION_HOLD,
                    audit_action=AUDIT_GATE_AUTO_PAYMENT_REQUIRED,
                    reason_code=REASON_WALLET_INSUFFICIENT,
                )
            return DecisionResult(
                action=ACTION_HOLD,
                audit_action=AUDIT_GATE_AUTO_PAYMENT_REQUIRED,
                reason_code=REASON_FEE_PAYMENT_REQUIRED,
            )

        # Row 12: Fee preview == 0.00 (covered by valid active subscription ticket) -> Auto checkout
        if fee_amount == Decimal("0.00"):
            return DecisionResult(
                action=ACTION_AUTO_CHECK_OUT,
                audit_action=AUDIT_GATE_AUTO_CHECK_OUT,
                reason_code=REASON_VALID_FEE_ZERO,
            )

        # Negative fee fallback
        return DecisionResult(
            action=ACTION_HOLD,
            audit_action=AUDIT_GATE_AUTO_PAYMENT_REQUIRED,
            reason_code=REASON_FEE_PAYMENT_REQUIRED,
        )

    # --------------------------------------------------------------------------
    # Fallback: Unrecognized gate direction
    # --------------------------------------------------------------------------
    return DecisionResult(
        action=ACTION_HOLD,
        audit_action=None,
        reason_code=REASON_GATE_INACTIVE,
    )
