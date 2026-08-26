"""カテゴリ判定・自動学習ロジック（基本設計書3.2節）。"""

import unicodedata

from django.db.models import Max

from kakeibo.models import Category, StoreRule


def normalize_store_name(value: str) -> str:
    """店舗名・キーワードの正規化（全角半角・大文字小文字の統一）。"""
    return unicodedata.normalize("NFKC", value).upper().strip()


def match_category(counterpart: str) -> Category | None:
    """店舗ルールに基づきカテゴリを判定する。一致しない場合はNone（未分類）を返す。"""
    normalized_counterpart = normalize_store_name(counterpart)
    for rule in StoreRule.objects.select_related("category").order_by("priority"):
        if normalize_store_name(rule.keyword) in normalized_counterpart:
            return rule.category
    return None


def extract_keyword(counterpart: str) -> str:
    """未分類取引へのカテゴリ割当時、店舗名から自動学習用キーワードを抽出する。

    実データ（決済通知メールの実際の店舗名表記）が確認できていないため、
    店舗名（正規化済み）全体をキーワードとして採用する保守的な規則とする
    （Issue #16、実データ確認後に見直す可能性がある）。
    """
    return normalize_store_name(counterpart)


def register_learned_rule(category: Category, counterpart: str) -> StoreRule:
    """未分類取引へのカテゴリ割当時、店舗ルールへ自動登録する（要件4.2.6）。"""
    keyword = extract_keyword(counterpart)
    next_priority = (
        StoreRule.objects.aggregate(Max("priority"))["priority__max"] or 0
    ) + 1
    rule, _ = StoreRule.objects.update_or_create(
        keyword=keyword,
        defaults={
            "category": category,
            "is_auto_generated": True,
            "priority": next_priority,
        },
    )
    return rule
