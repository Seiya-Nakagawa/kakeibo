/**
 * Web アプリのエントリポイント (GET)。
 */
function doGet(e) {
  const action = e && e.parameter && e.parameter.action;

  // 初期化API: カテゴリ一覧と直近の取引データを返す
  if (action === 'init') {
    try {
      const categories = getCategories();
      const recent = getRecentTransactions(10);
      return jsonOk_({
        categories: categories,
        recent: recent
      });
    } catch (err) {
      return jsonError_(err.toString());
    }
  }

  // 直近の取引リスト取得API
  if (action === 'list') {
    try {
      const rows = getRecentTransactions(10);
      return jsonOk_(rows);
    } catch (err) {
      return jsonError_(err.toString());
    }
  }

  // 動作確認用
  return jsonOk_({ status: 'ok', message: 'Kakeibo API is running' });
}

/**
 * Web アプリのエントリポイント (POST)。
 * CORSプリフライトを回避するため、フロントエンドからは Content-Type: text/plain でJSON文字列を送信し、
 * ここでパースする。
 */
function doPost(e) {
  try {
    if (!e || !e.postData || !e.postData.contents) {
      return jsonError_('リクエストボディが空です');
    }

    const params = JSON.parse(e.postData.contents);
    const result = apiAddEntry(params);
    return jsonOk_(result);
  } catch (err) {
    return jsonError_(err.toString());
  }
}

/**
 * 支出情報を追加する API。
 */
function apiAddEntry(params) {
  try {
    // 重複チェック用のキーを生成
    const dedupKey = computeHash_(params.date + params.amount + params.shop + 'manual');
    
    // スプレッドシートへ追加
    appendTransaction({
      date: params.date,
      amount: Number(params.amount),
      shop: params.shop,
      source: params.source,
      category: params.category,
      memo: params.memo || '',
      method: 'manual',
      dedupKey: dedupKey
    });
    
    // 集計を更新
    refreshMonthlySummary();
    
    return { success: true };
  } catch (e) {
    return { success: false, error: e.toString() };
  }
}

function jsonOk_(data) {
  return ContentService.createTextOutput(JSON.stringify(data)).setMimeType(ContentService.MimeType.JSON);
}

function jsonError_(message) {
  return jsonOk_({ success: false, error: message });
}
