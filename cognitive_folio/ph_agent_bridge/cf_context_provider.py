"""CFChatContextProvider — injects Cognitive Folio context into ph_agent sessions.

When a Chat Session has ``reference_doctype`` set to ``"CF Portfolio"`` or
``"CF Security"``, this provider loads the referenced document and injects
enriched context (portfolio holdings, security details, etc.) as system
instructions before each agent turn.

Registered via the ``ph_agent_context_providers`` hook in hooks.py.
"""

from __future__ import annotations

import logging
from typing import Any

import frappe
from agent_framework import ContextProvider

logger = logging.getLogger(__name__)

# DocTypes this provider supports
SUPPORTED_DOCTYPES = {"CF Portfolio", "CF Security"}

# Maximum length of a single context block to avoid token overflow
_MAX_CONTEXT_LENGTH = 4000


class CFChatContextProvider(ContextProvider):
    """ContextProvider that injects Cognitive Folio document context.

    On ``before_run()``, checks if the session has a ``reference_doctype``
    matching a supported CF doctype. If so, loads the referenced document
    and builds enriched context text that is injected as system instructions.

    The provider is instantiated by ph_agent's framework_agent with the
    ``session_doc`` keyword argument.
    """

    def __init__(self, session_doc: frappe._dict | None = None) -> None:
        super().__init__("cognitive_folio_context")
        self._session_doc = session_doc

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def before_run(
        self,
        *,
        agent: Any,
        session: Any,
        context: Any,
        state: dict[str, Any],
    ) -> None:
        """Load referenced document context and inject as instructions.

        Only activates when the session's ``reference_doctype`` is one of
        ``SUPPORTED_DOCTYPES``.
        """
        session_doc = self._resolve_session_doc(session)
        if not session_doc:
            return

        ref_doctype = session_doc.get("reference_doctype")
        ref_name = session_doc.get("reference_name")

        if not ref_doctype or not ref_name:
            return

        if ref_doctype not in SUPPORTED_DOCTYPES:
            return

        try:
            context_text = self._build_context(ref_doctype, ref_name)
            if context_text:
                context.extend_instructions(self.source_id, context_text)
                state["cf_context_doctype"] = ref_doctype
                state["cf_context_name"] = ref_name
        except Exception:
            logger.exception(
                "CFChatContextProvider: failed to build context for %s %s",
                ref_doctype,
                ref_name,
            )

    async def after_run(
        self,
        *,
        agent: Any,
        session: Any,
        context: Any,
        state: dict[str, Any],
    ) -> None:
        """No post-processing needed for CF context."""
        pass

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_session_doc(self, session: Any) -> frappe._dict | None:
        """Resolve the Chat Session document.

        Uses the ``session_doc`` passed at construction (hook-registered
        providers receive it), falling back to a DB lookup from the
        session ID.
        """
        if self._session_doc is not None:
            return self._session_doc

        session_id = getattr(session, "session_id", None)
        if not session_id:
            return None
        try:
            return frappe.get_doc("Chat Session", session_id)
        except Exception:
            return None

    def _build_context(self, ref_doctype: str, ref_name: str) -> str | None:
        """Build enriched context text for the referenced document."""
        if ref_doctype == "CF Portfolio":
            return self._build_portfolio_context(ref_name)
        elif ref_doctype == "CF Security":
            return self._build_security_context(ref_name)
        return None

    # ------------------------------------------------------------------
    # Portfolio context
    # ------------------------------------------------------------------

    def _build_portfolio_context(self, portfolio_name: str) -> str | None:
        """Build static identity context for a CF Portfolio.

        Only injects static/identity data that doesn't change.
        Dynamic data (holdings, prices, performance, etc.) must be
        fetched on-demand via the ``cf_query`` tool.
        """
        try:
            doc = frappe.get_doc("CF Portfolio", portfolio_name)
        except frappe.DoesNotExistError:
            logger.warning("CFChatContextProvider: portfolio %s not found", portfolio_name)
            return None

        lines = [
            "## Current Portfolio Context",
            f"- **Name**: {doc.name}",
            f"- **Portfolio**: {doc.portfolio_name}",
            f"- **Currency**: {doc.currency or 'N/A'}",
            f"- **Risk Profile**: {doc.risk_profile or 'N/A'}",
        ]

        if doc.start_date:
            lines.append(f"- **Start Date**: {doc.start_date}")
        if doc.description:
            lines.append(f"- **Description**: {doc.description}")

        context_text = "\n".join(lines)

        if len(context_text) > _MAX_CONTEXT_LENGTH:
            context_text = context_text[:_MAX_CONTEXT_LENGTH] + "\n\n*(Context truncated due to length)*"

        return context_text

    # ------------------------------------------------------------------
    # Security context
    # ------------------------------------------------------------------

    def _build_security_context(self, security_name: str) -> str | None:
        """Build static identity context for a CF Security.

        Only injects static/identity data that doesn't change.
        Dynamic data (current price, suggestions, ratings, EPS,
        parent portfolios, etc.) must be fetched on-demand via
        the ``cf_query`` tool.
        """
        try:
            doc = frappe.get_doc("CF Security", security_name)
        except frappe.DoesNotExistError:
            logger.warning("CFChatContextProvider: security %s not found", security_name)
            return None

        lines = [
            "## Current Security Context",
            f"- **Name**: {doc.name}",
            f"- **Security Name**: {doc.security_name}",
            f"- **Symbol**: {doc.symbol or 'N/A'}",
        ]

        if doc.isin:
            lines.append(f"- **ISIN**: {doc.isin}")
        if doc.security_type:
            lines.append(f"- **Type**: {doc.security_type}")
        if doc.country:
            lines.append(f"- **Country**: {doc.country}")
        if doc.sector:
            lines.append(f"- **Sector**: {doc.sector}")
        if doc.industry:
            lines.append(f"- **Industry**: {doc.industry}")

        context_text = "\n".join(lines)

        if len(context_text) > _MAX_CONTEXT_LENGTH:
            context_text = context_text[:_MAX_CONTEXT_LENGTH] + "\n\n*(Context truncated due to length)*"

        return context_text

    # ------------------------------------------------------------------
    # Formatting helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _fmt_currency(value: float | None, currency: str | None = None) -> str:
        """Format a currency value with optional currency symbol."""
        if value is None:
            return "N/A"
        symbol = currency or ""
        if symbol:
            return f"{symbol} {value:,.2f}"
        return f"{value:,.2f}"
