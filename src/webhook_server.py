from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
import uuid
from typing import Any, Dict, Optional

import httpx
from fastapi import Body, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel

from .config import settings
from .models import DeclineReason, PaymentEvent
from .orchestrator import orchestrator
from .razorpay_client import RazorpayService
from .storage import fetch_all, fetch_metrics, init_db, insert_record, mark_recovered

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("contextpulse.webhook_server")

app = FastAPI(title="Razorpay ContextPulse", version="1.0.0")

razorpay_service = RazorpayService()


@app.on_event("startup")
async def startup() -> None:
    # Clear old database records on startup to keep only fresh additions
    init_db(clear_data=True)
    notifier_live = getattr(orchestrator, "notifier", None) and orchestrator.notifier.is_live()
    logger.info("ContextPulse started (db cleared). Razorpay live=%s | OpenAI configured=%s | Twilio live=%s",
                razorpay_service.is_live(), settings.llm_configured(), notifier_live)


@app.get("/health")
async def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "razorpay_configured": settings.razorpay_configured(),
        "webhook_secret_configured": settings.webhook_secret_configured(),
        "llm_configured": settings.llm_configured(),
        "twilio_configured": settings.twilio_configured(),
    }


def _save_event_to_db(event: PaymentEvent, result: Dict[str, Any]) -> None:
    """Extracts values safely from PaymentEvent and orchestrator result, then calls insert_record."""
    strategy = result.get("strategy")
    payload = result.get("payload")
    notify_result = result.get("notify_result", {})

    record = {
        "event_id": getattr(event, "event_id", f"evt_{uuid.uuid4().hex[:10]}"),
        "strategy_id": getattr(strategy, "strategy_id", "strat_default"),
        "payload_id": getattr(payload, "payload_id", "pay_default"),
        "order_reference": getattr(event, "order_id", ""),
        "customer_name": getattr(event, "customer_name", "Ashmitharaja"),
        "customer_phone": getattr(event, "customer_phone", ""),
        "amount": float(getattr(event, "amount", 0.0)),
        "decline_reason": str(getattr(getattr(event, "decline_reason", None), "value", getattr(event, "decline_reason", "unknown"))),
        "payment_method": getattr(event, "payment_method", "card"),
        "bank": getattr(event, "bank", "N/A"),
        "retry_count": getattr(event, "retry_count", 0),
        "channel": getattr(getattr(strategy, "channel", None), "value", result.get("channel", "sms")),
        "confidence_score": float(getattr(strategy, "confidence_score", result.get("confidence", 0.95))),
        "urgency_level": getattr(strategy, "urgency_level", "high"),
        "decided_by": getattr(strategy, "decided_by", result.get("decided_by", "Rule Engine Fallback")),
        "recommended_action": getattr(strategy, "recommended_action", "Send SMS Recovery Link"),
        "reasoning": getattr(strategy, "reasoning", result.get("reasoning", "Automatic recovery link generated.")),
        "installment_plan": getattr(strategy, "installment_plan", None),
        "payment_link": getattr(payload, "payment_link", result.get("payment_link", "")),
        "razorpay_payment_link_id": getattr(payload, "razorpay_payment_link_id", ""),
        "sms_message": getattr(payload, "sms_message", result.get("sms_message", "")),
        "sms_sid": result.get("sms_sid", ""),
        "notified": notify_result.get("notified", False) if isinstance(notify_result, dict) else False,
        "recovered": False,
    }

    try:
        row_id = insert_record(record)
        logger.info("Successfully recorded event %s to DB (row %s)", record["event_id"], row_id)
    except Exception as exc:
        logger.error("Failed to insert record into database: %s", exc)


@app.post("/webhook/razorpay")
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    raw_body = await request.body()
    body_str = raw_body.decode("utf-8")

    if x_razorpay_signature and not razorpay_service.verify_webhook_signature(body_str, x_razorpay_signature or ""):
        raise HTTPException(status_code=400, detail="Invalid or missing webhook signature")

    body = json.loads(body_str)
    event_type = body.get("event")

    # 1. Handle Successful Payment Recovery Events
    if event_type in ["payment_link.paid", "payment.captured"]:
        plink_entity = body.get("payload", {}).get("payment_link", {}).get("entity", {})
        plink_id = plink_entity.get("id")
        
        # Fallback check inside payment entity if sent via payment.captured
        if not plink_id:
            payment_entity = body.get("payload", {}).get("payment", {}).get("entity", {})
            plink_id = payment_entity.get("payment_link_id")

        all_events = fetch_all(limit=100)
        target_event_id = None

        # Search for explicit link match in SQLite records
        for ev in all_events:
            if ev.get("recovered") in [0, False]:
                ev_plink = str(ev.get("razorpay_payment_link_id") or "")
                ev_url = str(ev.get("payment_link") or "")
                if plink_id and (plink_id in ev_plink or plink_id in ev_url):
                    target_event_id = ev.get("event_id")
                    break

        # Fallback: Match the most recent pending record if explicit ID missing
        if not target_event_id and all_events:
            for ev in all_events:
                if ev.get("recovered") in [0, False]:
                    target_event_id = ev.get("event_id")
                    break

        if target_event_id:
            mark_recovered(target_event_id, True)
            logger.info("Recovery marked as paid for event %s (plink: %s)", target_event_id, plink_id)
            return {"status": "success", "message": f"Event {target_event_id} marked as recovered"}
            
        return {"status": "ignored", "reason": "No pending payment link record found to mark recovered"}

    # 2. Handle Payment Failure Events
    if event_type != "payment.failed":
        return {"status": "ignored", "reason": f"unhandled event type: {event_type}"}

    try:
        event = PaymentEvent.from_razorpay_webhook(body, merchant_id=body.get("account_id", "unknown"))
    except Exception as exc:
        logger.error("Failed to parse webhook payload: %s", exc)
        raise HTTPException(status_code=422, detail=f"Malformed payment.failed payload: {exc}") from exc

    result = await orchestrator.process(event)
    _save_event_to_db(event, result)

    channel_val = getattr(getattr(result.get("strategy"), "channel", None), "value", "sms")
    decided_by_val = getattr(result.get("strategy"), "decided_by", "Rule Engine")
    confidence_val = getattr(result.get("strategy"), "confidence_score", 0.95)
    payment_link_val = getattr(result.get("payload"), "payment_link", result.get("payment_link", ""))
    notified_val = result.get("notify_result", {}).get("notified", False) if isinstance(result.get("notify_result"), dict) else False

    return {
        "status": "processed",
        "event_id": event.event_id,
        "channel": channel_val,
        "decided_by": decided_by_val,
        "confidence": confidence_val,
        "payment_link": payment_link_val,
        "notified": notified_val,
    }


class SimulateRequest(BaseModel):
    customer_name: str = "Ashmitharaja"
    customer_phone: str = "+918778384434"
    customer_email: Optional[str] = None
    amount: float = 1.0
    decline_reason: DeclineReason = DeclineReason.AUTH_TIMEOUT
    payment_method: str = "card"
    bank: str = "HDFC Bank"
    retry_count: int = 0
    send_notifications: bool = True


_ERROR_CODE_FOR_REASON = {
    DeclineReason.AUTH_TIMEOUT: "payment.authentication.failed",
    DeclineReason.SOFT_LIMIT_EXCEEDED: "payment.limit.exceeded",
    DeclineReason.INSUFFICIENT_FUNDS: "payment.insufficient_funds",
    DeclineReason.BANK_SERVER_ERROR: "GATEWAY_ERROR",
    DeclineReason.OTP_FAILURE: "payment.otp.invalid",
    DeclineReason.CARD_EXPIRED: "payment.card.expired",
    DeclineReason.UNKNOWN: "server_error",
}


def _build_signed_webhook(req: SimulateRequest) -> tuple[str, str]:
    payment_id = f"pay_{uuid.uuid4().hex[:14]}"
    body: Dict[str, Any] = {
        "entity": "event",
        "account_id": "acc_ContextPulseDemo",
        "event": "payment.failed",
        "contains": ["payment"],
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "order_id": f"order_{uuid.uuid4().hex[:14]}",
                    "amount": int(round(req.amount * 100)),
                    "currency": "INR",
                    "status": "failed",
                    "method": req.payment_method,
                    "bank": req.bank,
                    "contact": req.customer_phone,
                    "email": req.customer_email,
                    "error_code": _ERROR_CODE_FOR_REASON[req.decline_reason],
                    "error_description": f"Simulated decline: {req.decline_reason.value}",
                    "notes": {
                        "customer_name": req.customer_name,
                        "customer_phone": req.customer_phone,
                        "retry_count": req.retry_count,
                    },
                    "created_at": int(time.time()),
                }
            }
        },
        "created_at": int(time.time()),
    }
    body_str = json.dumps(body)
    secret = settings.razorpay_webhook_secret or "local-dev-secret-do-not-use-in-prod"
    signature = hmac.new(secret.encode(), body_str.encode(), hashlib.sha256).hexdigest()
    return body_str, signature


@app.post("/simulate/payment-failed")
async def simulate_payment_failed(req: SimulateRequest = Body(...)) -> Dict[str, Any]:
    body_str, signature = _build_signed_webhook(req)

    if not settings.webhook_secret_configured():
        logger.warning("RAZORPAY_WEBHOOK_SECRET not set — bypassing signature verification for simulation")
        body = json.loads(body_str)
        event = PaymentEvent.from_razorpay_webhook(body, merchant_id="acc_ContextPulseDemo")
        result = await orchestrator.process(event, send_notifications=req.send_notifications)
        
        _save_event_to_db(event, result)

        channel_val = getattr(getattr(result.get("strategy"), "channel", None), "value", "sms")
        decided_by_val = getattr(result.get("strategy"), "decided_by", "Rule Engine")
        confidence_val = getattr(result.get("strategy"), "confidence_score", 0.95)
        reasoning_val = getattr(result.get("strategy"), "reasoning", "")
        payment_link_val = getattr(result.get("payload"), "payment_link", "")
        sms_message_val = getattr(result.get("payload"), "sms_message", "")
        notified_val = result.get("notify_result", {}).get("notified", False) if isinstance(result.get("notify_result"), dict) else False

        return {
            "status": "processed_unsigned",
            "event_id": event.event_id,
            "channel": channel_val,
            "decided_by": decided_by_val,
            "confidence": confidence_val,
            "reasoning": reasoning_val,
            "payment_link": payment_link_val,
            "sms_message": sms_message_val,
            "notified": notified_val,
        }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.base_url}/webhook/razorpay",
            content=body_str,
            headers={"Content-Type": "application/json", "X-Razorpay-Signature": signature},
            timeout=30.0,
        )
    return {"status": "posted_to_webhook", "webhook_response": resp.json()}


@app.get("/events")
async def list_events(limit: int = 100) -> Dict[str, Any]:
    return {"events": fetch_all(limit=limit)}


@app.get("/metrics")
async def metrics() -> Dict[str, Any]:
    return fetch_metrics()


@app.post("/events/{event_id}/mark-recovered")
async def mark_event_recovered(event_id: str) -> Dict[str, Any]:
    mark_recovered(event_id, True)
    return {"status": "ok", "event_id": event_id}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.webhook_server:app", host="0.0.0.0", port=8000, reload=True)