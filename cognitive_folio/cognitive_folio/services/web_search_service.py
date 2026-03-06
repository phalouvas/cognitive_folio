import re

import frappe


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

    def search_web_results(self, query, num_results=3, providers=None, domain_filter=None, result_type="snippets", date_range=None):
        if providers is None:
            query_type = self.classify_query_type(query)
            providers = ["ddgs"] if query_type == "financial" else ["ddgs", "wikipedia"]

        all_results = []
        per_provider = max(1, num_results)

        for provider in providers:
            try:
                if provider == "ddgs":
                    results = self.search_ddgs(
                        query,
                        max_results=per_provider,
                        date_range=date_range,
                        domain_filter=domain_filter,
                    )
                elif provider == "wikipedia":
                    results = self.search_wikipedia(query, max_results=min(3, per_provider))
                else:
                    continue
                all_results.extend(results)
            except Exception as exc:
                frappe.log_error(f"Provider '{provider}' search error: {str(exc)}", "Web Search Error")

        deduped = self.deduplicate_results(all_results)[:num_results]

        if result_type == "full" and deduped:
            top = deduped[0]
            try:
                fetched = self.chat_message._tool_fetch_url_content({"url": top["url"], "max_chars": DEFAULT_TOOL_RESULT_MAX_CHARS})
                top["full_content"] = (fetched.get("content") or "")[:DEFAULT_TOOL_RESULT_MAX_CHARS]
            except Exception:
                pass

        return deduped

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

    def search_financial_sources(self, query, ticker=None, source="auto", form_type=None, max_results=5):
        all_results = []
        half = max(1, max_results // 2 + 1)

        if source in ("auto", "sec_edgar"):
            all_results.extend(self.search_edgar(query, ticker=ticker, form_type=form_type, max_results=half))

        if source in ("auto", "yahoo_finance"):
            yf_query = f"{query} {ticker} site:finance.yahoo.com" if ticker else f"{query} site:finance.yahoo.com"
            yf_results = self.search_ddgs(yf_query, max_results=half)
            for result in yf_results:
                result["source"] = "yahoo_finance"
            all_results.extend(yf_results)

        if source in ("auto", "financial_news"):
            news_results = self.search_ddgs(
                query,
                max_results=half,
                domain_filter="reuters.com,bloomberg.com,wsj.com,ft.com,marketwatch.com",
            )
            for result in news_results:
                result["source"] = "financial_news"
            all_results.extend(news_results)

        return self.deduplicate_results(all_results)[:max_results]

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
