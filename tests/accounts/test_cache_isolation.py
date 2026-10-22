"""
Test suite validating cache isolation between test cases per TL-52.
"""

from django.core.cache import cache
from django.test import TestCase


class CachePollutionPredecessorTest(TestCase):
    def test_step_1_set_dirty_cache(self):
        cache.set("sentinel_test_key", "polluted_value", timeout=600)
        self.assertEqual(cache.get("sentinel_test_key"), "polluted_value")


class CachePollutionSuccessorTest(TestCase):
    def test_step_2_verify_clean_cache_at_start(self):
        self.assertIsNone(
            cache.get("sentinel_test_key"),
            "Cache was not cleared before test execution! Missing autouse fixture.",
        )
