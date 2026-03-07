import json
import re

import frappe

from .embedding_provider import EmbeddingProvider


class VectorMemory:
    """Vector memory using deterministic embeddings with contextual scope boosts."""

    _CACHE_KEY_PREFIX = "cf:vector_memory:"
    _DOCTYPE_NAME = "CF Vector Memory"

    def __init__(self, embedding_provider=None):
        self.embedding_provider = embedding_provider or EmbeddingProvider()

    def get_context(self, chat_name, current_prompt, config, context=None):
        if not chat_name:
            return ""

        context = context or {}
        if not bool((config or {}).get("vector_enabled", True)):
            return ""

        max_items = int((config or {}).get("vector_max_items", 3) or 3)
        max_chars = int((config or {}).get("vector_max_chars", 700) or 700)
        dims = int((config or {}).get("vector_embedding_dims", 96) or 96)

        entries = self._load_entries(chat_name)
        if not entries and bool((config or {}).get("vector_persist_enabled", False)):
            entries = self._load_recent_entries_from_store(chat_name, limit=max_items * 4)
        if not entries:
            entries = self._load_recent_entries_from_db(chat_name, limit=max_items * 4)

        if not entries:
            return ""

        selected = self._rank(
            entries,
            current_prompt=current_prompt,
            context=context,
            max_items=max_items,
            config=config,
            dims=dims,
        )
        lines = []
        for item in selected:
            text = (item or {}).get("text") or ""
            if not text:
                continue

            facts = (item or {}).get("facts") or []
            portfolio = (item or {}).get("portfolio")
            security = (item or {}).get("security")

            if security and portfolio:
                lines.append(f"- [{portfolio} | {security}] {text}")
            elif security:
                lines.append(f"- [{security}] {text}")
            elif portfolio:
                lines.append(f"- [{portfolio}] {text}")
            else:
                lines.append(f"- {text}")

            if facts:
                lines.append(f"  Facts: {'; '.join(facts[:2])}")

        output = "\n".join(lines).strip()
        if len(output) > max_chars:
            output = output[-max_chars:]
        return output

    def record_turn(self, chat_name, prompt, response, config, metadata=None, context=None):
        if not chat_name:
            return {"stored": False, "reason": "missing_chat"}

        if not bool((config or {}).get("vector_enabled", True)):
            return {"stored": False, "reason": "vector_disabled"}

        context = context or {}
        metadata = metadata or {}

        prompt = (prompt or "").strip()
        response = (response or "").strip()
        combined = self._compact(f"{prompt} {response}".strip(), 480)
        if not combined:
            return {"stored": False, "reason": "empty_turn"}

        max_cache_items = int((config or {}).get("vector_cache_items", 60) or 60)
        dims = int((config or {}).get("vector_embedding_dims", 96) or 96)
        vector = self.embedding_provider.embed_text(combined, dims=dims)
        entry = {
            "text": combined,
            "facts": list(metadata.get("facts") or [])[:4],
            "tags": list(metadata.get("tags") or [])[:6],
            "portfolio": context.get("portfolio"),
            "security": context.get("security"),
            "embedding": vector,
        }

        entries = self._load_entries(chat_name)
        entries.append(entry)
        entries = entries[-max_cache_items:]
        self._save_entries(chat_name, entries)

        persistence = self._persist_entry(chat_name=chat_name, entry=entry, context=context, config=config)
        return {
            "stored": True,
            "items": len(entries),
            "persistence": persistence,
        }

    def prune_persistent_store(self, config=None, chat_names=None):
        config = config or {}
        if not bool((config or {}).get("vector_persist_enabled", False)):
            return {"pruned": False, "reason": "persist_disabled", "deleted": 0, "chats": 0}

        if not self._doctype_available():
            return {"pruned": False, "reason": "doctype_missing", "deleted": 0, "chats": 0}

        if chat_names is None:
            chat_rows = frappe.get_all(
                self._DOCTYPE_NAME,
                filters={"chat": ("!=", "")},
                fields=["chat"],
                group_by="chat",
                limit_page_length=5000,
            )
            chat_names = [
                (row or {}).get("chat")
                for row in (chat_rows or [])
                if (row or {}).get("chat")
            ]

        total_deleted = 0
        total_chats = 0
        for chat_name in chat_names or []:
            if not chat_name:
                continue
            total_chats += 1
            result = self._prune_store(chat_name=str(chat_name), config=config)
            total_deleted += int((result or {}).get("deleted", 0) or 0)

        return {
            "pruned": True,
            "deleted": total_deleted,
            "chats": total_chats,
        }

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
            frappe.log_error(title="VectorMemory cache write error", message=frappe.get_traceback())

    def _persist_entry(self, chat_name, entry, context, config):
        if not bool((config or {}).get("vector_persist_enabled", False)):
            return {"persisted": False, "reason": "persist_disabled"}

        if not self._doctype_available():
            return {"persisted": False, "reason": "doctype_missing"}

        try:
            doc = frappe.get_doc(
                {
                    "doctype": self._DOCTYPE_NAME,
                    "chat": chat_name,
                    "portfolio": (context or {}).get("portfolio"),
                    "security": (context or {}).get("security"),
                    "memory_text": (entry or {}).get("text") or "",
                    "facts_json": json.dumps((entry or {}).get("facts") or [], ensure_ascii=False, default=str),
                    "tags_json": json.dumps((entry or {}).get("tags") or [], ensure_ascii=False, default=str),
                    "embedding_json": json.dumps((entry or {}).get("embedding") or [], ensure_ascii=False, default=str),
                }
            )
            doc.insert(ignore_permissions=True)
            prune_result = self._prune_store(chat_name=chat_name, config=config)
            return {"persisted": True, "name": getattr(doc, "name", None), "prune": prune_result}
        except Exception:
            try:
                frappe.log_error(title="VectorMemory persist error", message=frappe.get_traceback())
            except Exception:
                pass
            return {"persisted": False, "reason": "persist_failed"}

    def _prune_store(self, chat_name, config):
        if not bool((config or {}).get("vector_persist_enabled", False)):
            return {"deleted": 0, "reason": "persist_disabled"}

        if not self._doctype_available():
            return {"deleted": 0, "reason": "doctype_missing"}

        deleted = 0
        deleted_names = set()

        # Retain only the most recent N rows per chat to keep storage bounded.
        max_records = int((config or {}).get("vector_store_max_records_per_chat", 300) or 300)
        if max_records > 0:
            try:
                overflow_rows = frappe.get_all(
                    self._DOCTYPE_NAME,
                    filters={"chat": chat_name},
                    fields=["name"],
                    order_by="creation desc",
                    limit_start=max_records,
                    limit_page_length=max_records,
                )
                for row in overflow_rows or []:
                    name = (row or {}).get("name")
                    if name and name not in deleted_names and self._delete_doc_name(name):
                        deleted += 1
                        deleted_names.add(name)
            except Exception:
                pass

        # Remove rows older than retention window.
        max_age_days = int((config or {}).get("vector_store_max_age_days", 180) or 180)
        if max_age_days > 0:
            try:
                cutoff_date = frappe.utils.add_days(frappe.utils.nowdate(), -max_age_days)
                old_rows = frappe.get_all(
                    self._DOCTYPE_NAME,
                    filters={"chat": chat_name, "creation": ("<", f"{cutoff_date} 00:00:00")},
                    fields=["name"],
                    limit_page_length=1000,
                )
                for row in old_rows or []:
                    name = (row or {}).get("name")
                    if name and name not in deleted_names and self._delete_doc_name(name):
                        deleted += 1
                        deleted_names.add(name)
            except Exception:
                pass

        return {"deleted": deleted}

    def _load_recent_entries_from_store(self, chat_name, limit=12):
        if not self._doctype_available():
            return []

        try:
            rows = frappe.get_all(
                self._DOCTYPE_NAME,
                filters={"chat": chat_name},
                fields=["memory_text", "facts_json", "tags_json", "embedding_json", "portfolio", "security"],
                order_by="creation desc",
                limit_page_length=limit,
            )
        except Exception:
            return []

        entries = []
        for row in rows or []:
            entries.append(
                {
                    "text": self._compact((row or {}).get("memory_text") or "", 480),
                    "facts": self._load_json_list((row or {}).get("facts_json")),
                    "tags": self._load_json_list((row or {}).get("tags_json")),
                    "embedding": self._load_json_list((row or {}).get("embedding_json")),
                    "portfolio": (row or {}).get("portfolio"),
                    "security": (row or {}).get("security"),
                }
            )
        return entries

    def _load_recent_entries_from_db(self, chat_name, limit=12):
        try:
            rows = frappe.get_all(
                "CF Chat Message",
                filters={"chat": chat_name, "status": "Success"},
                fields=["prompt", "response", "portfolio", "security"],
                order_by="creation desc",
                limit_page_length=limit,
            )
        except Exception:
            # Backward-compatible fallback for sites where CF Chat Message lacks
            # portfolio/security columns.
            rows = frappe.get_all(
                "CF Chat Message",
                filters={"chat": chat_name, "status": "Success"},
                fields=["prompt", "response"],
                order_by="creation desc",
                limit_page_length=limit,
            )

        entries = []
        for row in rows or []:
            entries.append(
                {
                    "text": self._compact(f"{(row or {}).get('prompt') or ''} {(row or {}).get('response') or ''}".strip(), 480),
                    "facts": [],
                    "tags": [],
                    "portfolio": (row or {}).get("portfolio"),
                    "security": (row or {}).get("security"),
                }
            )
        return entries

    def _rank(self, entries, current_prompt, context, max_items, config=None, dims=96):
        config = config or {}
        similarity_mode = str(config.get("vector_similarity_mode") or "embedding").strip().lower()
        use_embeddings = similarity_mode == "embedding"
        query_embedding = self.embedding_provider.embed_text(current_prompt, dims=dims) if use_embeddings else []
        prompt_terms = self._terms(current_prompt)
        portfolio_ctx = str((context or {}).get("portfolio") or "").strip()
        security_ctx = str((context or {}).get("security") or "").strip()

        scored = []
        for item in entries:
            text_blob = " ".join(
                [
                    str((item or {}).get("text") or ""),
                    " ".join((item or {}).get("facts") or []),
                    " ".join((item or {}).get("tags") or []),
                ]
            )
            similarity = 0.0
            if use_embeddings:
                item_embedding = (item or {}).get("embedding")
                if not isinstance(item_embedding, list) or not item_embedding:
                    item_embedding = self.embedding_provider.embed_text(text_blob, dims=dims)
                similarity = self.embedding_provider.cosine_similarity(query_embedding, item_embedding)
            else:
                terms = self._terms(text_blob)
                similarity = float(len(prompt_terms.intersection(terms)) if prompt_terms else 0)

            ctx_bonus = 0
            if portfolio_ctx and str((item or {}).get("portfolio") or "") == portfolio_ctx:
                ctx_bonus += 3
            if security_ctx and str((item or {}).get("security") or "") == security_ctx:
                ctx_bonus += 4

            scored.append((float(ctx_bonus) + float(similarity), item))

        ordered = [item for _, item in sorted(scored, key=lambda pair: pair[0], reverse=True)]
        return ordered[:max_items]

    def _terms(self, text):
        cleaned = re.sub(r"[^a-zA-Z0-9. ]", " ", str(text or "").lower())
        return {token for token in cleaned.split() if len(token) >= 3}

    def _compact(self, text, max_len):
        cleaned = " ".join(str(text or "").split())
        if len(cleaned) <= max_len:
            return cleaned
        return cleaned[: max_len - 3] + "..."

    def _doctype_available(self):
        try:
            return bool(frappe.db.exists("DocType", self._DOCTYPE_NAME))
        except Exception:
            return False

    def _load_json_list(self, raw):
        if isinstance(raw, list):
            return raw
        if raw in (None, ""):
            return []
        try:
            loaded = json.loads(raw)
            return loaded if isinstance(loaded, list) else []
        except Exception:
            return []

    def _delete_doc_name(self, name):
        try:
            frappe.delete_doc(self._DOCTYPE_NAME, name, ignore_permissions=True, force=1)
            return True
        except Exception:
            return False
