"""
Storage Module for Vera Bot
===========================
In-memory structured state store with context caching,
conversation history, deduplication, and suppression tracking.
"""

from datetime import datetime, timezone
from typing import Any, Optional, Dict, Set, Tuple


class BotStorage:
    def __init__(self):
        # (scope, context_id) -> {"version": int, "payload": dict}
        self.contexts: Dict[Tuple[str, str], Dict[str, Any]] = {}
        
        # conv_id -> {
        #   "merchant_id": str,
        #   "customer_id": Optional[str],
        #   "turns": list[dict],
        #   "sent_bodies": list[str],
        #   "state": str, # "active" | "ended"
        #   "last_activity": str
        # }
        self.conversations: Dict[str, Dict[str, Any]] = {}
        
        # Track auto-reply frequency per merchant to detect loops across changing conv_ids
        self.merchant_auto_replies: Dict[str, int] = {}
        
        # Suppression keys (e.g. "trigger_kind:merchant_id")
        self.suppressions: Set[str] = set()
        
        # Set of conversation IDs marked as ended
        self.ended_conversations: Set[str] = set()

    def set_context(self, scope: str, context_id: str, version: int, payload: dict) -> Tuple[bool, str, Optional[int]]:
        """
        Store a context document with monotonic version checks.
        Returns: (accepted, reason_or_ack, current_version)
        """
        valid_scopes = {"category", "merchant", "customer", "trigger"}
        if scope not in valid_scopes:
            return False, f"Invalid scope '{scope}'. Allowed: {valid_scopes}", None

        key = (scope, context_id)
        current = self.contexts.get(key)
        if current:
            if current["version"] > version:
                return False, "stale_version", current["version"]
            if current["version"] == version:
                # Idempotent re-post is a successful no-op
                return True, f"ack_{context_id}_v{version}", version

        self.contexts[key] = {
            "version": version,
            "payload": payload,
            "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        ack_id = f"ack_{context_id}_v{version}"
        return True, ack_id, version

    def get_context(self, scope: str, context_id: str) -> Optional[dict]:
        """Fetch payload for a given scope and ID."""
        entry = self.contexts.get((scope, context_id))
        return entry["payload"] if entry else None

    def get_context_version(self, scope: str, context_id: str) -> Optional[int]:
        entry = self.contexts.get((scope, context_id))
        return entry["version"] if entry else None

    def count_contexts(self) -> Dict[str, int]:
        counts = {"category": 0, "merchant": 0, "customer": 0, "trigger": 0}
        for (scope, _) in self.contexts:
            if scope in counts:
                counts[scope] += 1
        return counts

    def is_suppressed(self, suppression_key: str) -> bool:
        if not suppression_key:
            return False
        return suppression_key in self.suppressions

    def add_suppression(self, suppression_key: str):
        if suppression_key:
            self.suppressions.add(suppression_key)

    def is_ended(self, conv_id: str) -> bool:
        return conv_id in self.ended_conversations

    def end_conversation(self, conv_id: str):
        self.ended_conversations.add(conv_id)
        if conv_id in self.conversations:
            self.conversations[conv_id]["state"] = "ended"

    def record_turn(
        self,
        conv_id: str,
        from_role: str,
        message: str,
        merchant_id: Optional[str] = None,
        customer_id: Optional[str] = None,
        timestamp: Optional[str] = None,
        turn_number: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Record an incoming or outgoing conversation turn."""
        if conv_id not in self.conversations:
            self.conversations[conv_id] = {
                "merchant_id": merchant_id or "",
                "customer_id": customer_id,
                "turns": [],
                "sent_bodies": [],
                "state": "active",
                "last_activity": timestamp or datetime.now(timezone.utc).isoformat(),
            }

        conv = self.conversations[conv_id]
        if merchant_id and not conv.get("merchant_id"):
            conv["merchant_id"] = merchant_id
        if customer_id and not conv.get("customer_id"):
            conv["customer_id"] = customer_id

        conv["turns"].append({
            "from": from_role,
            "msg": message,
            "ts": timestamp or datetime.now(timezone.utc).isoformat(),
            "turn": turn_number or (len(conv["turns"]) + 1),
        })
        conv["last_activity"] = timestamp or datetime.now(timezone.utc).isoformat()

        if from_role == "vera":
            conv["sent_bodies"].append(message)

        return conv

    def get_conversation(self, conv_id: str) -> Optional[Dict[str, Any]]:
        return self.conversations.get(conv_id)

    def increment_auto_reply(self, merchant_id: str) -> int:
        if not merchant_id:
            merchant_id = "default"
        count = self.merchant_auto_replies.get(merchant_id, 0) + 1
        self.merchant_auto_replies[merchant_id] = count
        return count

    def get_auto_reply_count(self, merchant_id: str) -> int:
        return self.merchant_auto_replies.get(merchant_id, 0)

    def reset_all(self):
        """Wipe state for teardown and testing."""
        self.contexts.clear()
        self.conversations.clear()
        self.merchant_auto_replies.clear()
        self.suppressions.clear()
        self.ended_conversations.clear()


# Global storage singleton
storage = BotStorage()
