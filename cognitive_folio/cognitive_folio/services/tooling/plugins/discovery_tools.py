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

# We'll import modules lazily when needed to avoid import errors
CF_SECURITY_AVAILABLE = True  # Assume available, will check in handler


def get_tool_definitions(chat_message=None):
    """Return plugin-contributed tool definitions for securities discovery."""
    return [
        {
            "type": "function",
            "function": {
                "name": "discover_securities",
                "description": "Discover securities (stocks) matching specific financial criteria using Yahoo Finance screening and SEC EDGAR data.",
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
    """Handle discover_securities tool call."""
    if not YFINANCE_INSTALLED:
        raise ValueError("yfinance is not installed. Please install it to use securities discovery.")
    
    # Try to import required modules lazily
    try:
        from cognitive_folio.cognitive_folio.doctype.cf_security.cf_security import search_stock_symbols
        from cognitive_folio.cognitive_folio.utils.helper import get_edgar_data
        from cognitive_folio.cognitive_folio.services.performance.reliability import CircuitBreakerManager, RateLimiter
        from cognitive_folio.cognitive_folio.services.performance.search_caching import SearchResultCache
    except ImportError as e:
        frappe.log_error(f"Failed to import required modules for discover_securities: {str(e)}", "Discovery Tools")
        raise ValueError(f"Required CF Security modules are not available: {str(e)}")
    
    # Extract parameters
    sector = args.get("sector")
    market_cap_min = args.get("market_cap_min")
    market_cap_max = args.get("market_cap_max")
    pe_min = args.get("pe_min")
    pe_max = args.get("pe_max")
    dividend_yield_min = args.get("dividend_yield_min")
    dividend_yield_max = args.get("dividend_yield_max")
    max_results = args.get("max_results", 10)
    
    # Initialize rate limiter and circuit breaker
    rate_limiter = RateLimiter()
    circuit_breaker = CircuitBreakerManager()
    search_cache = SearchResultCache()
    
    # Create cache key
    cache_key = {
        "operation": "discover_securities",
        "sector": sector,
        "market_cap_min": market_cap_min,
        "market_cap_max": market_cap_max,
        "pe_min": pe_min,
        "pe_max": pe_max,
        "dividend_yield_min": dividend_yield_min,
        "dividend_yield_max": dividend_yield_max,
        "max_results": max_results
    }
    
    # Check cache first
    cached = search_cache.get("discover_securities", cache_key)
    if cached:
        return cached
    
    try:
        # Step 1: Get initial candidate symbols
        candidates = _get_initial_candidates(
            sector=sector,
            market_cap_min=market_cap_min,
            market_cap_max=market_cap_max,
            max_results=max_results * 3  # Get more candidates for filtering
        )
        
        if not candidates:
            return {
                "message": "No securities found matching the initial criteria.",
                "securities": [],
                "total_candidates": 0
            }
        
        # Step 2: Apply financial filters
        filtered_securities = _apply_financial_filters(
            candidates=candidates,
            pe_min=pe_min,
            pe_max=pe_max,
            dividend_yield_min=dividend_yield_min,
            dividend_yield_max=dividend_yield_max,
            market_cap_min=market_cap_min,
            market_cap_max=market_cap_max,
            max_results=max_results,
            rate_limiter=rate_limiter,
            circuit_breaker=circuit_breaker
        )
        
        # Step 3: Enrich with additional data
        enriched_securities = _enrich_securities_data(
            securities=filtered_securities,
            rate_limiter=rate_limiter,
            circuit_breaker=circuit_breaker
        )
        
        result = {
            "message": f"Found {len(enriched_securities)} securities matching criteria",
            "securities": enriched_securities,
            "total_candidates": len(candidates),
            "criteria_used": {
                "sector": sector,
                "market_cap_range": f"{market_cap_min or 'Any'} to {market_cap_max or 'Any'}",
                "pe_range": f"{pe_min or 'Any'} to {pe_max or 'Any'}",
                "dividend_yield_range": f"{dividend_yield_min or 'Any'}% to {dividend_yield_max or 'Any'}%"
            }
        }
        
        # Cache the result
        search_cache.set("discover_securities", cache_key, result)
        
        return result
        
    except Exception as e:
        frappe.log_error(f"Error in discover_securities: {str(e)}", "Discovery Tools Error")
        raise


def _get_initial_candidates(sector=None, market_cap_min=None, market_cap_max=None, max_results=30):
    """Get initial candidate symbols using Yahoo Finance search or screener."""
    candidates = []
    
    try:
        # Import here to avoid circular imports
        from cognitive_folio.cognitive_folio.doctype.cf_security.cf_security import search_stock_symbols
        
        # Try to use Yahoo Finance search with sector filter
        if sector:
            # Search for stocks in the sector
            search_terms = [sector]
        else:
            # Get popular stocks
            search_terms = ["technology", "healthcare", "financial", "consumer", "industrial"]
        
        for term in search_terms:
            if len(candidates) >= max_results:
                break
            
            try:
                # Use existing search_stock_symbols function
                results = search_stock_symbols(term)
                for result in results:
                    if len(candidates) >= max_results:
                        break
                    
                    # Filter by sector if specified
                    if sector and result.get("sector", "").lower() != sector.lower():
                        continue
                    
                    candidates.append({
                        "symbol": result.get("symbol"),
                        "name": result.get("name"),
                        "sector": result.get("sector"),
                        "industry": result.get("industry"),
                        "exchange": result.get("exchange")
                    })
            except Exception as e:
                frappe.log_error(f"Error searching for {term}: {str(e)}", "Discovery Tools")
                continue
        
        # If we have too few candidates, add some popular tickers
        if len(candidates) < 10:
            popular_tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META", "JPM", "JNJ", "V"]
            for ticker in popular_tickers:
                if len(candidates) >= max_results:
                    break
                candidates.append({
                    "symbol": ticker,
                    "name": "",  # Will be filled later
                    "sector": "",
                    "industry": "",
                    "exchange": ""
                })
        
    except Exception as e:
        frappe.log_error(f"Error getting initial candidates: {str(e)}", "Discovery Tools")
    
    return candidates[:max_results]


def _apply_financial_filters(candidates, pe_min=None, pe_max=None, dividend_yield_min=None,
                            dividend_yield_max=None, market_cap_min=None, market_cap_max=None,
                            max_results=10, rate_limiter=None, circuit_breaker=None):
    """Apply financial filters to candidates using Yahoo Finance data."""
    filtered = []
    
    for candidate in candidates:
        if len(filtered) >= max_results:
            break
        
        symbol = candidate.get("symbol")
        if not symbol:
            continue
        
        try:
            # Apply rate limiting
            if rate_limiter:
                rate_limiter.check_limit("yfinance", "discovery")
            
            # Fetch ticker data
            ticker = yf.Ticker(symbol)
            
            # Get info with timeout
            info = ticker.get_info()
            
            # Apply market cap filter
            market_cap = info.get("marketCap")
            if market_cap_min and market_cap and market_cap < market_cap_min:
                continue
            if market_cap_max and market_cap and market_cap > market_cap_max:
                continue
            
            # Apply P/E filter
            trailing_pe = info.get("trailingPE")
            if pe_min and trailing_pe and trailing_pe < pe_min:
                continue
            if pe_max and trailing_pe and trailing_pe > pe_max:
                continue
            
            # Apply dividend yield filter
            dividend_yield = info.get("dividendYield")
            if dividend_yield:
                dividend_yield_percent = dividend_yield * 100
                if dividend_yield_min and dividend_yield_percent < dividend_yield_min:
                    continue
                if dividend_yield_max and dividend_yield_percent > dividend_yield_max:
                    continue
            
            # Add to filtered list with financial data
            candidate.update({
                "current_price": info.get("regularMarketPrice"),
                "market_cap": market_cap,
                "pe_ratio": trailing_pe,
                "dividend_yield": dividend_yield_percent if dividend_yield else None,
                "currency": info.get("currency"),
                "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
                "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
                "volume": info.get("volume"),
                "average_volume": info.get("averageVolume")
            })
            
            filtered.append(candidate)
            
            # Small delay to avoid rate limiting
            time.sleep(0.1)
            
        except Exception as e:
            frappe.log_error(f"Error filtering {symbol}: {str(e)}", "Discovery Tools")
            continue
    
    return filtered


def _enrich_securities_data(securities, rate_limiter=None, circuit_breaker=None):
    """Enrich securities with additional data (news, SEC filings)."""
    enriched = []
    
    for security in securities:
        symbol = security.get("symbol")
        
        try:
            # Get news
            try:
                if rate_limiter:
                    rate_limiter.check_limit("yfinance", "news")
                
                ticker = yf.Ticker(symbol)
                news_items = ticker.get_news()
                if news_items:
                    security["recent_news"] = news_items[:3]  # Limit to 3 most recent
            except Exception as e:
                frappe.log_error(f"Error getting news for {symbol}: {str(e)}", "Discovery Tools")
                security["recent_news"] = []
            
            # Try to get SEC data if CIK is available
            try:
                # Import here to avoid circular imports
                from cognitive_folio.cognitive_folio.utils.helper import get_edgar_data
                
                # Extract CIK from ticker info or lookup
                ticker_info = yf.Ticker(symbol).get_info()
                if "cik" in ticker_info:
                    cik = str(ticker_info["cik"]).zfill(10)
                    
                    # Get SEC data
                    sec_data = get_edgar_data(cik, annual_years=2, quarterly_count=4)
                    if sec_data:
                        security["sec_data_available"] = True
                        # Extract key metrics
                        if "income_statement_annual" in sec_data:
                            income_data = sec_data["income_statement_annual"]
                            if "data" in income_data and len(income_data["data"]) > 0:
                                latest_year = income_data["data"][0]
                                security["revenue"] = latest_year.get("Revenue")
                                security["net_income"] = latest_year.get("NetIncomeLoss")
            except Exception as e:
                frappe.log_error(f"Error getting SEC data for {symbol}: {str(e)}", "Discovery Tools")
                security["sec_data_available"] = False
            
            enriched.append(security)
            
        except Exception as e:
            frappe.log_error(f"Error enriching {symbol}: {str(e)}", "Discovery Tools")
            enriched.append(security)  # Add without enrichment
    
    return enriched