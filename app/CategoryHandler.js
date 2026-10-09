/**
 * CategoryHandler.js - カテゴリ判定
 *
 * 主要な関数:
 *   getCategory(shopName) : 店舗名からカテゴリを判定する
 */

/**
 * 店舗名からカテゴリを判定する。
 *
 * 判定優先順位:
 *   1. 店舗ルールシートを上から順に部分一致で検索
 *   2. ルール未ヒットの場合は「その他」とする
 *
 * @param {string} shopName
 * @returns {string}  カテゴリ名
 */
function getCategory(shopName) {
  const rules = getShopRules();
  const normalizedShop = normalizeStr(shopName);

  for (const [keyword, category] of rules) {
    if (!keyword) continue;
    if (normalizedShop.includes(normalizeStr(String(keyword)))) {
      return String(category);
    }
  }

  return 'その他';
}

/**
 * 文字列を正規化する（全角英数字→半角、大文字→小文字）。
 *
 * @param {string} str
 * @returns {string}
 */
function normalizeStr(str) {
  return str
    .replace(/[Ａ-Ｚａ-ｚ０-９]/g, (s) =>
      String.fromCharCode(s.charCodeAt(0) - 0xfee0)
    )
    .toLowerCase();
}
