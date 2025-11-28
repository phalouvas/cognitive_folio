import re
import frappe

TEMPLATES = [
    "/workspace/development/frappe-bench/apps/cognitive_folio/Comprehensive Security Evaluation.md",
    "/workspace/development/frappe-bench/apps/cognitive_folio/Quarterly Annual Update Analysis.md",
]

VAR_PATTERN = re.compile(r"\{\{\s*([^}]+?)\s*\}\}")


def _extract_placeholders(text: str) -> set:
    return set(VAR_PATTERN.findall(text))


def _load_templates() -> dict:
    templates = {}
    for path in TEMPLATES:
        try:
            with open(path, "r", encoding="utf-8") as f:
                templates[path] = f.read()
        except Exception:
            templates[path] = ""
    return templates


def _has_periods(doc) -> dict:
    annual = frappe.get_all(
        "CF Financial Period",
        filters={"security": doc.name, "period_type": "Annual"},
        fields=["name"],
        order_by="period_end desc",
    )
    quarterly = frappe.get_all(
        "CF Financial Period",
        filters={"security": doc.name, "period_type": "Quarterly"},
        fields=["name"],
        order_by="period_end desc",
    )
    return {"annual_count": len(annual), "quarterly_count": len(quarterly)}


def _resolve_simple(doc, key: str):
    # Supports keys like: field, ticker_info.key, news.ARRAY.content.title (only presence check)
    parts = key.split(".")
    if parts[0] in {"periods", "news"}:
        # Special blocks handled separately; here we only check availability
        return "__SPECIAL__"
    if len(parts) == 1:
        return getattr(doc, parts[0], None)
    if parts[0] == "ticker_info":
        info = getattr(doc, "ticker_info", None)
        if isinstance(info, dict):
            return info.get(parts[1])
        return None
    # Generic nested dict field support
    val = getattr(doc, parts[0], None)
    for p in parts[1:]:
        if isinstance(val, dict):
            val = val.get(p)
        else:
            return None
    return val


def audit_templates(security_names=None):
    """Return audit results of template variables per security.

    Output structure:
    {
        security_name: {
            "missing": { template_path: [variables...] },
            "periods": {"annual_count": n, "quarterly_count": m}
        },
        ...
    }
    """
    results = {}
    templates = _load_templates()
    placeholders_per_template = {
        path: _extract_placeholders(text) for path, text in templates.items()
    }

    if not security_names:
        security_names = [r.name for r in frappe.get_all("CF Security", fields=["name"])]

    for sec_name in security_names:
        doc = frappe.get_doc("CF Security", sec_name)
        period_counts = _has_periods(doc)
        sec_result = {"missing": {}, "periods": period_counts}

        for path, placeholders in placeholders_per_template.items():
            missing = []
            for ph in placeholders:
                # Handle special periods tags like periods:annual:5:markdown etc.
                if ph.startswith("periods:"):
                    try:
                        _, kind, count, *_ = ph.split(":")
                        count = int(count)
                        available = (
                            period_counts["annual_count"] if kind == "annual" else period_counts["quarterly_count"]
                        )
                        if available < count:
                            missing.append(f"{ph} (have {available})")
                    except Exception:
                        missing.append(ph)
                    continue

                # News array presence check
                if ph.startswith("news."):
                    news = getattr(doc, "news", None)
                    has_news = bool(news) and isinstance(news, list) and len(news) > 0
                    if not has_news:
                        missing.append(ph)
                    continue

                val = _resolve_simple(doc, ph)
                if val in (None, "", 0):
                    missing.append(ph)

            sec_result["missing"][path] = missing

        results[sec_name] = sec_result

    return results
