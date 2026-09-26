"""
Composer Module for Vera Bot
============================
LLM integration and prompt orchestrator with multi-provider support:
- OpenAI (GPT-4o-mini)
- Anthropic (Claude-3-5-Haiku)
- Google Gemini (gemini-2.0-flash)
- Deterministic template fallback via templates.py
"""

import os
import json
import re
from typing import Dict, Any, Optional
import httpx
from dotenv import load_dotenv

from storage import storage
from rules import evaluate_rules_for_reply, sanitize_message_body
import templates

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

if OPENAI_API_KEY:
    LLM_PROVIDER = "openai"
    LLM_MODEL = "gpt-4o-mini"
elif ANTHROPIC_API_KEY:
    LLM_PROVIDER = "anthropic"
    LLM_MODEL = "claude-3-5-haiku-20241022"
elif GEMINI_API_KEY:
    LLM_PROVIDER = "gemini"
    LLM_MODEL = "gemini-flash-latest"
else:
    LLM_PROVIDER = "none"
    LLM_MODEL = "deterministic-engine"


COMPOSE_SYSTEM_PROMPT = """You are Vera, magicpin's trusted WhatsApp AI growth advisor for Indian merchant partners.
Your mission is to compose a concise, high-converting WhatsApp message.

STRICT SCORING GUIDELINES:
1. SPECIFICITY: Anchor on 1-2 concrete, verifiable facts from the provided context (exact % change, view count, citation source, pricing).
2. CATEGORY FIT:
   - Clinics / Dentists: Clinical peer-to-peer tone. Address owner as "Dr. <FirstName>".
   - Salons / Spas: Warm, friendly, practical styling/grooming tone.
   - Restaurants / Cafes: Operator-to-operator, busy hour and footfall focus.
   - Gyms / Fitness: Energizing coach tone.
   - Pharmacies: Trustworthy, essential wellness.
3. MERCHANT FIT: Use owner's name and store name accurately. Respect language preference (natural Hinglish if 'hi' in languages).
4. TRIGGER RELEVANCE: Clearly explain "WHY NOW" based on the trigger payload.
5. NO INTERNAL JARGON: Never say 'trigger', 'payload', 'suppression_key', 'CTR delta', or 'endpoint'.
6. NO URLS: Do not include http/https links in the message body.
7. ACTIONABLE CTA: End with a low-friction binary question (e.g., "Reply YES to review", "Reply YES to publish").
8. LENGTH: 2 to 4 sentences maximum.

TRIGGER BEHAVIOR:
- research_digest: Cite the specific study/journal and key statistic. Offer a draft educational post.
- perf_spike: State the exact positive delta and offer a quick weekend flash promo.
- perf_dip: State the dip clearly with loss-aversion framing and recovery campaign.
- milestone_reached: Celebrate the exact milestone reached with customer reward.
- recall_due (send_as="merchant_on_behalf"): Message customer referencing last visit service and offer specific slot choices.
- category_trend_movement: Mention trending search query and YoY growth percentage.
- dormant_with_vera / stale_posts: Cite peer benchmark CTR or days inactive and offer instant 1-click draft.

OUTPUT FORMAT:
Respond ONLY with a valid JSON object (no markdown code fences):
{
  "body": "<WhatsApp message text>",
  "cta": "binary_yes_no" | "open_ended" | "multi_choice_slot",
  "send_as": "vera" | "merchant_on_behalf",
  "suppression_key": "<suppression_key>",
  "rationale": "<1-2 sentence explanation of why this was generated>"
}"""

REPLY_SYSTEM_PROMPT = """You are Vera, magicpin's WhatsApp AI assistant chatting with a merchant partner.
Your goal is to guide the conversation forward effectively.

RULES:
1. If the merchant committed or agreed (e.g. "yes", "let's do it", "proceed"), DO NOT ask qualifying questions. Switch to ACTION mode immediately ("Done! Here is the plan...").
2. Keep replies brief, supportive, and business-focused (2 sentences max).
3. If they ask a question, answer directly from store context without making up facts.
4. If they want to stop, gracefully close.

OUTPUT FORMAT:
Respond ONLY with a valid JSON object:
{
  "action": "send" | "wait" | "end",
  "body": "<message text if action is send>",
  "cta": "binary_yes_no" | "open_ended" | "none",
  "wait_seconds": <integer if action is wait>,
  "rationale": "<brief explanation>"
}"""


def _clean_json_str(raw: str) -> str:
    cleaned = raw.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def call_llm(system_prompt: str, user_prompt: str, temperature: float = 0.0) -> Optional[str]:
    """Call configured LLM provider with error handling and timeout."""
    if LLM_PROVIDER == "none":
        return None

    try:
        if LLM_PROVIDER == "openai":
            resp = httpx.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                json={
                    "model": LLM_MODEL,
                    "temperature": temperature,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                },
                timeout=20.0,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()

        elif LLM_PROVIDER == "anthropic":
            resp = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                },
                json={
                    "model": LLM_MODEL,
                    "max_tokens": 512,
                    "temperature": temperature,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": user_prompt}],
                },
                timeout=20.0,
            )
            resp.raise_for_status()
            return resp.json()["content"][0]["text"].strip()

        elif LLM_PROVIDER == "gemini":
            resp = httpx.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{LLM_MODEL}:generateContent?key={GEMINI_API_KEY}",
                json={
                    "contents": [{"parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]}],
                    "generationConfig": {"temperature": temperature, "maxOutputTokens": 512},
                },
                timeout=20.0,
            )
            resp.raise_for_status()
            return resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()

    except Exception:
        return None

    return None


def compose_message(
    category: dict,
    merchant: dict,
    trigger: dict,
    customer: Optional[dict] = None
) -> Dict[str, Any]:
    """Compose initial outbound message using LLM or deterministic template fallback."""
    trg_kind = trigger.get("kind", "")
    trg_pay = trigger.get("payload", {})
    supp_key = trigger.get("suppression_key", f"{trg_kind}:{merchant.get('merchant_id', 'm')}")

    # Build detailed context for LLM
    identity = merchant.get("identity", {})
    m_name = identity.get("name", "Merchant")
    owner = identity.get("owner_first_name", m_name.split()[0])
    langs = identity.get("languages", ["en"])
    cat_slug = merchant.get("category_slug", category.get("slug", ""))
    perf = merchant.get("performance", {})
    peer = category.get("peer_stats", {})
    trends = category.get("trend_signals", [])
    digest = category.get("digest", [])
    voice = category.get("voice", {})

    top_id = trg_pay.get("top_item_id", "")
    digest_item = next((d for d in digest if d.get("id") == top_id), digest[0] if digest else None)

    cust_info = ""
    if customer:
        c_ident = customer.get("identity", {})
        c_rel = customer.get("relationship", {})
        cust_info = f"""
TARGET CUSTOMER:
  Name: {c_ident.get('name', 'Customer')}
  Last Visit: {c_rel.get('last_visit', 'N/A')}
  Services: {c_rel.get('services_received', [])}
  Preferred Slots: {customer.get('preferences', {}).get('preferred_slots', 'anytime')}
"""

    user_prompt = f"""CONTEXT:
Category: {cat_slug} (Voice Tone: {voice.get('tone', 'professional')})
Category Peer Avg CTR: {peer.get('avg_ctr')}, Avg Rating: {peer.get('avg_rating')}
Category Trends: {[t.get('query') for t in trends[:3]]}
Category Digest Item: {json.dumps(digest_item, ensure_ascii=False) if digest_item else "None"}

Merchant: {m_name} (Owner: {owner})
City: {identity.get('city', '')} | Languages: {langs}
Performance (30d): views={perf.get('views')}, calls={perf.get('calls')}, ctr={perf.get('ctr')}
Delta (7d): {perf.get('delta_7d', {})}
Active Offers: {[o.get('title') for o in merchant.get('offers', []) if o.get('status') == 'active']}

Trigger:
  Kind: {trg_kind}
  Suppression Key: {supp_key}
  Payload: {json.dumps(trg_pay, ensure_ascii=False)}
{cust_info}
Instructions: Output ONLY valid JSON."""

    raw_llm = call_llm(COMPOSE_SYSTEM_PROMPT, user_prompt, temperature=0.0)
    if raw_llm:
        try:
            parsed = json.loads(_clean_json_str(raw_llm))
            body = sanitize_message_body(parsed.get("body", ""))
            if body:
                return {
                    "body": body,
                    "cta": parsed.get("cta", "binary_yes_no"),
                    "send_as": parsed.get("send_as", "vera" if not customer else "merchant_on_behalf"),
                    "suppression_key": parsed.get("suppression_key", supp_key),
                    "rationale": parsed.get("rationale", "Composed via LLM from verified merchant context.")
                }
        except Exception:
            pass

    # High-quality deterministic fallback
    return templates.render_template_message(category, merchant, trigger, customer)


def compose_reply(
    conv_id: str,
    merchant_id: str,
    customer_id: Optional[str],
    message: str,
    turn_number: int
) -> Dict[str, Any]:
    """Compose next turn reply using rule fast-path or LLM."""
    # 1. Fast-path rules check
    rule_action = evaluate_rules_for_reply(conv_id, merchant_id, customer_id, message, turn_number)
    if rule_action:
        return rule_action

    # 2. Conversational LLM continuation
    conv = storage.get_conversation(conv_id) or {}
    turns = conv.get("turns", [])
    sent_bodies = conv.get("sent_bodies", [])
    m_ctx = storage.get_context("merchant", merchant_id) or {}

    history_str = "\n".join(
        f"[{t.get('from', 'user').upper()}] {t.get('msg', '')}" for t in turns[-6:]
    )

    user_prompt = f"""CONVERSATION LOG:
{history_str}

LATEST MERCHANT MESSAGE (Turn {turn_number}): "{message}"
MERCHANT STORE: {m_ctx.get('identity', {}).get('name', merchant_id)}
PREVIOUSLY SENT BY VERA: {sent_bodies[-3:]}

Decide next action (send / wait / end). Output ONLY JSON."""

    raw_llm = call_llm(REPLY_SYSTEM_PROMPT, user_prompt, temperature=0.0)
    if raw_llm:
        try:
            parsed = json.loads(_clean_json_str(raw_llm))
            action = parsed.get("action", "send")
            body = sanitize_message_body(parsed.get("body", ""))
            if action != "send" or body:
                return {
                    "action": action,
                    "body": body,
                    "cta": parsed.get("cta", "binary_yes_no"),
                    "wait_seconds": parsed.get("wait_seconds", 3600),
                    "rationale": parsed.get("rationale", "LLM conversational continuation.")
                }
        except Exception:
            pass

    # Deterministic fallback response with category-aware salutation
    salutation = templates.get_merchant_salutation(m_ctx, m_ctx.get("category_slug", ""))
    return {
        "action": "send",
        "body": f"Samajh gayi {salutation}! Main is par kaam shuru kar rahi hoon. Reply YES to confirm.",
        "cta": "binary_yes_no",
        "rationale": "Deterministic conversational acknowledgement."
    }


def respond(state: Any, merchant_message: str) -> Dict[str, Any]:
    """Optional multi-turn responder conforming to challenge-brief.md §7.4."""
    if isinstance(state, dict):
        conv_id = state.get("conversation_id", "conv_default")
        merchant_id = state.get("merchant_id", "m_default")
        customer_id = state.get("customer_id")
        turn_number = len(state.get("turns", [])) + 1
        if state.get("merchant"):
            storage.set_context("merchant", merchant_id, 1, state["merchant"])
        if state.get("category"):
            storage.set_context("category", state["category"].get("slug", "default"), 1, state["category"])
    else:
        conv_id = getattr(state, "conversation_id", "conv_default")
        merchant_id = getattr(state, "merchant_id", "m_default")
        customer_id = getattr(state, "customer_id", None)
        turn_number = len(getattr(state, "turns", [])) + 1

    return compose_reply(
        conv_id=conv_id,
        merchant_id=merchant_id,
        customer_id=customer_id,
        message=merchant_message,
        turn_number=turn_number,
    )


# Alias for submission/testing harnesses
compose = compose_message
