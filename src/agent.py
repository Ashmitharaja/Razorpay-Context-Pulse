"""
Reasoning agent powered strictly by OpenAI API via Pydantic AI.
"""

from __future__ import annotations

import uuid

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from .config import settings
from .models import PaymentEvent, RecoveryStrategy

SYSTEM_PROMPT = """\
You are ContextPulse, an autonomous revenue-recovery agent embedded in a \
payments platform. You are handed a single failed payment event and must \
decide the single best 1-click recovery channel for the customer.

Rules of thumb:
- AUTH_TIMEOUT, OTP_FAILURE, BANK_SERVER_ERROR: these are transient/redirect \
  failures, not hard declines. Prefer UPI_ONE_TAP since it skips the OTP/3DS \
  redirect step that just failed, and settles on a different rail (NPCI) than \
  the card network.
- SOFT_LIMIT_EXCEEDED: if amount > 3000 INR, prefer MICRO_INSTALLMENT (split \
  into 2-3 parts, each under the likely cap). If amount <= 3000, prefer \
  ALT_PAYMENT_METHOD.
- INSUFFICIENT_FUNDS: prefer MICRO_INSTALLMENT to reduce the single-charge size.
- CARD_EXPIRED: this is a hard decline — prefer ALT_PAYMENT_METHOD, since \
  retrying the same instrument will never succeed.
- If retry_count >= 2, treat this as urgent (raise urgency_level, lower \
  confidence_score to reflect channel fatigue risk).

Always populate `reasoning` with 3-6 short, concrete steps that reference the \
specific fields of the event you were given (amount, method, bank, decline \
reason, retry_count) — do not write generic boilerplate. Set `decided_by` to \
exactly "llm_agent". Generate a fresh `strategy_id` starting with "strat_".
"""


def _build_model() -> OpenAIChatModel:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY not set in .env")
    return OpenAIChatModel(
        settings.llm_model,
        provider=OpenAIProvider(api_key=settings.openai_api_key),
    )


_agent: Agent | None = None


def get_agent() -> Agent:
    global _agent
    if _agent is None:
        _agent = Agent(
            _build_model(),
            output_type=RecoveryStrategy,
            system_prompt=SYSTEM_PROMPT,
            retries=2,
        )
    return _agent


async def analyze_with_llm(event: PaymentEvent) -> RecoveryStrategy:
    agent = get_agent()
    prompt = (
        f"Failed payment event (id={event.event_id}):\n"
        f"{event.model_dump_json(indent=2)}\n\n"
        f"Decide the recovery strategy now."
    )
    result = await agent.run(prompt)
    strategy = result.output
    strategy.event_id = event.event_id
    if not strategy.strategy_id or not strategy.strategy_id.startswith("strat_"):
        strategy.strategy_id = f"strat_{uuid.uuid4().hex[:10]}"
    strategy.decided_by = "llm_agent"
    return strategy
