import json
import re

import frappe


class ConversationMemory:
    """Lightweight chat memory using cache with DB fallback."""

    _CACHE_KEY_PREFIX = "cf:conversation_memory:"
    _TICKER_RE = re.compile(r"\b[A-Z]{1,5}(?:\.[A-Z]{1,3})?\b")

    def get_context(self, chat_name, config, current_prompt=""):
        if not chat_name:
            return ""

        max_items = int((config or {}).get("max_items", 6) or 6)
        max_chars = int((config or {}).get("max_chars", 1200) or 1200)
        max_relevant_items = int((config or {}).get("max_relevant_items", 3) or 3)

        entries = self._load_entries(chat_name)
        if not entries:
            entries = self._load_recent_entries_from_db(chat_name, max_items=max_items)

        if not entries:
            return ""

        entries = self._select_entries(entries, current_prompt=current_prompt, max_items=max_items, max_relevant_items=max_relevant_items)

        lines = []
        for item in list(entries)[-max_items:]:
            if not isinstance(item, dict):
                continue

            user_text = (item.get("user") or "").strip()
            assistant_text = (item.get("assistant") or "").strip()
            tags = item.get("tags") or []
            facts = item.get("facts") or []

            if not user_text and not assistant_text:
                continue

            if user_text:
                lines.append(f"- User: {user_text}")
            if assistant_text:
                lines.append(f"  Assistant: {assistant_text}")
            if tags:
                lines.append(f"  Tags: {', '.join(tags)}")
            if facts:
                lines.append(f"  Facts: {'; '.join(facts[:3])}")

        context = "\n".join(lines).strip()
        if not context:
            return ""

        if len(context) > max_chars:
            context = context[-max_chars:]

        return context

    def record_turn(self, chat_name, prompt, response, config, metadata=None):
        if not chat_name:
            return {"stored": False, "reason": "missing_chat"}

        prompt = (prompt or "").strip()
        response = (response or "").strip()
        if not prompt and not response:
            return {"stored": False, "reason": "empty_turn"}

        max_cache_items = int((config or {}).get("cache_items", 30) or 30)
        item = {
            "user": self._compact(prompt, 240),
            "assistant": self._compact(response, 320),
            "tags": self._extract_tags(f"{prompt} {response}"),
            "facts": list((metadata or {}).get("facts") or [])[:5],
        }

        entries = self._load_entries(chat_name)
        entries.append(item)
        entries = entries[-max_cache_items:]
        self._save_entries(chat_name, entries)
        return {"stored": True, "items": len(entries)}

    def _cache_key(self, chat_name):
        return f"{self._CACHE_KEY_PREFIX}{chat_name}"

    def _load_entries(self, chat_name):
        key = self._cache_key(chat_name)
        try:
            raw = frappe.cache().get_value(key)
            if not raw:
                return []
            if isinstance(raw, (bytes, bytearray)):
                raw = raw.decode("utf-8", errors="ignore")
            loaded = json.loads(raw)
            return loaded if isinstance(loaded, list) else []
        except Exception:
            return []

    def _save_entries(self, chat_name, entries):
        key = self._cache_key(chat_name)
        try:
            frappe.cache().set_value(key, json.dumps(entries, ensure_ascii=False, default=str))
        except Exception:
            frappe.log_error(title="ConversationMemory cache write error", message=frappe.get_traceback())

    def _load_recent_entries_from_db(self, chat_name, max_items):
        rows = frappe.get_all(
            "CF Chat Message",
            filters={"chat": chat_name, "status": "Success"},
            fields=["prompt", "response"],
            order_by="creation desc",
            limit_page_length=max_items,
        )

        entries = []
        for row in reversed(rows or []):
            entries.append(
                {
                    "user": self._compact((row or {}).get("prompt"), 240),
                    "assistant": self._compact((row or {}).get("response"), 320),
                    "tags": self._extract_tags(f"{(row or {}).get('prompt') or ''} {(row or {}).get('response') or ''}"),
                }
            )
        return entries

    def _compact(self, text, max_len):
        cleaned = " ".join(str(text or "").split())
        if len(cleaned) <= max_len:
            return cleaned
        return cleaned[: max_len - 3] + "..."

    def _extract_tags(self, text):
        tags = []
        for value in self._TICKER_RE.findall(text or ""):
            if value in {"AND", "THE", "FOR", "WITH"}:
                continue
            if value not in tags:
                tags.append(value)
            if len(tags) >= 5:
                break
        return tags

    def _select_entries(self, entries, current_prompt, max_items, max_relevant_items):
        if not entries:
            return []

        recents = list(entries)[-max_items:]
        prompt_terms = self._terms(current_prompt)
        if not prompt_terms:
            return recents

        scored = []
        for item in entries:
            item_terms = self._terms(" ".join([
                str((item or {}).get("user") or ""),
                str((item or {}).get("assistant") or ""),
                " ".join((item or {}).get("tags") or []),
                " ".join((item or {}).get("facts") or []),
            ]))
            score = len(prompt_terms.intersection(item_terms))
            scored.append((score, item))

        relevant = [item for score, item in sorted(scored, key=lambda x: x[0], reverse=True) if score > 0][:max_relevant_items]

        selected = []
        for item in recents + relevant:
            if item not in selected:
                selected.append(item)

        return selected[-max_items:]

    def _terms(self, text):
        cleaned = re.sub(r"[^a-zA-Z0-9. ]", " ", str(text or "").lower())
        terms = {part for part in cleaned.split() if len(part) >= 3}
        return terms
