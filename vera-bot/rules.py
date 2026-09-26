"""
Rules and Guardrails Module for Vera Bot
========================================
Handles:
- Intent classification (auto-reply, hard stop/hostile, positive commitment, off-topic)
- Auto-reply backoff & loop termination
- Action mode transition upon commitment (no re-qualifying)
- Guardrails (quiet hours, jargon cleanup, URL validation)
"""

import re
from typing import Dict, Any, Optional, Tuple
from storage import storage


# Regex patterns for intent detection
AUTO_REPLY_PATTERN = re.compile(
    r"thank you for contacting|our team will (respond|get back)|automated (message|assistant|response)"
    r"|i am an automated|this is an auto|auto.?reply|system generated message"
    r"|aapki jaankari ke liye.*team tak|hume contact karne ke liye dhanyavad",
    re.IGNORECASE,
)

HARD_STOP_PATTERN = re.compile(
    r"\b(stop|unsubscribe|not interested|spam|useless spam|leave me alone|don't (contact|message|text)"
    r"|mujhe nahi chahiye|band karo|mat bhejo|roko|block|report|disturb mat|faltu|not needed)\b",
    re.IGNORECASE,
)

INTENT_YES_PATTERN = re.compile(
    r"\b(yes|yeah|sure|ok|okay|haan|kar do|chalega|bhej do|let.?s do it|whats next|what.?s next"
    r"|go ahead|confirm|proceed|start|interested|ready|bana do|theek hai)\b",
    re.IGNORECASE,
)

OFF_TOPIC_PATTERN = re.compile(
    r"\b(gst filing|income tax|itr|ca audit|lawyer|court case|fir|police|litigation)\b",
    re.IGNORECASE,
)

# Internal terms that must never appear in merchant-facing messages
INTERNAL_JARGON = [
    "trigger", "payload", "suppression_key", "ctr delta", "algorithm",
    "conversion_rate_delta", "customer_aggregate", "json", "endpoint"
]


def detect_intent(message: str) -> str:
    """Classify the incoming merchant message intent."""
    msg = message.strip()
    if AUTO_REPLY_PATTERN.search(msg):
        return "auto_reply"
    if HARD_STOP_PATTERN.search(msg):
        return "hard_stop"
    if INTENT_YES_PATTERN.search(msg):
        return "intent_yes"
    if OFF_TOPIC_PATTERN.search(msg):
        return "off_topic"
    return "general"


def sanitize_message_body(text: str) -> str:
    """Strip or replace internal system jargon if accidentally generated."""
    cleaned = text
    for term in INTERNAL_JARGON:
        pattern = re.compile(re.escape(term), re.IGNORECASE)
        if term in ["trigger", "payload"]:
            cleaned = pattern.sub("update", cleaned)
        elif term in ["suppression_key", "json", "endpoint"]:
            cleaned = pattern.sub("", cleaned)
        elif term == "ctr delta":
            cleaned = pattern.sub("growth in customer views", cleaned)
        else:
            cleaned = pattern.sub("system update", cleaned)
    # Clean redundant whitespaces
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def evaluate_rules_for_reply(
    conv_id: str,
    merchant_id: str,
    customer_id: Optional[str],
    message: str,
    turn_number: int,
) -> Optional[Dict[str, Any]]:
    """
    Fast-path rule evaluation before calling LLM.
    Returns response dict if handled deterministically, or None to pass to LLM.
    """
    intent = detect_intent(message)

    # 1. Hostile / Hard Stop -> End immediately with clean rationale
    if intent == "hard_stop":
        storage.end_conversation(conv_id)
        return {
            "action": "end",
            "rationale": "Merchant opted out or sent hostile message. Terminating conversation immediately.",
        }

    # 2. Automated Assistant / Canned reply -> Backoff or End
    if intent == "auto_reply":
        auto_count = storage.increment_auto_reply(merchant_id)
        # Check turn number and consecutive auto-replies
        if auto_count >= 2 or turn_number >= 3:
            storage.end_conversation(conv_id)
            return {
                "action": "end",
                "rationale": f"Consecutive automated replies detected ({auto_count}x). Ending conversation.",
            }
        else:
            return {
                "action": "wait",
                "wait_seconds": 14400,
                "rationale": "Automated response received. Backing off 4 hours before any follow-up.",
            }

    # 3. Positive commitment -> Immediately switch to ACTION mode
    # Strictly avoid qualifying questions ("would you", "can you tell", etc.)
    if intent == "intent_yes":
        from templates import get_merchant_salutation
        m_ctx = storage.get_context("merchant", merchant_id) or {}
        cat_slug = m_ctx.get("category_slug", "")
        salutation = get_merchant_salutation(m_ctx, cat_slug)

        action_body = (
            f"Done! Here is your campaign draft for {salutation}: Special exclusive offer is ready to launch. "
            f"Reply CONFIRM to publish right away, or say EDIT to make any changes."
        )
        return {
            "action": "send",
            "body": action_body,
            "cta": "binary_yes_no",
            "rationale": "Merchant showed direct commitment. Switched immediately to action mode with prepared draft.",
        }

    # 4. Off-topic (Tax / Legal / ITR)
    if intent == "off_topic":
        return {
            "action": "send",
            "body": (
                "Main sirf aapke magicpin store growth, offers aur customer engagement mein madad kar sakti hoon. "
                "Tax ya legal mamlon ke liye kripya apne CA ya advisor se consult karein. "
                "Kya aapko store offers mein koi help chahiye?"
            ),
            "cta": "binary_yes_no",
            "rationale": "Politely declined off-topic query and redirected to magicpin growth.",
        }

    return None
