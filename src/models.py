from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class DeclineReason(str, Enum):
    AUTH_TIMEOUT = "AUTH_TIMEOUT"
    SOFT_LIMIT_EXCEEDED = "SOFT_LIMIT_EXCEEDED"
    INSUFFICIENT_FUNDS = "INSUFFICIENT_FUNDS"
    BANK_SERVER_ERROR = "BANK_SERVER_ERROR"
    OTP_FAILURE = "OTP_FAILURE"
    CARD_EXPIRED = "CARD_EXPIRED"
    UNKNOWN = "UNKNOWN"


RAZORPAY_ERROR_CODE_MAP: Dict[str, DeclineReason] = {
    "GATEWAY_ERROR": DeclineReason.BANK_SERVER_ERROR,
    "BAD_REQUEST_ERROR": DeclineReason.AUTH_TIMEOUT,
    "payment.authentication.failed": DeclineReason.AUTH_TIMEOUT,
    "payment.timeout": DeclineReason.AUTH_TIMEOUT,
    "payment.otp.invalid": DeclineReason.OTP_FAILURE,
    "payment.otp.timeout": DeclineReason.OTP_FAILURE,
    "payment.card.expired": DeclineReason.CARD_EXPIRED,
    "payment.limit.exceeded": DeclineReason.SOFT_LIMIT_EXCEEDED,
    "payment.insufficient_funds": DeclineReason.INSUFFICIENT_FUNDS,
    "server_error": DeclineReason.BANK_SERVER_ERROR,
}


class ChannelType(str, Enum):
    UPI_ONE_TAP = "UPI_ONE_TAP"
    MICRO_INSTALLMENT = "MICRO_INSTALLMENT"
    ALT_PAYMENT_METHOD = "ALT_PAYMENT_METHOD"
    RETRY_SMS_REMINDER = "RETRY_SMS_REMINDER"


class UrgencyLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class PaymentEvent(BaseModel):
    event_id: str
    razorpay_payment_id: str
    razorpay_order_id: Optional[str] = None
    merchant_id: str
    customer_name: str = Field(default="Customer")
    customer_email: Optional[str] = None
    customer_phone: str = Field(..., min_length=8)
    amount: float = Field(..., gt=0, description="Transaction amount in INR")
    currency: str = Field(default="INR")
    decline_reason: DeclineReason
    raw_error_code: Optional[str] = None
    raw_error_description: Optional[str] = None
    payment_method: str
    bank: Optional[str] = None
    retry_count: int = Field(default=0, ge=0, le=10)
    received_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("customer_phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        cleaned = v.strip().replace(" ", "")
        if not cleaned.startswith("+"):
            raise ValueError("Phone number must be E.164, e.g. +919812345678")
        return cleaned

    @classmethod
    def from_razorpay_webhook(cls, body: Dict[str, Any], merchant_id: str) -> "PaymentEvent":
        entity = body["payload"]["payment"]["entity"]
        error_code = entity.get("error_code") or entity.get("error_reason") or ""
        reason = RAZORPAY_ERROR_CODE_MAP.get(error_code, DeclineReason.UNKNOWN)

        notes = entity.get("notes") or {}
        return cls(
            event_id=body.get("id", f"evt_{entity['id']}"),
            razorpay_payment_id=entity["id"],
            razorpay_order_id=entity.get("order_id"),
            merchant_id=merchant_id,
            customer_name=notes.get("customer_name", "Customer"),
            customer_email=entity.get("email"),
            customer_phone=notes.get("customer_phone") or entity.get("contact") or "+910000000000",
            amount=float(entity["amount"]) / 100.0,
            currency=entity.get("currency", "INR"),
            decline_reason=reason,
            raw_error_code=error_code,
            raw_error_description=entity.get("error_description"),
            payment_method=entity.get("method", "unknown"),
            bank=entity.get("bank"),
            retry_count=int(notes.get("retry_count", 0)),
        )


class RecoveryStrategy(BaseModel):
    strategy_id: str
    event_id: str
    channel: ChannelType
    reasoning: List[str] = Field(..., min_length=1)
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    recommended_action: str
    installment_plan: Optional[List[float]] = None
    urgency_level: UrgencyLevel
    decided_by: str = Field(description="'llm_agent' or 'deterministic_fallback'")


class DynamicPayload(BaseModel):
    payload_id: str
    strategy_id: str
    razorpay_payment_link_id: str
    order_reference: Optional[str]
    amount: float
    payment_link: str
    short_link: str
    sms_message: str
    expires_at: datetime
    is_live_razorpay_link: bool

    @classmethod
    def build_expiry(cls, urgent: bool) -> datetime:
        minutes = 20 if urgent else 120
        return datetime.utcnow() + timedelta(minutes=minutes)
