from .cross_source_verifier import CrossSourceVerifier
from .domain_authority_scorer import DomainAuthorityScorer
from .freshness_weighting import FreshnessWeighting
from .personalized_search import PersonalizedSearch
from .semantic_search import SemanticSearch
from .trend_detector import TrendDetector


class ResultReranker:
    """Score search results by lexical relevance and source quality."""

    _PROVIDER_BASE_WEIGHTS = {
        "sec_edgar": 0.9,
        "financial_news": 0.7,
        "yahoo_finance": 0.65,
        "serpapi": 0.55,
        "ddgs": 0.5,
        "wikipedia": 0.45,
    }

    def __init__(
        self,
        freshness_weighting=None,
        cross_source_verifier=None,
        domain_authority_scorer=None,
        semantic_search=None,
        trend_detector=None,
        personalized_search=None,
    ):
        self.freshness_weighting = freshness_weighting or FreshnessWeighting()
        self.cross_source_verifier = cross_source_verifier or CrossSourceVerifier()
        self.domain_authority_scorer = domain_authority_scorer or DomainAuthorityScorer()
        self.semantic_search = semantic_search or SemanticSearch()
        self.trend_detector = trend_detector or TrendDetector()
        self.personalized_search = personalized_search or PersonalizedSearch()

    def rerank(self, query, results, query_type="general", ticker=None, top_k=8, options=None):
        if not results:
            return []

        options = options or {}
        query_terms = {part for part in (query or "").lower().split() if part}
        scored = []

        for index, result in enumerate(results):
            score = self._score_result(
                result=result,
                all_results=results,
                query_terms=query_terms,
                query_type=query_type,
                ticker=ticker,
                options=options,
            )
            # Preserve original order as a stable tie-breaker.
            scored.append((score, -index, result))

        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        limited = scored[: max(1, int(top_k or 8))]
        return [item[2] for item in limited]

    def _score_result(self, result, all_results, query_terms, query_type, ticker, options):
        title = (result.get("title") or "").lower()
        snippet = (result.get("snippet") or "").lower()
        source = (result.get("source") or "").strip().lower()
        url = (result.get("url") or "").strip().lower()

        lexical_score = 0.0
        for term in query_terms:
            if term in title:
                lexical_score += 1.2
            if term in snippet:
                lexical_score += 0.7
            if term in url:
                lexical_score += 0.5

        authority_score = 0.0
        if options.get("domain_authority_enabled", True):
            authority_score = self.domain_authority_scorer.score(
                url=url,
                domain_weights=options.get("domain_authority_weights"),
                default_weight=float(options.get("domain_authority_default_weight", 0.2) or 0.2),
            )
        provider_score = self._PROVIDER_BASE_WEIGHTS.get(source, 0.35)

        ticker_score = 0.0
        if ticker:
            ticker_text = str(ticker).strip().lower()
            joined = f"{title} {snippet} {url}"
            if ticker_text and ticker_text in joined:
                ticker_score = 0.8

        financial_bonus = 0.0
        if query_type == "financial" and source in {"sec_edgar", "financial_news", "yahoo_finance"}:
            financial_bonus = 0.5

        freshness_score = 0.0
        if options.get("freshness_enabled", True):
            freshness_score = self.freshness_weighting.score(
                result=result,
                query_type=query_type,
                half_life_days=int(options.get("freshness_half_life_days", 21) or 21),
                now_utc=options.get("now_utc"),
            )

        cross_source_score = 0.0
        if options.get("cross_source_enabled", True):
            cross_source_score = self.cross_source_verifier.score(
                target_result=result,
                all_results=all_results,
                min_sources=int(options.get("cross_source_min_sources", 2) or 2),
                contradiction_penalty=float(options.get("cross_source_contradiction_penalty", 0.25) or 0.25),
                confidence_boost=float(options.get("cross_source_confidence_boost", 0.1) or 0.1),
            )

        semantic_score = 0.0
        if options.get("semantic_search_enabled", False):
            semantic_score = self.semantic_search.score(
                query=" ".join(sorted(query_terms)) if query_terms else "",
                result=result,
                dims=int(options.get("semantic_embedding_dims", 96) or 96),
                weight=float(options.get("semantic_score_weight", 0.6) or 0.6),
            )

        trend_score = 0.0
        if options.get("trend_detector_enabled", False):
            trend_score = self.trend_detector.score(
                target_result=result,
                all_results=all_results,
                query_terms=query_terms,
                min_frequency=int(options.get("trend_min_frequency", 2) or 2),
                weight=float(options.get("trend_score_weight", 0.4) or 0.4),
            )

        personalized_score = 0.0
        if options.get("personalized_search_enabled", False):
            personalization_context = options.get("personalization_context") or {}
            if isinstance(personalization_context, dict):
                personalization_context = dict(personalization_context)
                personalization_context.setdefault("query_type", query_type)
            personalized_score = self.personalized_search.score(
                result=result,
                context=personalization_context,
                weight=float(options.get("personalized_score_weight", 0.35) or 0.35),
            )

        return (
            lexical_score
            + authority_score
            + provider_score
            + ticker_score
            + financial_bonus
            + freshness_score
            + cross_source_score
            + semantic_score
            + trend_score
            + personalized_score
        )
