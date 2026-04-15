/**
 * CategoryHandler.js - カテゴリ判定
 *
 * 主要な関数:
 *   getCategory(shopName)   : 店舗名からカテゴリを判定する
 *   callGeminiApi(shopName) : Gemini API でカテゴリを推定する
 */

/**
 * 店舗名からカテゴリを判定する。
 *
 * 判定優先順位:
 *   1. 店舗ルールシートを上から順に部分一致で検索
 *   2. ルール未ヒットの場合は Gemini API にフォールバック
 *
 * @param {string} shopName
 * @returns {{ category: string, method: 'rule' | 'llm' }}
 */
function getCategory(shopName) {
  const rules = getShopRules();
  const normalizedShop = normalizeStr(shopName);

  for (const [keyword, category] of rules) {
    if (!keyword) continue;
    if (normalizedShop.includes(normalizeStr(String(keyword)))) {
      return { category: String(category), method: 'rule' };
    }
  }

  const category = callGeminiApi(shopName);
  return { category, method: 'llm' };
}

/**
 * Gemini API を使って店舗名からカテゴリを推定する。
 * カテゴリマスタの一覧をプロンプトに埋め込み、リストから1つだけ選ばせる。
 *
 * @param {string} shopName
 * @returns {string}  カテゴリ名（取得できなかった場合は "その他"）
 */
function callGeminiApi(shopName) {
  const apiKey = getGeminiApiKey();
  const categories = getCategories();
  const categoryList = categories.join('、');

  const prompt =
    '以下の店舗名を、家計簿のカテゴリに分類してください。\n' +
    'カテゴリは必ず次のリストから1つだけ選んでください: ' +
    categoryList +
    '\n\n店舗名: ' +
    shopName +
    '\n\nカテゴリ名のみ返答してください。';

  const url =
    'https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=' +
    apiKey;

  const payload = {
    contents: [{ parts: [{ text: prompt }] }],
    generationConfig: { temperature: 0, maxOutputTokens: 64 },
  };

  try {
    const response = UrlFetchApp.fetch(url, {
      method: 'post',
      contentType: 'application/json',
      payload: JSON.stringify(payload),
      muteHttpExceptions: true,
    });

    const json = JSON.parse(response.getContentText());
    const text =
      json?.candidates?.[0]?.content?.parts?.[0]?.text?.trim() ?? '';

    if (categories.includes(text)) {
      return text;
    }

    // カテゴリ一覧に含まれない回答の場合、部分一致で拾う
    const matched = categories.find((c) => text.includes(c));
    return matched || 'その他';
  } catch (e) {
    console.error('Gemini API エラー:', e.message);
    return 'その他';
  }
}

/**
 * 店舗名からルール登録用キーワードを抽出する。
 * 全角・半角スペースで分割し、先頭トークン（チェーン名部分）を返す。
 * スペースがない場合は店舗名をそのまま返す。
 *
 * 例: "ベルク　座間南栗原店" → "ベルク"
 *     "マクドナルド 新宿東口店" → "マクドナルド"
 *     "セブンイレブン" → "セブンイレブン"
 *
 * @param {string} shopName
 * @returns {string}
 */
function extractShopKeyword(shopName) {
  const firstToken = shopName.split(/[ 　]/)[0];
  return firstToken && firstToken !== shopName ? firstToken : shopName;
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
