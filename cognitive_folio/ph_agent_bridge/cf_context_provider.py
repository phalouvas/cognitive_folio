"""CFChatContextProvider — injects Cognitive Folio context into ph_agent sessions.

When a Chat Session has ``reference_doctype`` set to ``"CF Portfolio"`` or
``"CF Security"``, this provider loads the referenced document and injects
enriched context (portfolio holdings, security details, etc.) as system
instructions before each agent turn.

Registered via the ``ph_agent_context_providers`` hook in hooks.py.
"""

from __future__ import annotations

import json
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
        """Build enriched context for a CF Portfolio."""
        try:
            doc = frappe.get_doc("CF Portfolio", portfolio_name)
        except frappe.DoesNotExistError:
            logger.warning("CFChatContextProvider: portfolio %s not found", portfolio_name)
            return None

        lines = [
            "## Current Portfolio Context",
            f"- **Portfolio**: {doc.portfolio_name}",
            f"- **Currency**: {doc.currency or 'N/A'}",
            f"- **Risk Profile**: {doc.risk_profile or 'N/A'}",
            f"- **Current Value**: {self._fmt_currency(doc.current_value, doc.currency)}",
            f"- **Cost Basis**: {self._fmt_currency(doc.cost, doc.currency)}",
        ]

        # Performance
        if doc.returns_percentage_total is not None:
            lines.append(
                f"- **Total Return**: {self._fmt_currency(doc.returns_total, doc.currency)} "
                f"({doc.returns_percentage_total:+.2f}%)"
            )

        # Holdings summary
        holdings = frappe.get_all(
            "CF Portfolio Holding",
            filters={"portfolio": portfolio_name},
            fields=[
                "security", "quantity", "current_value", "allocation_percentage",
                "profit_loss_percentage", "sector", "suggestion_action",
                "suggestion_rating",
            ],
            order_by="allocation_percentage desc",
            limit_page_length=20,
        )

        if holdings:
            lines.append("")
            lines.append("### Holdings")
            lines.append("| Security | Qty | Value | Allocation | P/L % | Action | Rating |")
            lines.append("|----------|-----|-------|------------|-------|--------|--------|")
            for h in holdings:
                alloc = f"{h.allocation_percentage:.1f}%" if h.allocation_percentage is not None else "N/A"
                pl = f"{h.profit_loss_percentage:+.2f}%" if h.profit_loss_percentage is not None else "N/A"
                val = self._fmt_currency(h.current_value, doc.currency)
                action = h.suggestion_action or "-"
                rating = f"{'★' * int(h.suggestion_rating or 0)}" if h.suggestion_rating else "-"
                lines.append(
                    f"| {h.security} | {h.quantity or 0:.2f} | {val} | {alloc} | {pl} | {action} | {rating} |"
                )

        # Sector allocations
        if doc.sector_allocations:
            try:
                sectors = json.loads(doc.sector_allocations) if isinstance(doc.sector_allocations, str) else doc.sector_allocations
                if sectors:
                    lines.append("")
                    lines.append("### Sector Allocation")
                    for s in sorted(sectors.items(), key=lambda x: x[1], reverse=True)[:10]:
                        lines.append(f"- **{s[0]}**: {s[1]:.1f}%")
            except (json.JSONDecodeError, TypeError, AttributeError):
                pass

        context_text = "\n".join(lines)

        if len(context_text) > _MAX_CONTEXT_LENGTH:
            context_text = context_text[:_MAX_CONTEXT_LENGTH] + "\n\n*(Context truncated due to length)*"

        return context_text

    # ------------------------------------------------------------------
    # Security context
    # ------------------------------------------------------------------

    def _build_security_context(self, security_name: str) -> str | None:
        """Build enriched context for a CF Security.

        Also loads the parent portfolio context if the security is held
        in any portfolio.
        """
        try:
            doc = frappe.get_doc("CF Security", security_name)
        except frappe.DoesNotExistError:
            logger.warning("CFChatContextProvider: security %s not found", security_name)
            return None

        lines = [
            "## Current Security Context",
            f"- **Name**: {doc.security_name}",
            f"- **Symbol**: {doc.symbol or 'N/A'}",
            f"- **Type**: {doc.security_type or 'N/A'}",
            f"- **Currency**: {doc.currency or 'N/A'}",
            f"- **Current Price**: {self._fmt_currency(doc.current_price, doc.currency)}",
        ]

        # Suggestion / rating
        if doc.suggestion_action:
            lines.append(f"- **Suggestion**: {doc.suggestion_action}")
        if doc.suggestion_rating:
            lines.append(f"- **Rating**: {'★' * int(doc.suggestion_rating)}/{5}")
        if doc.suggestion_buy_price:
            lines.append(f"- **Buy Price Target**: {self._fmt_currency(doc.suggestion_buy_price, doc.currency)}")
        if doc.suggestion_sell_price:
            lines.append(f"- **Sell Price Target**: {self._fmt_currency(doc.suggestion_sell_price, doc.currency)}")
        if doc.suggestion_fair_value:
            lines.append(f"- **Fair Value**: {self._fmt_currency(doc.suggestion_fair_value, doc.currency)}")
        if doc.evaluation_stop_loss:
            lines.append(f"- **Stop Loss**: {self._fmt_currency(doc.evaluation_stop_loss, doc.currency)}")

        # Sector / industry
        if doc.sector:
            lines.append(f"- **Sector**: {doc.sector}")
        if doc.industry:
            lines.append(f"- **Industry**: {doc.industry}")

        # Earnings
        if doc.trailing_eps:
            lines.append(f"- **Trailing EPS**: {self._fmt_currency(doc.trailing_eps, doc.currency)}")
        if doc.forward_eps:
            lines.append(f"- **Forward EPS**: {self._fmt_currency(doc.forward_eps, doc.currency)}")

        # Find parent portfolios
        portfolios = frappe.get_all(
            "CF Portfolio Holding",
            filters={"security": security_name},
            fields=["portfolio", "allocation_percentage", "current_value", "quantity"],
            limit_page_length=10,
        )

        if portfolios:
            lines.append("")
            lines.append("### Held In Portfolios")
            for p in portfolios:
                alloc = f"{p.allocation_percentage:.1f}%" if p.allocation_percentage is not None else "N/A"
                val = self._fmt_currency(p.current_value, doc.currency)
                lines.append(f"- **{p.portfolio}**: {p.quantity or 0:.2f} shares, {val} ({alloc})")

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
