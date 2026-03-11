import frappe
import json
import time
from typing import Dict, List, Optional, Any
import re

# Import yfinance if available
try:
    import yfinance as yf
    YFINANCE_INSTALLED = True
except ImportError:
    YFINANCE_INSTALLED = False


def get_tool_definitions(chat_message=None):
    """Return plugin-contributed tool definitions for securities discovery."""
    return [
        {
            "type": "function",
            "function": {
                "name": "discover_securities",
                "description": "Discover securities (stocks) matching specific financial criteria using Yahoo Finance.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "sector": {
                            "type": "string",
                            "description": "Sector to filter by (e.g., 'Technology', 'Healthcare', 'Financial Services')"
                        },
                        "market_cap_min": {
                            "type": "number",
                            "description": "Minimum market capitalization in USD (e.g., 1000000000 for $1B)"
                        },
                        "market_cap_max": {
                            "type": "number",
                            "description": "Maximum market capitalization in USD (e.g., 100000000000 for $100B)"
                        },
                        "pe_min": {
                            "type": "number",
                            "description": "Minimum price-to-earnings (P/E) ratio"
                        },
                        "pe_max": {
                            "type": "number",
                            "description": "Maximum price-to-earnings (P/E) ratio"
                        },
                        "dividend_yield_min": {
                            "type": "number",
                            "description": "Minimum dividend yield percentage (e.g., 2.5 for 2.5%)"
                        },
                        "dividend_yield_max": {
                            "type": "number",
                            "description": "Maximum dividend yield percentage"
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of securities to return (default: 10)",
                            "default": 10
                        }
                    },
                    "required": []
                }
            }
        }
    ]


def handle_discover_securities(chat_message, args, portfolio_doc=None, security_doc=None):
    """Handle discover_securities tool call - simplified version."""
    if not YFINANCE_INSTALLED:
        raise ValueError("yfinance is not installed. Please install it to use securities discovery.")
    
    # Extract parameters
    sector = args.get("sector")
    market_cap_min = args.get("market_cap_min")
    market_cap_max = args.get("market_cap_max")
    pe_min = args.get("pe_min")
    pe_max = args.get("pe_max")
    dividend_yield_min = args.get("dividend_yield_min")
    dividend_yield_max = args.get("dividend_yield_max")
    max_results = args.get("max_results", 10)
    
    # Get some popular tickers based on sector
    if sector and sector.lower() == "technology":
        tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "INTC", "AMD", "CSCO"]
    elif sector and sector.lower() == "healthcare":
        tickers = ["JNJ", "PFE", "MRK", "ABT", "TMO", "UNH", "LLY", "AMGN", "GILD", "BMY"]
    elif sector and sector.lower() == "financial":
        tickers = ["JPM", "BAC", "WFC", "C", "GS", "MS", "BLK", "SCHW", "AXP", "V"]
    else:
        # Mixed sectors
        tickers = ["AAPL", "MSFT", "JNJ", "JPM", "V", "WMT", "PG", "XOM", "CVX", "DIS"]
    
    # Limit to max_results
    tickers = tickers[:max_results]
    
    securities = []
    
    for symbol in tickers:
        try:
            # Fetch ticker data
            ticker = yf.Ticker(symbol)
            info = ticker.get_info()
            
            # Extract key metrics
            market_cap = info.get("marketCap")
            trailing_pe = info.get("trailingPE")
            dividend_yield = info.get("dividendYield")
            current_price = info.get("regularMarketPrice")
            
            # Apply filters if specified
            if market_cap_min and market_cap and market_cap < market_cap_min:
                continue
            if market_cap_max and market_cap and market_cap > market_cap_max:
                continue
            if pe_min and trailing_pe and trailing_pe < pe_min:
                continue
            if pe_max and trailing_pe and trailing_pe > pe_max:
                continue
            if dividend_yield:
                dividend_yield_percent = dividend_yield * 100
                if dividend_yield_min and dividend_yield_percent < dividend_yield_min:
                    continue
                if dividend_yield_max and dividend_yield_percent > dividend_yield_max:
                    continue
            
            # Get company name
            name = info.get("longName") or info.get("shortName") or symbol
            
            # Get sector if available
            ticker_sector = info.get("sector") or sector or "Unknown"
            
            # Create security object
            security = {
                "symbol": symbol,
                "name": name,
                "sector": ticker_sector,
                "current_price": current_price,
                "market_cap": market_cap,
                "pe_ratio": trailing_pe,
                "dividend_yield": dividend_yield_percent if dividend_yield else None,
                "currency": info.get("currency", "USD"),
                "exchange": info.get("exchange", "Unknown"),
                "data_source": "yfinance",
                "note": "This is a simplified demonstration. Full implementation would include screening API."
            }
            
            securities.append(security)
            
            # Small delay to avoid rate limiting
            time.sleep(0.2)
            
        except Exception as e:
            frappe.log_error(f"Error fetching data for {symbol}: {str(e)}", "Discovery Tools Simple")
            continue
    
    if not securities:
        return {
            "message": "No securities found matching the criteria with the simplified implementation.",
            "securities": [],
            "suggestion": "Try with fewer or broader criteria, or check if yfinance is working properly."
        }
    
    return {
        "message": f"Found {len(securities)} securities matching criteria (simplified implementation)",
        "securities": securities,
        "total_checked": len(tickers),
        "criteria_used": {
            "sector": sector or "Mixed",
            "market_cap_range": f"{market_cap_min or 'Any'} to {market_cap_max or 'Any'}",
            "pe_range": f"{pe_min or 'Any'} to {pe_max or 'Any'}",
            "dividend_yield_range": f"{dividend_yield_min or 'Any'}% to {dividend_yield_max or 'Any'}%",
            "max_results": max_results
        },
        "implementation_note": "This uses a simplified approach with predefined tickers. The full implementation would use Yahoo Finance screening API for dynamic discovery."
    }