import re


_TICKER_RE = re.compile(r"[^A-Za-z0-9.\-]")


def get_tool_definitions(chat_message=None):
    """Return plugin-contributed tool definitions.

    This is a lightweight example used to validate dynamic registration wiring.
    """
    return [
        {
            "type": "function",
            "function": {
                "name": "normalize_ticker",
                "description": "Normalize a stock ticker to canonical uppercase format.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ticker": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 40,
                            "description": "Ticker or symbol-like input",
                        }
                    },
                    "required": ["ticker"],
                },
            },
        }
    ]


def handle_normalize_ticker(chat_message, args, portfolio_doc=None, security_doc=None):
    value = str((args or {}).get("ticker") or "").strip()
    if not value:
        raise ValueError("ticker is required")

    cleaned = _TICKER_RE.sub("", value).upper()
    return {
        "input": value,
        "normalized": cleaned,
        "changed": cleaned != value,
    }