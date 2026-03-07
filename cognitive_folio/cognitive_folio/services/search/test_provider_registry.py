import unittest

from cognitive_folio.cognitive_folio.services.search import ProviderRegistry


class TestProviderRegistry(unittest.TestCase):
    def test_resolve_chain_auto_uses_query_type_defaults(self):
        registry = ProviderRegistry()
        registry.register("ddgs", lambda **_: [])
        registry.register("wikipedia", lambda **_: [])

        chain = registry.resolve_chain(provider_hint="auto", query_type="general")
        self.assertEqual(chain, ["ddgs", "wikipedia"])

    def test_provider_hint_overrides_chain(self):
        registry = ProviderRegistry()
        registry.register("ddgs", lambda **_: [])
        registry.register("sec_edgar", lambda **_: [])

        chain = registry.resolve_chain(provider_hint="sec_edgar", query_type="financial")
        self.assertEqual(chain, ["sec_edgar"])

    def test_set_chain_deduplicates(self):
        registry = ProviderRegistry()
        registry.register("ddgs", lambda **_: [])
        registry.register("wikipedia", lambda **_: [])
        registry.set_chain("general", ["ddgs", "ddgs", "wikipedia"])

        chain = registry.resolve_chain(provider_hint="auto", query_type="general")
        self.assertEqual(chain, ["ddgs", "wikipedia"])
