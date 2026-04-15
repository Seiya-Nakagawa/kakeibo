/**
 * WebApp.js - Web アプリ（手動入力画面）
 *
 * エンドポイント:
 *   doGet()                     : HTML 画面を返す（カテゴリ一覧を埋め込む）
 *   doGet(?action=list)         : 直近10件を JSON で返す
 *   doPost()                    : フォーム入力を生データシートに登録する
 *   doPost(?action=delete)      : 指定行を削除する
 */

/**
 * GET リクエストを処理する。
 * action=list の場合は直近10件を JSON で返す。
 * それ以外は手動入力 HTML 画面を返す。
 *
 * @param {GoogleAppsScript.Events.AppsScriptHttpRequestEvent} e
 * @returns {GoogleAppsScript.HTML.HtmlOutput | GoogleAppsScript.Content.TextOutput}
 */
function doGet(e) {
  const action = e && e.parameter && e.parameter.action;

  if (action === 'list') {
    const rows = getRecentTransactions(10);
    return ContentService.createTextOutput(JSON.stringify(rows)).setMimeType(
      ContentService.MimeType.JSON
    );
  }

  const categories = getCategories();
  const html = buildHtml_(categories);
  return HtmlService.createHtmlOutput(html)
    .setTitle('家計簿 - 手動入力')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}

/**
 * POST リクエストを処理する。
 * action=delete の場合は指定行を削除する。
 * それ以外はフォームデータを生データシートに追加する。
 *
 * @param {GoogleAppsScript.Events.AppsScriptHttpRequestEvent} e
 * @returns {GoogleAppsScript.Content.TextOutput}
 */
function doPost(e) {
  const action = e && e.parameter && e.parameter.action;

  if (action === 'delete') {
    const rowNumber = parseInt(e.parameter.rowNumber, 10);
    if (!rowNumber || rowNumber < 2) {
      return jsonError_('無効な行番号です。');
    }
    deleteTransactionByRow(rowNumber);
    return jsonOk_({ message: '削除しました。' });
  }

  // 登録処理
  const { date, amount, shop, category, source, memo } = e.parameter;

  if (!date || !amount || !shop || !category || !source) {
    return jsonError_('必須項目が不足しています。');
  }

  const parsedAmount = parseInt(amount, 10);
  if (isNaN(parsedAmount) || parsedAmount <= 0) {
    return jsonError_('金額が不正です。');
  }

  const dedupKey = computeHash_(date + parsedAmount + shop + source);

  if (isDuplicateHash(dedupKey)) {
    return jsonError_('同じ内容がすでに登録されています。');
  }

  appendTransaction(
    {
      date,
      amount: parsedAmount,
      shop,
      source,
      category,
      memo: memo || '',
      method: 'manual',
      dedupKey,
    },
    false
  );

  return jsonOk_({ message: '登録しました。' });
}

// ---- プライベートヘルパー ----

/**
 * 手動入力画面の HTML 文字列を生成する。
 *
 * @param {string[]} categories  カテゴリ名の配列
 * @returns {string}
 */
function buildHtml_(categories) {
  const today = Utilities.formatDate(new Date(), 'Asia/Tokyo', 'yyyy-MM-dd');
  const categoryOptions = categories
    .map((c) => '<option value="' + escapeHtml_(c) + '">' + escapeHtml_(c) + '</option>')
    .join('\n');

  return `<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>家計簿 - 手動入力</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; }
    body { font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 16px; background: #f5f5f5; }
    h1 { font-size: 1.2rem; border-bottom: 2px solid #333; padding-bottom: 8px; }
    section { background: #fff; border-radius: 8px; padding: 16px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
    label { display: block; font-size: 0.85rem; color: #555; margin-bottom: 4px; }
    input, select { width: 100%; padding: 8px; border: 1px solid #ccc; border-radius: 4px; font-size: 1rem; margin-bottom: 12px; }
    .amount-wrap { display: flex; align-items: center; gap: 8px; }
    .amount-wrap input { margin-bottom: 0; }
    .amount-unit { white-space: nowrap; }
    button { background: #1a73e8; color: #fff; border: none; border-radius: 4px; padding: 10px 24px; font-size: 1rem; cursor: pointer; }
    button:hover { background: #1558b0; }
    #message { margin-top: 8px; font-size: 0.9rem; }
    .ok  { color: green; }
    .err { color: red; }
    table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
    th, td { text-align: left; padding: 6px 4px; border-bottom: 1px solid #eee; }
    th { background: #f0f0f0; }
    .del-btn { background: #e53935; color: #fff; border: none; border-radius: 3px; padding: 2px 8px; cursor: pointer; }
  </style>
</head>
<body>
  <h1>家計簿 - 手動入力</h1>

  <section>
    <form id="entryForm">
      <label>日付</label>
      <input type="date" name="date" value="${today}" required>

      <label>金額</label>
      <div class="amount-wrap">
        <input type="number" name="amount" min="1" placeholder="0" required>
        <span class="amount-unit">円</span>
      </div>

      <label>店舗名</label>
      <input type="text" name="shop" placeholder="例: セブンイレブン 渋谷店" required>

      <label>カテゴリ</label>
      <select name="category" required>
        <option value="">-- 選択 --</option>
        ${categoryOptions}
      </select>

      <label>決済手段</label>
      <select name="source" required>
        <option value="現金">現金</option>
        <option value="楽天ペイ">楽天ペイ</option>
        <option value="楽天カード">楽天カード</option>
        <option value="口座引落">口座引落</option>
        <option value="その他">その他</option>
      </select>

      <label>メモ（任意）</label>
      <input type="text" name="memo" placeholder="">

      <button type="submit">登録する</button>
      <div id="message"></div>
    </form>
  </section>

  <section>
    <h2 style="font-size:1rem; margin-top:0;">直近の登録（10件）</h2>
    <table id="recentTable">
      <thead>
        <tr><th>日付</th><th>金額</th><th>店舗名</th><th>カテゴリ</th><th>削除</th></tr>
      </thead>
      <tbody id="recentBody"></tbody>
    </table>
  </section>

  <script>
    const scriptUrl = window.location.href.split('?')[0];

    function showMessage(text, isOk) {
      const el = document.getElementById('message');
      el.textContent = text;
      el.className = isOk ? 'ok' : 'err';
    }

    function loadRecent() {
      fetch(scriptUrl + '?action=list')
        .then((r) => r.json())
        .then((rows) => {
          const tbody = document.getElementById('recentBody');
          tbody.innerHTML = '';
          rows.forEach((row) => {
            const tr = document.createElement('tr');
            tr.innerHTML =
              '<td>' + (row.date instanceof Object ? row.date : row.date) + '</td>' +
              '<td style="text-align:right">' + Number(row.amount).toLocaleString() + '</td>' +
              '<td>' + escapeHtml(row.shop) + '</td>' +
              '<td>' + escapeHtml(row.category) + '</td>' +
              '<td><button class="del-btn" data-row="' + row.rowNumber + '">×</button></td>';
            tbody.appendChild(tr);
          });
          document.querySelectorAll('.del-btn').forEach((btn) => {
            btn.addEventListener('click', () => deleteRow(btn.dataset.row));
          });
        })
        .catch(() => {});
    }

    function deleteRow(rowNumber) {
      if (!confirm('この行を削除しますか？')) return;
      const params = new URLSearchParams({ action: 'delete', rowNumber });
      fetch(scriptUrl, { method: 'POST', body: params })
        .then((r) => r.json())
        .then((res) => {
          showMessage(res.message || '削除しました。', !res.error);
          loadRecent();
        })
        .catch(() => showMessage('削除に失敗しました。', false));
    }

    document.getElementById('entryForm').addEventListener('submit', (ev) => {
      ev.preventDefault();
      const data = new FormData(ev.target);
      const params = new URLSearchParams(data);
      fetch(scriptUrl, { method: 'POST', body: params })
        .then((r) => r.json())
        .then((res) => {
          showMessage(res.message || (res.error ? res.error : '登録しました。'), !res.error);
          if (!res.error) {
            ev.target.reset();
            document.querySelector('[name=date]').value = '${today}';
            loadRecent();
          }
        })
        .catch(() => showMessage('登録に失敗しました。', false));
    });

    function escapeHtml(str) {
      return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
    }

    loadRecent();
  </script>
</body>
</html>`;
}

/**
 * 成功レスポンスの JSON を返す。
 *
 * @param {Object} data
 * @returns {GoogleAppsScript.Content.TextOutput}
 */
function jsonOk_(data) {
  return ContentService.createTextOutput(JSON.stringify(data)).setMimeType(
    ContentService.MimeType.JSON
  );
}

/**
 * エラーレスポンスの JSON を返す。
 *
 * @param {string} message
 * @returns {GoogleAppsScript.Content.TextOutput}
 */
function jsonError_(message) {
  return ContentService.createTextOutput(
    JSON.stringify({ error: message })
  ).setMimeType(ContentService.MimeType.JSON);
}

/**
 * HTML 特殊文字をエスケープする。
 *
 * @param {string} str
 * @returns {string}
 */
function escapeHtml_(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
