from django.test import TestCase

from kakeibo.categorization import (
    extract_keyword,
    match_category,
    register_learned_rule,
)
from kakeibo.models import Category, StoreRule


class NormalizationMatchTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(
            name="食費", category_type=Category.CategoryType.EXPENSE
        )

    def test_full_width_and_case_are_normalized_before_matching(self):
        StoreRule.objects.create(
            keyword="seven-eleven", category=self.category, priority=1
        )
        # 全角・大文字小文字が異なっていても一致する。
        matched = match_category("ＳＥＶＥＮ-ＥＬＥＶＥＮ新宿三丁目店")
        self.assertEqual(matched, self.category)

    def test_no_match_returns_none(self):
        self.assertIsNone(match_category("未登録の店舗"))

    def test_priority_order_is_respected(self):
        other_category = Category.objects.create(
            name="日用品", category_type=Category.CategoryType.EXPENSE
        )
        StoreRule.objects.create(
            keyword="ドラッグストア", category=other_category, priority=1
        )
        StoreRule.objects.create(
            keyword="ドラッグストアA", category=self.category, priority=2
        )
        matched = match_category("ドラッグストアA新宿店")
        self.assertEqual(matched, other_category)


class KeywordExtractionTests(TestCase):
    def test_extract_keyword_uses_full_normalized_name(self):
        self.assertEqual(
            extract_keyword("ｾﾌﾞﾝ-ｲﾚﾌﾞﾝ新宿三丁目店"), "セブン-イレブン新宿三丁目店"
        )


class RegisterLearnedRuleTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(
            name="食費", category_type=Category.CategoryType.EXPENSE
        )

    def test_creates_auto_generated_rule(self):
        rule = register_learned_rule(self.category, "セブン-イレブン新宿三丁目店")
        self.assertTrue(rule.is_auto_generated)
        self.assertEqual(rule.category, self.category)
        self.assertTrue(match_category("セブン-イレブン新宿三丁目店"))

    def test_appends_after_existing_priorities(self):
        StoreRule.objects.create(
            keyword="既存ルール", category=self.category, priority=5
        )
        rule = register_learned_rule(self.category, "新しい店舗")
        self.assertEqual(rule.priority, 6)

    def test_reassigning_same_store_updates_existing_rule(self):
        other_category = Category.objects.create(
            name="日用品", category_type=Category.CategoryType.EXPENSE
        )
        first = register_learned_rule(self.category, "同じ店舗")
        second = register_learned_rule(other_category, "同じ店舗")
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(StoreRule.objects.filter(keyword="同じ店舗").count(), 1)
