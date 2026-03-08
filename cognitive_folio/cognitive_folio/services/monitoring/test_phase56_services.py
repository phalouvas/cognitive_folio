import unittest

from cognitive_folio.cognitive_folio.services.compliance import ContentSanitizer, PrivacyPreserver
from cognitive_folio.cognitive_folio.services.monitoring import AnswerQualityScorer, CostOptimizer, StatisticalAnalyzer, RolloutController


class TestPhase56Services(unittest.TestCase):
    def test_content_sanitizer_removes_script_and_tags(self):
        value = '<div>Hello<script>alert(1)</script><b>world</b></div>'
        cleaned = ContentSanitizer().sanitize_text(value)
        self.assertEqual(cleaned, "Helloworld")

    def test_content_sanitizer_preserves_newlines(self):
        value = "Line one\nLine two\n\nLine three"
        cleaned = ContentSanitizer().sanitize_text(value)
        self.assertEqual(cleaned, "Line one\nLine two\n\nLine three")

    def test_privacy_preserver_redacts_email_and_phone(self):
        text = "contact me at test@example.com or +1 (650) 123-4567"
        redacted = PrivacyPreserver().anonymize_query(text)
        self.assertNotIn("test@example.com", redacted)
        self.assertNotIn("650", redacted)

    def test_answer_quality_scorer_returns_weighted_scores(self):
        score = AnswerQualityScorer().score(
            prompt="analyze apple earnings",
            response="Apple earnings improved with strong revenue and margin expansion.",
            tool_trace=[{"ok": True}, {"ok": False}],
        )
        self.assertIn("quality_score", score)
        self.assertGreaterEqual(score["quality_score"], 0.0)
        self.assertLessEqual(score["quality_score"], 1.0)

    def test_cost_optimizer_estimates_cost(self):
        estimate = CostOptimizer().estimate(
            usage={"prompt_tokens": 1000, "completion_tokens": 500},
            tool_trace=[{"ok": True}] * 3,
        )
        self.assertGreater(estimate["estimated_cost_usd"], 0)
        self.assertEqual(estimate["tool_calls"], 3)

    def test_statistical_analyzer_and_rollout_controller(self):
        summary = StatisticalAnalyzer().compare_variants(
            [
                {"experiment": "exp-1", "variant": "variant_a", "quality_score": 0.8},
                {"experiment": "exp-1", "variant": "variant_a", "quality_score": 0.85},
                {"experiment": "exp-1", "variant": "variant_a", "quality_score": 0.9},
                {"experiment": "exp-1", "variant": "variant_a", "quality_score": 0.83},
                {"experiment": "exp-1", "variant": "variant_a", "quality_score": 0.81},
                {"experiment": "exp-1", "variant": "variant_b", "quality_score": 0.7},
                {"experiment": "exp-1", "variant": "variant_b", "quality_score": 0.72},
                {"experiment": "exp-1", "variant": "variant_b", "quality_score": 0.69},
                {"experiment": "exp-1", "variant": "variant_b", "quality_score": 0.74},
                {"experiment": "exp-1", "variant": "variant_b", "quality_score": 0.71},
            ]
        )
        decisions = RolloutController().determine_winner(summary)
        self.assertEqual(decisions[0]["winner_variant"], "variant_a")


if __name__ == "__main__":
    unittest.main()
