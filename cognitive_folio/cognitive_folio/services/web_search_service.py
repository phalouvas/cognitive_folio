import re
from urllib.parse import urlparse

import frappe

from .compliance import AccessControl, AuditLogger, ContentSanitizer, PrivacyPreserver, SearchComplianceTracker
from .performance import (
    CircuitBreakerManager,
    HealthDashboard,
    PredictivePrefetching,
    RateLimiter,
    SearchResultCache,
)
from .search import ProviderRegistry, QueryRefiner, ResultReranker, SearchSessionTracker


DEFAULT_TOOL_RESULT_MAX_CHARS = 8000
FINANCIAL_QUERY_KEYWORDS = frozenset([
    "stock", "equity", "share", "dividend", "earnings", "revenue", "profit", "loss",
    "market cap", "pe ratio", "p/e", "ebitda", "balance sheet", "cash flow",
    "10-k", "10-q", "8-k", "sec filing", "annual report", "quarterly report",
    "ticker", "isin", "bond", "yield", "interest rate", "fed",
    "sec", "edgar", "ipo", "merger", "acquisition", "valuation", "analyst",
    "price target", "buy rating", "sell rating", "hold rating",
])


class WebSearchService:
    """Web and financial search provider orchestration."""

    def __init__(self, chat_message):
        self.chat_message = chat_message
        self.provider_registry = ProviderRegistry()
        self.provider_registry.register("ddgs", self._provider_ddgs)
        self.provider_registry.register("wikipedia", self._provider_wikipedia)
        self.provider_registry.register("serpapi", self._provider_serpapi)
        self.provider_registry.register("sec_edgar", self._provider_sec_edgar)
        self.provider_registry.register("financial_news", self._provider_financial_news)
        self.provider_registry.register("yahoo_finance", self._provider_yahoo_finance)
        self._search_provider_config = self._get_search_provider_config()
        self._performance_config = self._with_runtime_namespaces(self._get_performance_config())
        self._compliance_config = self._get_compliance_monitoring_config()
        self._apply_registry_chains(self._search_provider_config)
        self.query_refiner = QueryRefiner(enable_llm=bool((self._search_provider_config or {}).get("query_refiner_llm_enabled")))
        self.result_reranker = ResultReranker()
        self.search_session_tracker = SearchSessionTracker()
        self.access_control = AccessControl()
        self.audit_logger = AuditLogger()
        self.content_sanitizer = ContentSanitizer()
        self.privacy_preserver = PrivacyPreserver()
        self.search_compliance_tracker = SearchComplianceTracker()
        self.search_cache = SearchResultCache(config=self._performance_config)
        self.prefetching = PredictivePrefetching(config=self._performance_config)
        self.circuit_breaker = CircuitBreakerManager(config=self._performance_config)
        self.rate_limiter = RateLimiter(config=self._performance_config)
        self.health_dashboard = HealthDashboard()

    def _with_runtime_namespaces(self, config):
        resolved = dict(config or {})
        runtime_id = str(getattr(self.chat_message, "chat", None) or getattr(self.chat_message, "name", None) or id(self.chat_message))
        suffix = runtime_id.replace(" ", "_")
        resolved.setdefault("search_cache_namespace", f"cf:search:{suffix}")
        resolved.setdefault("search_circuit_breaker_namespace", f"cf:circuit:{suffix}")
        resolved.setdefault("search_rate_limiter_namespace", f"cf:rate:{suffix}")
        return resolved

    def _get_search_provider_config(self):
        try:
            settings_doc = frappe.get_single("CF Settings")
            if hasattr(self.chat_message, "_get_settings_manager"):
                manager = self.chat_message._get_settings_manager(settings_doc)
            else:
                from .settings_manager import SettingsManager

                manager = SettingsManager(settings_doc)

            if hasattr(manager, "get_search_provider_config"):
                return manager.get_search_provider_config() or {}
        except Exception:
            pass

        return {
            "general_chain": ["ddgs", "wikipedia"],
            "financial_chain": ["ddgs", "sec_edgar", "financial_news", "yahoo_finance"],
            "financial_domains": ["reuters.com", "bloomberg.com", "wsj.com", "ft.com", "marketwatch.com"],
            "max_results": 5,
            "serpapi_enabled": False,
            "serpapi_api_key": "",
            "serpapi_engine": "google",
            "sec_realtime_enabled": True,
            "sec_user_agent": "CognitiveFolio/1.0 research@example.com",
            "provider_timeout_seconds": 15,
            "query_refiner_enabled": True,
            "query_refiner_llm_enabled": False,
            "result_reranker_enabled": True,
            "result_reranker_top_k": 8,
            "freshness_weighting_enabled": True,
            "freshness_half_life_days": 21,
            "cross_source_verifier_enabled": True,
            "cross_source_min_sources": 2,
            "cross_source_contradiction_penalty": 0.25,
            "cross_source_confidence_boost": 0.1,
            "domain_authority_enabled": True,
            "domain_authority_default_weight": 0.2,
            "domain_authority_weights": {},
            "session_tracker_enabled": True,
            "session_max_entries": 25,
            "session_context_max_items": 3,
            "session_context_max_chars": 180,
            "session_followup_expand_enabled": True,
            "semantic_search_enabled": False,
            "semantic_embedding_dims": 96,
            "semantic_score_weight": 0.6,
            "trend_detector_enabled": False,
            "trend_min_frequency": 2,
            "trend_score_weight": 0.4,
            "personalized_search_enabled": False,
            "personalized_score_weight": 0.35,
            "personalized_history_items": 5,
            "preferred_sources": [],
            "preferred_domains": [],
        }

    def _get_performance_config(self):
        try:
            settings_doc = frappe.get_single("CF Settings")
            if hasattr(self.chat_message, "_get_settings_manager"):
                manager = self.chat_message._get_settings_manager(settings_doc)
            else:
                from .settings_manager import SettingsManager

                manager = SettingsManager(settings_doc)

            if hasattr(manager, "get_performance_config"):
                return manager.get_performance_config() or {}
        except Exception:
            pass

        return {
            "search_cache_enabled": True,
            "search_cache_ttl_general_seconds": 900,
            "search_cache_ttl_financial_seconds": 300,
            "search_cache_ttl_realtime_seconds": 120,
            "content_summary_cache_enabled": True,
            "content_summary_cache_ttl_seconds": 3600,
            "tool_result_cache_enabled": True,
            "tool_result_cache_ttl_seconds": 600,
            "search_prefetch_enabled": False,
            "search_prefetch_max_queries": 2,
            "search_circuit_breaker_enabled": True,
            "search_circuit_breaker_failure_threshold": 3,
            "search_circuit_breaker_recovery_seconds": 120,
            "search_circuit_breaker_half_open_calls": 1,
            "search_rate_limiter_enabled": True,
            "search_rate_limit_per_provider_per_minute": 60,
            "search_stale_cache_fallback_enabled": True,
            "db_batch_writer_enabled": True,
            "db_index_maintenance_enabled": False,
            "health_dashboard_enabled": True,
        }

    def _get_compliance_monitoring_config(self):
        try:
            settings_doc = frappe.get_single("CF Settings")
            if hasattr(self.chat_message, "_get_settings_manager"):
                manager = self.chat_message._get_settings_manager(settings_doc)
            else:
                from .settings_manager import SettingsManager

                manager = SettingsManager(settings_doc)

            if hasattr(manager, "get_compliance_monitoring_config"):
                return manager.get_compliance_monitoring_config() or {}
        except Exception:
            pass

        return {
            "content_sanitizer_enabled": True,
            "privacy_preserver_enabled": True,
            "search_compliance_tracking_enabled": True,
            "audit_logging_enabled": True,
            "access_control_enabled": True,
        }

    def _apply_registry_chains(self, config):
        config = config or {}
        general_chain = [str(item).strip().lower() for item in (config.get("general_chain") or []) if str(item).strip()]
        financial_chain = [str(item).strip().lower() for item in (config.get("financial_chain") or []) if str(item).strip()]

        if not config.get("serpapi_enabled"):
            general_chain = [name for name in general_chain if name != "serpapi"]
            financial_chain = [name for name in financial_chain if name != "serpapi"]

        if general_chain:
            self.provider_registry.set_chain("general", general_chain)
        if financial_chain:
            self.provider_registry.set_chain("financial", financial_chain)

    def extract_search_query(self, prompt_text=None):
        try:
            from openai import OpenAI

            settings = frappe.get_single("CF Settings")
            client = OpenAI(api_key=settings.get_password("open_ai_api_key"), base_url=settings.open_ai_url)

            extraction_prompt = f"""
You are a search query extraction assistant. Your job is to analyze user prompts and extract the most relevant search terms for a web search.

Rules:
1. Extract 1-3 key search terms or phrases that would be most useful for web search
2. Focus on specific topics, companies, concepts, or current events mentioned
3. Ignore generic words like "tell me about" or "what do you think"
4. If the prompt is about financial analysis, include relevant financial terms
5. Return only the search query, nothing else
6. If no clear search terms can be identified, return the main topic in 2-3 words

User prompt: "{(prompt_text if prompt_text is not None else self.chat_message.prompt)[:500]}"

Search query:"""

            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": extraction_prompt}],
                max_tokens=50,
                temperature=0.1,
            )

            search_query = response.choices[0].message.content.strip()
            search_query = search_query.strip('"\'.,!?')

            if not search_query or len(search_query) < 3:
                source_prompt = prompt_text if prompt_text is not None else self.chat_message.prompt
                return (source_prompt or "")[:50].strip()

            return search_query

        except Exception as exc:
            frappe.log_error(f"Search query extraction error: {str(exc)}", "Search Query Extraction")
            source_prompt = prompt_text if prompt_text is not None else self.chat_message.prompt
            return (source_prompt or "")[:50].strip()

    def perform_web_search(self, query, num_results=3):
        results = self.search_web_results(query, num_results=num_results)
        if not results:
            return ""

        snippets = []
        for result in results:
            snippet = (result.get("snippet") or "").strip()
            if not snippet:
                continue
            if len(snippet) > 240:
                snippet = snippet[:240] + "..."
            snippets.append(snippet)

        if not snippets:
            return ""

        lines = ["Web snippets:"]
        for i, snippet in enumerate(snippets, 1):
            lines.append(f"{i}. {snippet}")

        return "\n".join(lines)

    def search_web_results(self, query, num_results=3, providers=None, domain_filter=None, result_type="snippets", date_range=None, is_prefetch=False):
        if self._compliance_config.get("access_control_enabled", True) and not self.access_control.has_access("search"):
            if self._compliance_config.get("audit_logging_enabled", True):
                self.audit_logger.log(
                    event_name="search_access_denied",
                    status="denied",
                    details={"query_type": "web"},
                    chat=getattr(self.chat_message, "chat", None),
                    message=getattr(self.chat_message, "name", None),
                )
            return []

        if self._compliance_config.get("privacy_preserver_enabled", True):
            query = self.privacy_preserver.anonymize_query(query)

        query_type = self.classify_query_type(query)
        search_query = self._prepare_search_query(query=query, query_type=query_type)
        provider_hint = providers[0] if isinstance(providers, list) and len(providers) == 1 else "auto"
        if isinstance(providers, list) and len(providers) > 1:
            resolved_providers = [str(value).strip().lower() for value in providers if str(value or "").strip()]
        else:
            resolved_providers = self.provider_registry.resolve_chain(provider_hint=provider_hint, query_type=query_type)

        cache_payload = {
            "query": search_query,
            "num_results": int(num_results or 0),
            "providers": resolved_providers,
            "domain_filter": domain_filter,
            "result_type": result_type,
            "date_range": date_range,
            "query_type": query_type,
        }
        cached = self.search_cache.get("search_web_results", cache_payload)
        if isinstance(cached, list):
            return cached[:num_results]

        all_results = []
        weather_results = []
        if self._is_weather_query(search_query):
            weather_results = self._search_weather_now(search_query)
            if weather_results:
                all_results.extend(weather_results)

        configured_max = int((self._search_provider_config or {}).get("max_results", 5) or 5)
        per_provider = max(1, min(num_results, configured_max))

        for provider in resolved_providers:
            results = self._execute_provider_search(
                provider=provider,
                query=search_query,
                max_results=per_provider,
                date_range=date_range,
                domain_filter=domain_filter,
                ticker=None,
                form_type=None,
            )
            all_results.extend(results)
            if len(all_results) >= num_results:
                break

        deduped = self.deduplicate_results(all_results)
        if self._compliance_config.get("content_sanitizer_enabled", True):
            deduped = self.content_sanitizer.sanitize_result_items(deduped)
        reranked = self._rerank_results(query=search_query, query_type=query_type, results=deduped)
        final_results = reranked[:num_results]

        if result_type == "full" and final_results:
            top = final_results[0]
            try:
                fetched = self.chat_message._tool_fetch_url_content({"url": top["url"], "max_chars": DEFAULT_TOOL_RESULT_MAX_CHARS})
                top["full_content"] = (fetched.get("content") or "")[:DEFAULT_TOOL_RESULT_MAX_CHARS]
            except Exception:
                pass

        if not is_prefetch:
            self._record_search_session(
                query=search_query,
                query_type=query_type,
                providers=resolved_providers,
                results=final_results,
            )

            if self._compliance_config.get("search_compliance_tracking_enabled", True):
                self.search_compliance_tracker.record_search(
                    query=search_query,
                    query_type=query_type,
                    providers=resolved_providers,
                    result_count=len(final_results),
                    metadata={
                        "chat": getattr(self.chat_message, "chat", None),
                        "message": getattr(self.chat_message, "name", None),
                        "mode": "web",
                    },
                )

        self.search_cache.set(
            operation="search_web_results",
            payload=cache_payload,
            value=final_results,
            query_type=query_type,
            date_range=date_range,
        )

        if not is_prefetch:
            self._prefetch_follow_ups(query=search_query, query_type=query_type, ticker=None)

        return final_results

    def _is_weather_query(self, query):
        lowered = str(query or "").lower()
        if not lowered:
            return False
        weather_markers = ("weather", "temperature", "forecast", "humidity", "wind", "rain")
        return any(marker in lowered for marker in weather_markers)

    def _extract_weather_location(self, query):
        text = str(query or "").strip()
        if not text:
            return ""

        lowered = text.lower()
        if " in " in lowered:
            return text[lowered.rfind(" in ") + 4 :].strip(" ?.,")

        cleaned = re.sub(r"\b(what|is|the|weather|now|current|currently|today|temperature|forecast|in)\b", " ", lowered)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ?.,")
        return cleaned or text.strip(" ?.,")

    def _search_weather_now(self, query):
        location = self._extract_weather_location(query)
        if not location:
            return []

        try:
            import requests as req
            from urllib.parse import quote_plus

            encoded = quote_plus(location)
            url = f"https://wttr.in/{encoded}?format=j1"
            response = req.get(url, timeout=10, headers={"User-Agent": "CognitiveFolio/1.0 weather lookup"})
            response.raise_for_status()
            payload = response.json() if response.content else {}
            current = (payload.get("current_condition") or [{}])[0] if isinstance(payload, dict) else {}
            if not current:
                return []

            desc = ""
            weather_desc = current.get("weatherDesc") or []
            if weather_desc and isinstance(weather_desc, list):
                desc = str((weather_desc[0] or {}).get("value") or "").strip()

            temp_c = str(current.get("temp_C") or "").strip()
            feels_c = str(current.get("FeelsLikeC") or "").strip()
            humidity = str(current.get("humidity") or "").strip()
            wind_kmph = str(current.get("windspeedKmph") or "").strip()
            observed = str(current.get("localObsDateTime") or current.get("observation_time") or "").strip()

            title = f"Current weather in {location}"
            snippet_parts = []
            if temp_c:
                snippet_parts.append(f"Temperature: {temp_c}C")
            if feels_c:
                snippet_parts.append(f"Feels like: {feels_c}C")
            if humidity:
                snippet_parts.append(f"Humidity: {humidity}%")
            if wind_kmph:
                snippet_parts.append(f"Wind: {wind_kmph} km/h")
            if desc:
                snippet_parts.append(f"Conditions: {desc}")
            if observed:
                snippet_parts.append(f"Observed: {observed}")

            snippet = ". ".join(snippet_parts)[:500]
            return [
                {
                    "title": title,
                    "url": f"https://wttr.in/{encoded}",
                    "snippet": snippet,
                    "source": "wttr.in",
                    "metadata": {
                        "location": location,
                        "temp_c": temp_c,
                        "feels_like_c": feels_c,
                        "humidity": humidity,
                        "wind_kmph": wind_kmph,
                        "conditions": desc,
                        "observed": observed,
                    },
                }
            ]
        except Exception:
            return []

    def search_ddgs(self, query, max_results=5, date_range=None, domain_filter=None):
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            frappe.log_error("duckduckgo_search package not installed", "Web Search Error")
            return []

        effective_query = query
        if domain_filter:
            domains = [d.strip() for d in domain_filter.split(",") if d.strip()][:3]
            if domains:
                site_clause = " OR ".join(f"site:{d}" for d in domains)
                effective_query = f"({query}) ({site_clause})"

        timelimit_map = {"day": "d", "week": "w", "month": "m", "year": "y"}
        timelimit = timelimit_map.get(date_range) if date_range else None

        try:
            kwargs = {"max_results": max_results}
            if timelimit:
                kwargs["timelimit"] = timelimit
            with DDGS() as ddgs:
                raw_results = list(ddgs.text(effective_query, **kwargs))
        except Exception as exc:
            frappe.log_error(f"DuckDuckGo search error for '{query}': {str(exc)}", "Web Search Error")
            return []

        normalized = []
        for result in raw_results or []:
            if not isinstance(result, dict):
                continue
            title = (result.get("title") or "").strip()
            url = (result.get("href") or "").strip()
            snippet = (result.get("body") or "").strip()
            if not url:
                continue
            if len(snippet) > 500:
                snippet = snippet[:500] + "..."
            normalized.append({
                "title": title or "Untitled",
                "url": url,
                "snippet": snippet,
                "source": "ddgs",
            })
        return normalized

    def search_wikipedia(self, query, max_results=3):
        try:
            import requests as req
        except ImportError:
            return []

        try:
            resp = req.get(
                "https://en.wikipedia.org/w/api.php",
                params={
                    "action": "query",
                    "list": "search",
                    "srsearch": query,
                    "srlimit": max_results,
                    "format": "json",
                    "srprop": "snippet",
                },
                timeout=10,
                headers={"User-Agent": "CognitiveFolio/1.0 (financial research bot)"},
            )
            resp.raise_for_status()
            search_items = resp.json().get("query", {}).get("search", [])
        except Exception as exc:
            frappe.log_error(f"Wikipedia search error for '{query}': {str(exc)}", "Web Search Error")
            return []

        normalized = []
        for item in search_items:
            title = (item.get("title") or "").strip()
            if not title:
                continue
            from urllib.parse import quote as _quote

            page_url = "https://en.wikipedia.org/wiki/" + _quote(title.replace(" ", "_"), safe="")
            raw_snippet = item.get("snippet") or ""
            snippet = re.sub(r"<[^>]+>", "", raw_snippet).strip()
            if len(snippet) > 500:
                snippet = snippet[:500] + "..."
            normalized.append({
                "title": title,
                "url": page_url,
                "snippet": snippet,
                "source": "wikipedia",
            })
        return normalized

    def search_edgar(self, query, ticker=None, form_type=None, max_results=3):
        try:
            import requests as req
        except ImportError:
            return []

        try:
            params = {
                "q": f'"{query}"',
                "dateRange": "custom",
                "startdt": "2020-01-01",
            }
            if ticker:
                params["entity"] = ticker.upper()
            if form_type:
                params["forms"] = form_type.upper()

            resp = req.get(
                "https://efts.sec.gov/LATEST/search-index",
                params=params,
                timeout=15,
                headers={"User-Agent": "CognitiveFolio/1.0 research@example.com"},
            )
            resp.raise_for_status()
            hits = (resp.json().get("hits") or {}).get("hits") or []
        except Exception as exc:
            frappe.log_error(f"SEC EDGAR search error for '{query}': {str(exc)}", "Web Search Error")
            return []

        normalized = []
        for hit in hits[:max_results]:
            src = hit.get("_source") or {}
            entity_name = (src.get("entity_name") or "").strip()
            if not entity_name:
                continue
            form = (src.get("form_type") or "").strip()
            period = (src.get("period_of_report") or "").strip()
            file_date = (src.get("file_date") or "").strip()
            cik = (src.get("entity_id") or src.get("cik") or "").strip()
            accession = (src.get("accession_no") or "").replace("-", "").strip()

            if cik and accession:
                filing_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{accession}-index.htm"
            elif cik:
                filing_url = (
                    f"https://www.sec.gov/cgi-bin/browse-edgar"
                    f"?action=getcompany&CIK={cik}&type={form}&dateb=&owner=include&count=10"
                )
            else:
                filing_url = "https://www.sec.gov/cgi-bin/srqsb"

            title = f"{entity_name} - {form}" + (f" ({period})" if period else "")
            snippet = f"{entity_name} filed {form} with the SEC. Period: {period or 'N/A'}. Filed: {file_date or 'N/A'}."
            normalized.append({
                "title": title,
                "url": filing_url,
                "snippet": snippet,
                "source": "sec_edgar",
                "metadata": {
                    "form_type": form,
                    "period": period,
                    "entity": entity_name,
                    "file_date": file_date,
                },
            })
        return normalized

    def search_edgar_realtime(self, ticker, form_type=None, max_results=3):
        try:
            import requests as req
        except ImportError:
            return []

        cik = self._resolve_sec_cik(ticker=ticker, timeout_seconds=10)
        if not cik:
            return []

        timeout_seconds = int((self._search_provider_config or {}).get("provider_timeout_seconds", 15) or 15)
        headers = {"User-Agent": self._sec_user_agent()}
        submissions_url = f"https://data.sec.gov/submissions/CIK{cik}.json"

        try:
            response = req.get(submissions_url, timeout=timeout_seconds, headers=headers)
            response.raise_for_status()
            payload = response.json() if response.content else {}
        except Exception as exc:
            frappe.log_error(f"SEC submissions realtime fetch error for ticker '{ticker}': {str(exc)}", "Web Search Error")
            return []

        recent = ((payload or {}).get("filings") or {}).get("recent") or {}
        forms = recent.get("form") or []
        accession_numbers = recent.get("accessionNumber") or []
        filing_dates = recent.get("filingDate") or []
        report_dates = recent.get("reportDate") or []
        primary_documents = recent.get("primaryDocument") or []
        primary_descriptions = recent.get("primaryDocDescription") or []

        total = min(len(forms), len(accession_numbers), len(filing_dates), len(primary_documents))
        normalized = []
        for idx in range(total):
            form = str(forms[idx] or "").strip().upper()
            if form_type and form and form != str(form_type).strip().upper():
                continue

            accession = str(accession_numbers[idx] or "").strip()
            accession_nodash = accession.replace("-", "")
            filing_date = str(filing_dates[idx] or "").strip()
            report_date = str(report_dates[idx] or "").strip()
            document = str(primary_documents[idx] or "").strip()
            description = str(primary_descriptions[idx] or "").strip()
            if not accession_nodash or not document:
                continue

            company_name = str((payload or {}).get("name") or ticker or "").strip()
            cik_int = str(int(cik))
            filing_url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_nodash}/{document}"
            title = f"{company_name} - {form}"
            snippet = f"{company_name} filed {form} on {filing_date or 'N/A'}. Report period: {report_date or 'N/A'}."
            if description:
                snippet = f"{snippet} {description}"

            normalized.append(
                {
                    "title": title,
                    "url": filing_url,
                    "snippet": snippet,
                    "source": "sec_edgar",
                    "metadata": {
                        "form_type": form,
                        "period": report_date,
                        "entity": company_name,
                        "file_date": filing_date,
                        "realtime": True,
                    },
                }
            )
            if len(normalized) >= max(1, int(max_results or 3)):
                break

        return normalized

    def search_financial_sources(self, query, ticker=None, source="auto", form_type=None, max_results=5, is_prefetch=False):
        if self._compliance_config.get("access_control_enabled", True) and not self.access_control.has_access("search"):
            if self._compliance_config.get("audit_logging_enabled", True):
                self.audit_logger.log(
                    event_name="search_access_denied",
                    status="denied",
                    details={"query_type": "financial"},
                    chat=getattr(self.chat_message, "chat", None),
                    message=getattr(self.chat_message, "name", None),
                )
            return []

        if self._compliance_config.get("privacy_preserver_enabled", True):
            query = self.privacy_preserver.anonymize_query(query)

        search_query = self._prepare_search_query(query=query, query_type="financial", ticker=ticker)
        cache_payload = {
            "query": search_query,
            "ticker": ticker,
            "source": source,
            "form_type": form_type,
            "max_results": int(max_results or 0),
            "query_type": "financial",
        }
        cached = self.search_cache.get("search_financial_sources", cache_payload)
        if isinstance(cached, list):
            return cached[:max_results]

        all_results = []
        half = max(1, max_results // 2 + 1)
        provider_hint = source if source in ("sec_edgar", "yahoo_finance", "financial_news", "serpapi") else "auto"
        resolved_providers = self.provider_registry.resolve_chain(provider_hint=provider_hint, query_type="financial")

        for provider in resolved_providers:
            results = self._execute_provider_search(
                provider=provider,
                query=search_query,
                max_results=half,
                date_range=None,
                domain_filter=None,
                ticker=ticker,
                form_type=form_type,
            )
            all_results.extend(results)
            if len(all_results) >= max_results:
                break

        deduped = self.deduplicate_results(all_results)
        if self._compliance_config.get("content_sanitizer_enabled", True):
            deduped = self.content_sanitizer.sanitize_result_items(deduped)
        reranked = self._rerank_results(query=search_query, query_type="financial", results=deduped, ticker=ticker)
        final_results = reranked[:max_results]
        if not is_prefetch:
            self._record_search_session(
                query=search_query,
                query_type="financial",
                providers=resolved_providers,
                results=final_results,
            )

            if self._compliance_config.get("search_compliance_tracking_enabled", True):
                self.search_compliance_tracker.record_search(
                    query=search_query,
                    query_type="financial",
                    providers=resolved_providers,
                    result_count=len(final_results),
                    metadata={
                        "chat": getattr(self.chat_message, "chat", None),
                        "message": getattr(self.chat_message, "name", None),
                        "mode": "financial",
                        "ticker": ticker,
                        "source": source,
                    },
                )

        self.search_cache.set(
            operation="search_financial_sources",
            payload=cache_payload,
            value=final_results,
            query_type="financial",
            date_range=None,
        )

        if not is_prefetch:
            self._prefetch_follow_ups(query=search_query, query_type="financial", ticker=ticker)

        return final_results

    def _execute_provider_search(self, provider, query, max_results, date_range, domain_filter, ticker, form_type):
        if not self.circuit_breaker.allow_request(provider):
            return []

        if not self.rate_limiter.allow(provider):
            return []

        handler = self.provider_registry.get_handler(provider)
        if not handler:
            return []

        try:
            results = handler(
                query=query,
                max_results=max_results,
                date_range=date_range,
                domain_filter=domain_filter,
                ticker=ticker,
                form_type=form_type,
            )
            self.circuit_breaker.record_success(provider)
            return list(results or [])
        except Exception as exc:
            self.circuit_breaker.record_failure(provider)
            frappe.log_error(f"Provider '{provider}' search error: {str(exc)}", "Web Search Error")
            return []

    def _prefetch_follow_ups(self, query, query_type, ticker=None):
        predicted = self.prefetching.predict_queries(query=query, query_type=query_type, ticker=ticker)
        if not predicted:
            return

        if query_type == "financial":
            self.prefetching.prefetch(
                callback=lambda query, num_results, is_prefetch=True: self.search_financial_sources(
                    query=query,
                    ticker=ticker,
                    source="auto",
                    form_type=None,
                    max_results=num_results,
                    is_prefetch=is_prefetch,
                ),
                queries=predicted,
                max_results=2,
            )
            return

        self.prefetching.prefetch(
            callback=lambda query, num_results, is_prefetch=True: self.search_web_results(
                query=query,
                num_results=num_results,
                providers=None,
                domain_filter=None,
                result_type="snippets",
                date_range=None,
                is_prefetch=is_prefetch,
            ),
            queries=predicted,
            max_results=2,
        )

    def get_health_snapshot(self):
        providers = (self.provider_registry or ProviderRegistry()).list_providers()
        return self.health_dashboard.build_snapshot(
            providers=providers,
            circuit_breaker=self.circuit_breaker,
            rate_limiter=self.rate_limiter,
        )

    def _prepare_search_query(self, query, query_type, ticker=None):
        config = self._search_provider_config or {}
        prepared_query = query

        if config.get("query_refiner_enabled", True):
            try:
                prepared_query = self.query_refiner.refine(
                    query=query,
                    query_type=query_type,
                    ticker=ticker,
                    extraction_fallback=self.extract_search_query,
                )
            except Exception as exc:
                frappe.log_error(f"Search query refinement error: {str(exc)}", "Web Search Error")
                prepared_query = query

        if config.get("session_tracker_enabled", True) and config.get("session_followup_expand_enabled", True):
            try:
                prepared_query = self.search_session_tracker.expand_follow_up_query(
                    query=prepared_query,
                    session_key=self._get_search_session_key(),
                    max_items=int(config.get("session_context_max_items", 3) or 3),
                    max_chars=int(config.get("session_context_max_chars", 180) or 180),
                )
            except Exception as exc:
                frappe.log_error(f"Search session context error: {str(exc)}", "Web Search Error")

        return prepared_query

    def _record_search_session(self, query, query_type, providers, results):
        config = self._search_provider_config or {}
        if not config.get("session_tracker_enabled", True):
            return

        try:
            self.search_session_tracker.record_search(
                session_key=self._get_search_session_key(),
                query=query,
                query_type=query_type,
                providers=providers,
                results=results,
                max_entries=int(config.get("session_max_entries", 25) or 25),
            )
        except Exception as exc:
            frappe.log_error(f"Search session record error: {str(exc)}", "Web Search Error")

    def _get_search_session_key(self):
        chat_name = getattr(self.chat_message, "chat", None)
        if chat_name:
            return str(chat_name)

        message_name = getattr(self.chat_message, "name", None)
        if message_name:
            return f"msg:{message_name}"

        return "default"

    def _rerank_results(self, query, query_type, results, ticker=None):
        config = self._search_provider_config or {}
        if not config.get("result_reranker_enabled", True):
            return list(results or [])

        top_k = int(config.get("result_reranker_top_k", 8) or 8)
        rerank_options = {
            "freshness_enabled": bool(config.get("freshness_weighting_enabled", True)),
            "freshness_half_life_days": int(config.get("freshness_half_life_days", 21) or 21),
            "cross_source_enabled": bool(config.get("cross_source_verifier_enabled", True)),
            "cross_source_min_sources": int(config.get("cross_source_min_sources", 2) or 2),
            "cross_source_contradiction_penalty": float(config.get("cross_source_contradiction_penalty", 0.25) or 0.25),
            "cross_source_confidence_boost": float(config.get("cross_source_confidence_boost", 0.1) or 0.1),
            "domain_authority_enabled": bool(config.get("domain_authority_enabled", True)),
            "domain_authority_default_weight": float(config.get("domain_authority_default_weight", 0.2) or 0.2),
            "domain_authority_weights": config.get("domain_authority_weights") or {},
            "semantic_search_enabled": bool(config.get("semantic_search_enabled", False)),
            "semantic_embedding_dims": int(config.get("semantic_embedding_dims", 96) or 96),
            "semantic_score_weight": float(config.get("semantic_score_weight", 0.6) or 0.6),
            "trend_detector_enabled": bool(config.get("trend_detector_enabled", False)),
            "trend_min_frequency": int(config.get("trend_min_frequency", 2) or 2),
            "trend_score_weight": float(config.get("trend_score_weight", 0.4) or 0.4),
            "personalized_search_enabled": bool(config.get("personalized_search_enabled", False)),
            "personalized_score_weight": float(config.get("personalized_score_weight", 0.35) or 0.35),
            "personalization_context": self._build_personalization_context(query_type=query_type, ticker=ticker),
        }
        try:
            return self.result_reranker.rerank(
                query=query,
                results=results or [],
                query_type=query_type,
                ticker=ticker,
                top_k=top_k,
                options=rerank_options,
            )
        except Exception as exc:
            frappe.log_error(f"Search result rerank error: {str(exc)}", "Web Search Error")
            return list(results or [])

    def _build_personalization_context(self, query_type, ticker=None):
        config = self._search_provider_config or {}
        preferred_sources = {str(item).strip().lower() for item in (config.get("preferred_sources") or []) if str(item).strip()}
        preferred_domains = {str(item).strip().lower().lstrip(".") for item in (config.get("preferred_domains") or []) if str(item).strip()}
        preferred_tickers = set()
        if ticker:
            preferred_tickers.add(str(ticker).strip().upper())

        if config.get("session_tracker_enabled", True):
            try:
                history = self.search_session_tracker.get_recent_history(
                    session_key=self._get_search_session_key(),
                    max_items=int(config.get("personalized_history_items", 5) or 5),
                )
            except Exception:
                history = []

            for item in history or []:
                for provider in (item or {}).get("providers") or []:
                    value = str(provider).strip().lower()
                    if value:
                        preferred_sources.add(value)
                for url in (item or {}).get("top_urls") or []:
                    host = self._host(url)
                    if host:
                        preferred_domains.add(host)

        return {
            "preferred_sources": sorted(preferred_sources),
            "preferred_domains": sorted(preferred_domains),
            "preferred_tickers": sorted({str(value).strip().lower() for value in preferred_tickers if str(value).strip()}),
            "preferred_query_type": str(query_type or "").strip().lower(),
            "query_type": str(query_type or "").strip().lower(),
        }

    def _host(self, url):
        try:
            return (urlparse(str(url or "")).hostname or "").lower().strip(".")
        except Exception:
            return ""

    def _provider_ddgs(self, query, max_results=5, date_range=None, domain_filter=None, ticker=None, form_type=None):
        return self.search_ddgs(
            query=query,
            max_results=max_results,
            date_range=date_range,
            domain_filter=domain_filter,
        )

    def _provider_wikipedia(self, query, max_results=5, date_range=None, domain_filter=None, ticker=None, form_type=None):
        return self.search_wikipedia(query=query, max_results=min(3, max_results))

    def _provider_sec_edgar(self, query, max_results=5, date_range=None, domain_filter=None, ticker=None, form_type=None):
        config = self._search_provider_config or {}
        realtime_results = []
        if config.get("sec_realtime_enabled", True) and ticker:
            realtime_results = self.search_edgar_realtime(
                ticker=ticker,
                form_type=form_type,
                max_results=max_results,
            )

        search_results = self.search_edgar(query=query, ticker=ticker, form_type=form_type, max_results=max_results)
        merged = self.deduplicate_results((realtime_results or []) + (search_results or []))
        return merged[: max(1, int(max_results or 5))]

    def _resolve_sec_cik(self, ticker, timeout_seconds=10):
        ticker_text = str(ticker or "").strip().upper()
        if not ticker_text:
            return ""

        if not hasattr(self, "_sec_ticker_cik_map"):
            self._sec_ticker_cik_map = {}

        if ticker_text in self._sec_ticker_cik_map:
            return self._sec_ticker_cik_map.get(ticker_text) or ""

        try:
            import requests as req
        except ImportError:
            return ""

        try:
            response = req.get(
                "https://www.sec.gov/files/company_tickers.json",
                timeout=max(3, int(timeout_seconds or 10)),
                headers={"User-Agent": self._sec_user_agent()},
            )
            response.raise_for_status()
            payload = response.json() if response.content else {}
        except Exception:
            return ""

        if isinstance(payload, dict):
            for value in payload.values():
                if not isinstance(value, dict):
                    continue
                symbol = str(value.get("ticker") or "").strip().upper()
                cik_number = value.get("cik_str")
                if symbol and cik_number is not None:
                    self._sec_ticker_cik_map[symbol] = str(cik_number).zfill(10)

        return self._sec_ticker_cik_map.get(ticker_text) or ""

    def _sec_user_agent(self):
        config = self._search_provider_config or {}
        value = str(config.get("sec_user_agent") or "").strip()
        return value or "CognitiveFolio/1.0 research@example.com"

    def _provider_yahoo_finance(self, query, max_results=5, date_range=None, domain_filter=None, ticker=None, form_type=None):
        yf_query = f"{query} {ticker} site:finance.yahoo.com" if ticker else f"{query} site:finance.yahoo.com"
        results = self.search_ddgs(yf_query, max_results=max_results)
        for result in results:
            result["source"] = "yahoo_finance"
        return results

    def _provider_financial_news(self, query, max_results=5, date_range=None, domain_filter=None, ticker=None, form_type=None):
        configured_domains = (self._search_provider_config or {}).get("financial_domains") or []
        domain_csv = ",".join(configured_domains) if configured_domains else "reuters.com,bloomberg.com,wsj.com,ft.com,marketwatch.com"
        results = self.search_ddgs(
            query,
            max_results=max_results,
            domain_filter=domain_csv,
        )
        for result in results:
            result["source"] = "financial_news"
        return results

    def _provider_serpapi(self, query, max_results=5, date_range=None, domain_filter=None, ticker=None, form_type=None):
        config = self._search_provider_config or {}
        if not config.get("serpapi_enabled"):
            return []

        api_key = str(config.get("serpapi_api_key") or "").strip()
        if not api_key:
            return []

        return self.search_serpapi(
            query=query,
            api_key=api_key,
            max_results=max_results,
            engine=str(config.get("serpapi_engine") or "google").strip().lower(),
            date_range=date_range,
            domain_filter=domain_filter,
            timeout_seconds=int(config.get("provider_timeout_seconds", 15) or 15),
        )

    def search_serpapi(self, query, api_key, max_results=5, engine="google", date_range=None, domain_filter=None, timeout_seconds=15):
        try:
            import requests as req
        except ImportError:
            frappe.log_error("requests package not installed", "SerpAPI Search Error")
            return []

        params = {
            "engine": engine or "google",
            "q": query,
            "api_key": api_key,
            "num": max(1, min(int(max_results or 5), 10)),
        }

        if domain_filter:
            first_domain = str(domain_filter).split(",")[0].strip()
            if first_domain:
                params["as_sitesearch"] = first_domain

        tbs_map = {"day": "qdr:d", "week": "qdr:w", "month": "qdr:m", "year": "qdr:y"}
        if date_range in tbs_map:
            params["tbs"] = tbs_map[date_range]

        try:
            response = req.get("https://serpapi.com/search.json", params=params, timeout=timeout_seconds)
            response.raise_for_status()
            payload = response.json() if response.content else {}
        except Exception as exc:
            frappe.log_error(f"SerpAPI search error for '{query}': {str(exc)}", "SerpAPI Search Error")
            return []

        organic = payload.get("organic_results") or []
        normalized = []
        for item in organic:
            if not isinstance(item, dict):
                continue
            title = (item.get("title") or "").strip()
            url = (item.get("link") or "").strip()
            snippet = (item.get("snippet") or "").strip()
            if not url:
                continue
            if len(snippet) > 500:
                snippet = snippet[:500] + "..."
            normalized.append(
                {
                    "title": title or "Untitled",
                    "url": url,
                    "snippet": snippet,
                    "source": "serpapi",
                }
            )

        return normalized

    def classify_query_type(self, query):
        lowered = (query or "").lower()
        return "financial" if any(kw in lowered for kw in FINANCIAL_QUERY_KEYWORDS) else "general"

    def deduplicate_results(self, results):
        seen_urls = set()
        deduped = []
        for result in results:
            url = (result.get("url") or "").strip().rstrip("/").lower()
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            deduped.append(result)
        return deduped
