from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

from dotenv import load_dotenv
import razorpay
from google import genai
from twilio.rest import Client

from .models import PaymentEvent

# Load variables from .env file into os.environ
load_dotenv()

logger = logging.getLogger("contextpulse.orchestrator")


def create_razorpay_native_link(amount: float, customer_phone: str) -> Optional[str]:
    key_id = os.getenv("RAZORPAY_KEY_ID")
    key_secret = os.getenv("RAZORPAY_KEY_SECRET")

    if not key_id or not key_secret:
        logger.warning("Razorpay API credentials missing. Skipping native link creation.")
        return None

    try:
        client = razorpay.Client(auth=(key_id, key_secret))
        link = client.payment_link.create({
            "amount": int(amount * 100),  # Amount in paise
            "currency": "INR",
            "accept_partial": False,
            "description": "Payment Recovery Link",
            "customer": {
                "contact": customer_phone
            },
            "notify": {
                "sms": True,     # Triggers native Razorpay SMS (as seen in screenshot)
                "email": False
            }
        })
        return link.get("short_url")
    except Exception as exc:
        logger.error("Failed to create Razorpay native payment link: %s", exc)
        return None


class TwilioNotifier:
    def __init__(self):
        self.account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        self.auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        self.sms_from = os.getenv("TWILIO_SMS_FROM")
        self.client: Optional[Client] = None

        if self.is_live():
            try:
                self.client = Client(self.account_sid, self.auth_token)
            except Exception as e:
                logger.error("Failed to initialize Twilio client: %s", e)

    def is_live(self) -> bool:
        return bool(self.account_sid and self.auth_token and self.sms_from)

    def send_sms(self, to_phone: str, message_body: str) -> Dict[str, Any]:
        if not self.client:
            logger.warning("Twilio client is not initialized. Skipping notification.")
            return {"notified": False, "error": "Twilio client uninitialized"}

        try:
            message = self.client.messages.create(
                body=message_body,
                from_=self.sms_from,
                to=to_phone
            )
            logger.info("Successfully dispatched Twilio SMS (SID: %s) to %s", message.sid, to_phone)
            return {"notified": True, "sid": message.sid, "status": message.status}
        except Exception as exc:
            logger.error("Failed to dispatch Twilio SMS to %s: %s", to_phone, exc)
            return {"notified": False, "error": str(exc)}


class StrategyChannel:
    value = "sms"


class RecoveryStrategy:
    def __init__(self, decided_by: str, confidence_score: float, reasoning: str):
        self.channel = StrategyChannel()
        self.decided_by = decided_by
        self.confidence_score = confidence_score
        self.reasoning = reasoning
        self.strategy_id = "strat_live_recovery"
        self.urgency_level = "high"
        self.recommended_action = "Send SMS Recovery Link"
        self.installment_plan = None


class RecoveryPayload:
    def __init__(self, payment_link: str, sms_message: str):
        self.payload_id = "pay_live_link"
        self.payment_link = payment_link
        self.sms_message = sms_message
        self.razorpay_payment_link_id = ""


class Orchestrator:
    def __init__(self):
        self.notifier = TwilioNotifier()

    async def process(self, event: PaymentEvent, send_notifications: bool = True) -> Dict[str, Any]:
        event_id = getattr(event, "event_id", "evt_demo")
        amount = getattr(event, "amount", 0)
        customer_phone = getattr(event, "customer_phone", "")
        decline_reason = getattr(event, "decline_reason", "unknown")
        bank = getattr(event, "bank", "N/A")
        payment_method = getattr(event, "payment_method", "N/A")

        logger.info("Processing failed payment event: %s", event_id)

        prompt = (
            f"Payment of INR {amount} failed for customer {customer_phone}. "
            f"Reason: {decline_reason}. Bank: {bank}. Method: {payment_method}."
        )

        llm_response = call_llm_agent(prompt)

        # Generate live native link from Razorpay (triggers native SMS if customer_phone exists)
        native_link = None
        if customer_phone:
            native_link = create_razorpay_native_link(amount=amount, customer_phone=customer_phone)

        payment_identifier = getattr(event, "payment_id", event_id)
        payment_link = native_link or f"https://rzp.io/i/{payment_identifier}"
        sms_message = f"Razorpay Payment Failure: Your transaction of INR {amount} failed. Click to complete payment safely: {payment_link}"

        strategy = RecoveryStrategy(
            decided_by=llm_response["provider"],
            confidence_score=0.95,
            reasoning=llm_response["decision"]
        )

        payload = RecoveryPayload(payment_link=payment_link, sms_message=sms_message)

        notify_result = {"notified": False}
        sms_sid = ""

        # Trigger Twilio fallback notification if needed
        if send_notifications and customer_phone and not native_link:
            notify_result = self.notifier.send_sms(to_phone=customer_phone, message_body=sms_message)
            sms_sid = notify_result.get("sid", "")

        return {
            "strategy": strategy,
            "payload": payload,
            "notify_result": notify_result,
            "recovery_url": payment_link,
            "payment_link": payment_link,
            "sms_message": sms_message,
            "sms_sid": sms_sid,
            "decided_by": llm_response["provider"],
            "reasoning": llm_response["decision"],
            "strategy_reasoning": llm_response["decision"],
            "status": "success"
        }


def call_llm_agent(prompt: str) -> dict:
    gemini_key = os.getenv("GEMINI_API_KEY")
    provider = os.getenv("LLM_PROVIDER", "gemini").lower()

    if provider == "gemini" and gemini_key:
        try:
            client = genai.Client(api_key=gemini_key)
            model_name = os.getenv("LLM_MODEL", "gemini-2.0-flash")

            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
            )

            return {
                "decision": response.text,
                "provider": "Google Gemini",
                "status": "success"
            }
        except Exception as e:
            logger.warning("Gemini API call failed (%s) — falling back to rule engine", e)

    return run_rule_engine(prompt)


def run_rule_engine(prompt: str) -> dict:
    logger.info("Executing rule engine fallback for context analysis")
    return {
        "decision": "Automatic Rule Engine: Instant recovery link generated via native payment channel.",
        "provider": "Rule Engine Fallback",
        "status": "fallback"
    }


orchestrator = Orchestrator()