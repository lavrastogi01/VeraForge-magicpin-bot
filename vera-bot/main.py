"""
Main FastAPI Application for Vera Bot
=====================================
magicpin AI Challenge Official Endpoints:
- GET  /v1/healthz
- GET  /v1/metadata
- POST /v1/context
- POST /v1/tick
- POST /v1/reply
- POST /v1/teardown

Usage:
  cd vera-bot && python3 -m uvicorn main:app --host 0.0.0.0 --port 8080 --reload
"""

import time
from datetime import datetime, timezone
from typing import Any, Optional, List, Dict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from storage import storage
from composer import compose_message, compose_reply, respond, LLM_MODEL, LLM_PROVIDER

APP_VERSION = "1.0.0"
START_TIME = time.time()

TEAM_NAME = "VeraForge"
TEAM_MEMBERS = ["Lav Rastogi"]
CONTACT_EMAIL = "lavrastogi01@gmail.com"

app = FastAPI(
    title="Vera Bot — magicpin AI Challenge",
    description="Intelligent Merchant Engagement Bot for WhatsApp",
    version=APP_VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── ROOT & HEALTH ─────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    """Welcome index displaying bot status and active API documentation."""
    return {
        "status": "online",
        "bot": "Vera — Merchant Engagement Agent",
        "team": TEAM_NAME,
        "challenge": "magicpin AI Challenge",
        "docs": "/docs",
        "endpoints": [
            "/v1/healthz",
            "/v1/metadata",
            "/v1/context",
            "/v1/tick",
            "/v1/reply",
        ],
    }


@app.get("/v1/healthz")
async def healthz():
    """Healthcheck reporting uptime and loaded contexts."""
    return {
        "status": "ok",
        "uptime_seconds": int(time.time() - START_TIME),
        "contexts_loaded": storage.count_contexts(),
    }


@app.get("/v1/metadata")
async def metadata():
    """Metadata describing the bot configuration and team details."""
    return {
        "team_name": TEAM_NAME,
        "team_members": TEAM_MEMBERS,
        "model": LLM_MODEL,
        "llm_provider": LLM_PROVIDER,
        "approach": "Modular trigger-aware architecture with fast-path deterministic rules and multi-provider LLM orchestration",
        "contact_email": CONTACT_EMAIL,
        "version": APP_VERSION,
        "submitted_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


# ── CONTEXT PUSH ──────────────────────────────────────────────────────────────

class ContextPushRequest(BaseModel):
    scope: str
    context_id: str
    version: int
    payload: Dict[str, Any]
    delivered_at: Optional[str] = None


@app.post("/v1/context")
async def push_context(body: ContextPushRequest):
    """Ingest category, merchant, customer, or trigger context."""
    accepted, result, cur_ver = storage.set_context(
        scope=body.scope,
        context_id=body.context_id,
        version=body.version,
        payload=body.payload,
    )
    if not accepted:
        if result == "stale_version":
            return JSONResponse(
                status_code=409,
                content={
                    "accepted": False,
                    "reason": "stale_version",
                    "current_version": cur_ver,
                }
            )
        return JSONResponse(
            status_code=400,
            content={"accepted": False, "reason": "invalid_scope", "details": result}
        )

    return {
        "accepted": True,
        "ack_id": result,
        "stored_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


# ── TICK ENGINE ───────────────────────────────────────────────────────────────

class TickRequest(BaseModel):
    now: str
    available_triggers: List[str] = []


@app.post("/v1/tick")
async def tick(body: TickRequest):
    """Evaluate pending triggers and generate outbound engagement actions."""
    actions = []

    for trg_id in body.available_triggers:
        if len(actions) >= 20:
            break

        trg = storage.get_context("trigger", trg_id)
        if not trg:
            continue

        supp_key = trg.get("suppression_key", "")
        if supp_key and storage.is_suppressed(supp_key):
            continue

        merchant_id = trg.get("merchant_id") or trg.get("payload", {}).get("merchant_id", "")
        if not merchant_id:
            continue

        merchant = storage.get_context("merchant", merchant_id)
        if not merchant:
            continue

        cat_slug = merchant.get("category_slug", "")
        category = storage.get_context("category", cat_slug) or {}

        customer = None
        cust_id = trg.get("customer_id") or trg.get("payload", {}).get("customer_id")
        if cust_id:
            customer = storage.get_context("customer", cust_id)

        conv_id = f"conv_{merchant_id}_{trg_id}"
        if storage.is_ended(conv_id):
            continue

        composed = compose_message(category, merchant, trg, customer)
        body_text = composed.get("body", "").strip()
        if not body_text:
            continue

        if supp_key:
            storage.add_suppression(supp_key)

        # Record Vera's initial turn in storage
        storage.record_turn(
            conv_id=conv_id,
            from_role="vera",
            message=body_text,
            merchant_id=merchant_id,
            customer_id=cust_id,
            timestamp=body.now,
            turn_number=1,
        )

        m_name = merchant.get("identity", {}).get("name", "Merchant")
        snippet = body_text[:100] + "..." if len(body_text) > 100 else body_text

        actions.append({
            "conversation_id": conv_id,
            "merchant_id": merchant_id,
            "customer_id": cust_id,
            "send_as": composed.get("send_as", "vera"),
            "trigger_id": trg_id,
            "template_name": f"vera_{trg.get('kind', 'generic')}_v1",
            "template_params": [m_name, snippet, "Reply YES or STOP."],
            "body": body_text,
            "cta": composed.get("cta", "binary_yes_no"),
            "suppression_key": composed.get("suppression_key", supp_key),
            "rationale": composed.get("rationale", "Composed from verified context."),
        })

    return {"actions": actions}


# ── REPLY ROUTE ───────────────────────────────────────────────────────────────

class ReplyRequest(BaseModel):
    conversation_id: str
    merchant_id: Optional[str] = None
    customer_id: Optional[str] = None
    from_role: str = "merchant"
    message: str
    received_at: str
    turn_number: int


@app.post("/v1/reply")
async def reply(body: ReplyRequest):
    """Handle incoming message turn and decide next bot action."""
    cid = body.conversation_id
    mid = body.merchant_id

    # Record incoming turn
    storage.record_turn(
        conv_id=cid,
        from_role=body.from_role,
        message=body.message,
        merchant_id=mid,
        customer_id=body.customer_id,
        timestamp=body.received_at,
        turn_number=body.turn_number,
    )

    if storage.is_ended(cid):
        return {
            "action": "end",
            "rationale": "Conversation is already marked as ended.",
        }

    # Decide next step
    result = compose_reply(
        conv_id=cid,
        merchant_id=mid or "",
        customer_id=body.customer_id,
        message=body.message,
        turn_number=body.turn_number,
    )

    action = result.get("action", "send")
    if action == "send":
        out_body = result.get("body", "")
        storage.record_turn(
            conv_id=cid,
            from_role="vera",
            message=out_body,
            merchant_id=mid,
            customer_id=body.customer_id,
            turn_number=body.turn_number + 1,
        )
    elif action == "end":
        storage.end_conversation(cid)

    return result


# ── TEARDOWN ──────────────────────────────────────────────────────────────────

@app.post("/v1/teardown")
async def teardown():
    """Reset all in-memory contexts and states."""
    storage.reset_all()
    return {
        "status": "wiped",
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


# Exported composition interface for harness/testing
compose = compose_message


if __name__ == "__main__":
    import uvicorn
    print(f"🚀 Starting Vera Bot [{LLM_PROVIDER.upper()} / {LLM_MODEL}] on http://0.0.0.0:8080")
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=False)
