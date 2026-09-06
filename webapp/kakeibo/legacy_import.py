"""現行スプレッドシートからのデータ移行ロジック（要件4.10、基本設計書6.3節）。

CSVはGoogleスプレッドシートから「ファイル > ダウンロード > カンマ区切り形式(.csv)」で
エクスポートしたものをそのまま使用する。ヘッダー行は読み飛ばし、列はシート上の列順（位置）で
解釈するため、エクスポート前に列を並び替えないこと。

対応するシートと列（旧基本設計書 docs/02.設計/old/DESIGN.md 2章準拠）:
    カテゴリ   : 月次集計シートのA〜C列（カテゴリ名, 月次予算, 集計対象）
    店舗ルール : 店舗ルールシートのA〜B列（店舗名キーワード, カテゴリ名）
    固定費     : 固定費マスタシートのA〜F列（支払先, 金額, カテゴリ名, 決済手段, 開始月, メモ）
    生データ   : 生データシートのA〜H列（日付, 金額, 店舗名, 決済手段, カテゴリ, メモ, 登録方法, 重複排除キー）

旧スプレッドシートは支出のみを扱っており収入区分が存在しないため、移行するカテゴリは
すべて支出区分（Category.CategoryType.EXPENSE）として登録する。収入用カテゴリは
移行完了後に管理画面で追加する。

生データの重複排除キー（H列）はGAS側の生成方式がDjango側（compute_dedup_hash）と異なるため
移行時には使用しない。冪等性の担保方法は登録方法によって異なる。

    auto（メール取込分）  : Django側のcompute_dedup_hashを再計算し、日次メール取込バッチ
                            （import_transactions_from_mailコマンド）と同じ「dedup_hashが
                            既に存在すれば作成しない」方式で判定する。
    manual（手動入力分）  : 手動入力はWeb入力時も元々dedup_hashを持たない（重複チェックを
                            行わない）仕様のため、日付・金額・店舗名・カテゴリ・決済手段・
                            メモの全項目一致を冪等性の判定に用いる。

日付・金額・店舗名・決済手段が偶然一致する別々の取引（例: 同日に同じ店で同額の買い物を
複数回した場合）が実データに存在するため、これらの4項目だけをキーにした重複統合は
行わない（実在する取引を誤って1件に統合してしまう）。
"""

import csv
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from django.db import transaction
from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth

from kakeibo.mail_import import compute_dedup_hash
from kakeibo.models import (
    Category,
    FixedCost,
    PaymentMethod,
    StoreRule,
    Transaction,
    User,
)

CATEGORY_COL = {"NAME": 0, "BUDGET": 1, "INCLUDE": 2}
STORE_RULE_COL = {"KEYWORD": 0, "CATEGORY": 1}
FIXED_COST_COL = {
    "PAYEE": 0,
    "AMOUNT": 1,
    "CATEGORY": 2,
    "PAYMENT_METHOD": 3,
    "START_MONTH": 4,
    "MEMO": 5,
}
TRANSACTION_COL = {
    "DATE": 0,
    "AMOUNT": 1,
    "SHOP": 2,
    "PAYMENT_METHOD": 3,
    "CATEGORY": 4,
    "MEMO": 5,
    "METHOD": 6,
}

LEGACY_METHOD_TO_SOURCE = {
    "auto": Transaction.Source.MAIL,
    "manual": Transaction.Source.MANUAL,
}
LEGACY_METHOD_FIXED = "fixed"

# 固定費マスタの「開始月」が空欄の場合は常時適用を意味するが、FixedCost.start_monthは
# NOT NULLのため、要件5.1.4（過去10年分のデータ保持）より確実に古い日付を割り当てて表現する。
LEGACY_ALWAYS_APPLIED_START_MONTH = date(2000, 1, 1)

FOOTER_ROW_LABEL = "合計"  # 月次集計シートの合計行


class LegacyImportError(Exception):
    """移行データがマスタ未登録等により取り込めない場合のエラー。"""


@dataclass
class UpsertResult:
    created: int = 0
    updated: int = 0


@dataclass
class TransactionImportResult:
    created: int = 0
    skipped_duplicate: int = 0
    skipped_fixed: int = 0
    transaction_ids: set = field(default_factory=set)
    monthly_csv_totals: dict = field(
        default_factory=dict
    )  # "YYYY-MM" -> (count, total)


@dataclass
class MonthlyVerification:
    month: str
    csv_count: int
    db_count: int
    csv_total: int
    db_total: int

    @property
    def matches(self) -> bool:
        return self.csv_count == self.db_count and self.csv_total == self.db_total


def _read_data_rows(csv_path: str, min_columns: int) -> list[list[str]]:
    """ヘッダー行・空行・合計行を除いたデータ行を返す。"""
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    body = rows[1:]
    return [row for row in body if _has_content(row, min_columns)]


def _has_content(row: list[str], min_columns: int) -> bool:
    if len(row) < min_columns:
        return False
    first_cell = row[0].strip()
    return first_cell != "" and first_cell != FOOTER_ROW_LABEL


def _parse_int(value: str) -> int:
    # スプレッドシートの数値セルは桁区切りカンマを含む場合がある。
    return int(value.replace(",", "").strip())


def _parse_legacy_month(value: str) -> date:
    value = value.strip()
    if not value:
        return LEGACY_ALWAYS_APPLIED_START_MONTH
    year_str, month_str = re.split(r"[/-]", value)
    return date(int(year_str), int(month_str), 1)


def _format_missing_masters(
    missing_categories: set, missing_payment_methods: set
) -> str:
    parts = [f"カテゴリ[{c}]" for c in sorted(missing_categories)]
    parts += [f"決済手段[{p}]" for p in sorted(missing_payment_methods)]
    return "、".join(parts)


def _find_expense_category(name: str) -> Category | None:
    return Category.objects.filter(
        name=name, category_type=Category.CategoryType.EXPENSE
    ).first()


def import_categories(csv_path: str) -> UpsertResult:
    """カテゴリ（月次集計シートA〜C列）を取り込む。"""
    result = UpsertResult()
    rows = _read_data_rows(csv_path, min_columns=3)
    with transaction.atomic():
        for display_order, row in enumerate(rows):
            name = row[CATEGORY_COL["NAME"]].strip()
            budget = _parse_int(row[CATEGORY_COL["BUDGET"]])
            is_aggregated = row[CATEGORY_COL["INCLUDE"]].strip().upper() == "TRUE"
            _, created = Category.objects.update_or_create(
                name=name,
                category_type=Category.CategoryType.EXPENSE,
                defaults={
                    "monthly_budget": budget or None,
                    "is_aggregated": is_aggregated,
                    "display_order": display_order,
                },
            )
            if created:
                result.created += 1
            else:
                result.updated += 1
    return result


def import_store_rules(csv_path: str) -> UpsertResult:
    """店舗ルールを取り込む。CSVの行順を優先順位（priority）として採用する。"""
    result = UpsertResult()
    rows = _read_data_rows(csv_path, min_columns=2)
    missing_categories = set()

    with transaction.atomic():
        for priority, row in enumerate(rows, start=1):
            keyword = row[STORE_RULE_COL["KEYWORD"]].strip()
            category_name = row[STORE_RULE_COL["CATEGORY"]].strip()
            category = _find_expense_category(category_name)
            if category is None:
                missing_categories.add(category_name)
                continue

            _, created = StoreRule.objects.update_or_create(
                keyword=keyword,
                defaults={
                    "category": category,
                    "priority": priority,
                    "is_auto_generated": False,
                },
            )
            if created:
                result.created += 1
            else:
                result.updated += 1

        if missing_categories:
            raise LegacyImportError(
                "店舗ルールが参照するカテゴリが未登録です: "
                + "、".join(sorted(missing_categories))
            )
    return result


def import_fixed_costs(csv_path: str) -> UpsertResult:
    """固定費マスタを取り込む。payee + start_monthをキーに冪等更新する。"""
    result = UpsertResult()
    rows = _read_data_rows(csv_path, min_columns=5)
    missing_categories = set()
    missing_payment_methods = set()

    with transaction.atomic():
        for row in rows:
            payee = row[FIXED_COST_COL["PAYEE"]].strip()
            amount = _parse_int(row[FIXED_COST_COL["AMOUNT"]])
            category_name = row[FIXED_COST_COL["CATEGORY"]].strip()
            payment_method_name = row[FIXED_COST_COL["PAYMENT_METHOD"]].strip()
            start_month = _parse_legacy_month(row[FIXED_COST_COL["START_MONTH"]])
            memo = (
                row[FIXED_COST_COL["MEMO"]].strip()
                if len(row) > FIXED_COST_COL["MEMO"]
                else ""
            )

            category = _find_expense_category(category_name)
            if category is None:
                missing_categories.add(category_name)
            payment_method = PaymentMethod.objects.filter(
                name=payment_method_name
            ).first()
            if payment_method is None:
                missing_payment_methods.add(payment_method_name)
            if category is None or payment_method is None:
                continue

            _, created = FixedCost.objects.update_or_create(
                payee=payee,
                start_month=start_month,
                defaults={
                    "amount": amount,
                    "category": category,
                    "payment_method": payment_method,
                    "memo": memo,
                },
            )
            if created:
                result.created += 1
            else:
                result.updated += 1

        if missing_categories or missing_payment_methods:
            raise LegacyImportError(
                "固定費が参照するマスタが未登録です: "
                + _format_missing_masters(missing_categories, missing_payment_methods)
            )
    return result


def import_transactions(csv_path: str, imported_by: User) -> TransactionImportResult:
    """生データ（変動費の取引）を取り込む。

    登録方法（G列）が"fixed"の行は、固定費マスタ側で別途取り込むため取引としては
    登録しない（重複計上の防止）。
    """
    rows = _read_data_rows(csv_path, min_columns=7)
    result = TransactionImportResult()
    csv_monthly = defaultdict(lambda: [0, 0])
    missing_categories = set()
    missing_payment_methods = set()
    parsed_rows = []

    for row in rows:
        method = row[TRANSACTION_COL["METHOD"]].strip()
        if method == LEGACY_METHOD_FIXED:
            result.skipped_fixed += 1
            continue
        source = LEGACY_METHOD_TO_SOURCE.get(method)
        if source is None:
            raise LegacyImportError(f"生データに未知の登録方法があります: {method!r}")

        transaction_date = date.fromisoformat(row[TRANSACTION_COL["DATE"]].strip())
        amount = _parse_int(row[TRANSACTION_COL["AMOUNT"]])
        shop = row[TRANSACTION_COL["SHOP"]].strip()
        payment_method_name = row[TRANSACTION_COL["PAYMENT_METHOD"]].strip()
        category_name = row[TRANSACTION_COL["CATEGORY"]].strip()
        memo = row[TRANSACTION_COL["MEMO"]].strip()

        category = _find_expense_category(category_name)
        if category is None:
            missing_categories.add(category_name)
        payment_method = PaymentMethod.objects.filter(name=payment_method_name).first()
        if payment_method is None:
            missing_payment_methods.add(payment_method_name)
        if category is None or payment_method is None:
            continue

        parsed_rows.append(
            (transaction_date, amount, shop, category, payment_method, memo, source)
        )
        bucket = csv_monthly[transaction_date.strftime("%Y-%m")]
        bucket[0] += 1
        bucket[1] += amount

    if missing_categories or missing_payment_methods:
        raise LegacyImportError(
            "生データが参照するマスタが未登録です: "
            + _format_missing_masters(missing_categories, missing_payment_methods)
        )

    with transaction.atomic():
        for (
            transaction_date,
            amount,
            shop,
            category,
            payment_method,
            memo,
            source,
        ) in parsed_rows:
            _import_one_transaction(
                result,
                transaction_date,
                amount,
                shop,
                category,
                payment_method,
                memo,
                source,
                imported_by,
            )

    result.monthly_csv_totals = {
        month: tuple(counts) for month, counts in csv_monthly.items()
    }
    return result


def _import_one_transaction(
    result: TransactionImportResult,
    transaction_date,
    amount,
    shop,
    category,
    payment_method,
    memo,
    source,
    imported_by: User,
) -> None:
    common_fields = {
        "transaction_type": Transaction.TransactionType.EXPENSE,
        "transaction_date": transaction_date,
        "amount": amount,
        "counterpart": shop,
        "category": category,
        "payment_method": payment_method,
        "memo": memo,
        "source": source,
        "created_by": imported_by,
    }
    if source == Transaction.Source.MAIL:
        dedup_hash = compute_dedup_hash(
            transaction_date, amount, shop, payment_method.name
        )
        existing = Transaction.objects.filter(dedup_hash=dedup_hash).first()
        create_fields = {**common_fields, "dedup_hash": dedup_hash}
    else:
        existing = Transaction.objects.filter(**common_fields).first()
        create_fields = common_fields

    if existing is not None:
        result.skipped_duplicate += 1
        result.transaction_ids.add(existing.id)
        return

    created_transaction = Transaction.objects.create(**create_fields)
    result.transaction_ids.add(created_transaction.id)
    result.created += 1


def verify_transactions(result: TransactionImportResult) -> list[MonthlyVerification]:
    """要件4.10.3: 月次の件数・合計金額がCSVとDBで一致することを検証する。"""
    db_rows = (
        Transaction.objects.filter(id__in=result.transaction_ids)
        .annotate(month=TruncMonth("transaction_date"))
        .values("month")
        .annotate(count=Count("id"), total=Sum("amount"))
    )
    db_by_month = {
        row["month"].strftime("%Y-%m"): (row["count"], row["total"]) for row in db_rows
    }

    months = sorted(set(result.monthly_csv_totals) | set(db_by_month))
    verifications = []
    for month in months:
        csv_count, csv_total = result.monthly_csv_totals.get(month, (0, 0))
        db_count, db_total = db_by_month.get(month, (0, 0))
        verifications.append(
            MonthlyVerification(month, csv_count, db_count, csv_total, db_total)
        )
    return verifications
