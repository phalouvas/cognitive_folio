class ProviderRegistry:
    """Resolve and execute search providers with configurable fallback chains."""

    DEFAULT_CHAINS = {
        "general": ["ddgs", "wikipedia"],
        "financial": ["ddgs", "sec_edgar", "financial_news", "yahoo_finance"],
    }

    def __init__(self, chains=None):
        self._providers = {}
        self._chains = dict(self.DEFAULT_CHAINS)
        if isinstance(chains, dict):
            for key, value in chains.items():
                self.set_chain(key, value)

    def register(self, name, handler):
        if not name or not callable(handler):
            return
        self._providers[str(name).strip().lower()] = handler

    def set_chain(self, query_type, providers):
        key = str(query_type or "general").strip().lower()
        normalized = []
        for provider in providers or []:
            value = str(provider or "").strip().lower()
            if value and value not in normalized:
                normalized.append(value)
        if normalized:
            self._chains[key] = normalized

    def resolve_chain(self, provider_hint=None, query_type="general"):
        hint = str(provider_hint or "auto").strip().lower()
        if hint and hint != "auto":
            return [hint]

        key = str(query_type or "general").strip().lower()
        chain = self._chains.get(key) or self._chains.get("general") or []
        return [provider for provider in chain if provider in self._providers]

    def get_handler(self, provider_name):
        return self._providers.get(str(provider_name or "").strip().lower())

    def execute_chain(self, provider_hint, query_type, call_provider):
        chain = self.resolve_chain(provider_hint=provider_hint, query_type=query_type)
        outcomes = []

        for provider_name in chain:
            handler = self._providers.get(provider_name)
            if not handler:
                continue
            outcomes.append(call_provider(provider_name, handler))

        return outcomes
