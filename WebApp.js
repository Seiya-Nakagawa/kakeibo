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
  const token = e && e.parameter && e.parameter.token;

  // 認証チェック
  const session = getSession_(token);

  if (!session) {
    return HtmlService.createHtmlOutput(buildLoginHtml_())
      .setTitle('家計簿 - ログイン')
      .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
  }

  if (action === 'list') {
    const rows = getRecentTransactions(10);
    return jsonOk_(rows);
  }

  const categories = getCategories();
  const html = buildHtml_(categories, token);
  return HtmlService.createHtmlOutput(html)
    .setTitle('家計簿 - 手動入力')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}

/**
 * POST リクエストを処理する。
 */
function doPost(e) {
  // fetch 経由の POST はリダイレクトの問題があるため、
  // 基本的に google.script.run を推奨しますが、互換性のために残します。
  const res = doHttpPost_(e.parameter);
  if (res.error) return jsonError_(res.error);
  return jsonOk_(res);
}

/**
 * POST 処理の共通ロジック
 */
function doHttpPost_(params) {
  const action = params.action;
  const token = params.token;

  if (action === 'login') {
    const password = params.password;
    if (password === getWebPassword()) {
      const newToken = Utilities.getUuid();
      setSession_(newToken);
      return { token: newToken };
    } else {
      return { error: 'パスワードが違います。' };
    }
  }

  if (!getSession_(token)) {
    return { error: 'セッションの期限が切れました。再ログインしてください。' };
  }

  if (action === 'delete') {
    const rowNumber = parseInt(params.rowNumber, 10);
    if (!rowNumber || rowNumber < 2) return { error: '無効な行番号です。' };
    deleteTransactionByRow(rowNumber);
    return { message: '削除しました。' };
  }

  // 登録処理
  const { date, amount, shop, category, source, memo } = params;
  if (!date || !amount || !shop || !category || !source) {
    return { error: '必須項目が不足しています。' };
  }

  const parsedAmount = parseInt(amount, 10);
  if (isNaN(parsedAmount) || parsedAmount <= 0) {
    return { error: '金額が不正です。' };
  }

  const dedupKey = computeHash_(date + parsedAmount + shop + source);
  if (isDuplicateHash(dedupKey)) {
    return { error: '同じ内容がすでに登録されています。' };
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

  return { message: '登録しました。' };
}

// ---- google.script.run 用の API 関数 ----

function apiLogin(password) {
  return doHttpPost_({ action: 'login', password: password });
}

function apiAddEntry(params) {
  return doHttpPost_(params);
}

function apiDeleteEntry(rowNumber, token) {
  return doHttpPost_({ action: 'delete', rowNumber: rowNumber, token: token });
}

// ---- プライベートヘルパー ----

/**
 * 手動入力画面の HTML 文字列を生成する。
 *
 * @param {string[]} categories  カテゴリ名の配列
 * @returns {string}
 */
function buildHtml_(categories, token) {
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
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap" rel="stylesheet">
  <style>
    :root {
      --primary: #2563eb;
      --primary-hover: #1d4ed8;
      --bg: #f1f5f9;
      --card-bg: #ffffff;
      --text-main: #1e293b;
      --text-muted: #64748b;
      --border: #e2e8f0;
      --success: #10b981;
      --error: #ef4444;
    }
    *, *::before, *::after { box-sizing: border-box; }
    body {
      font-family: 'Inter', system-ui, -apple-system, sans-serif;
      background-color: var(--bg);
      color: var(--text-main);
      margin: 0;
      padding: 0;
      line-height: 1.5;
    }
    
    header {
      background: white;
      padding: 1rem 1.5rem;
      border-bottom: 1px solid var(--border);
      display: flex;
      justify-content: space-between;
      align-items: center;
      position: sticky;
      top: 0;
      z-index: 10;
    }
    header h1 { font-size: 1.25rem; font-weight: 600; margin: 0; }
    .logout-btn {
      font-size: 0.875rem;
      color: var(--text-muted);
      cursor: pointer;
      padding: 0.5rem 1rem;
      border-radius: 0.5rem;
      border: 1px solid var(--border);
      background: transparent;
      transition: all 0.2s;
    }
    .logout-btn:hover { background: #fee2e2; color: #b91c1c; border-color: #fecaca; }

    main { max-width: 640px; margin: 2rem auto; padding: 0 1rem; }
    
    section {
      background: var(--card-bg);
      border-radius: 1rem;
      padding: 1.5rem;
      margin-bottom: 2rem;
      box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px 0 rgba(0, 0, 0, 0.06);
    }
    h2 { font-size: 1rem; font-weight: 600; margin-top: 0; margin-bottom: 1.25rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; }

    label { display: block; font-size: 0.875rem; font-weight: 600; margin-bottom: 0.5rem; color: var(--text-muted); }
    input, select {
      width: 100%;
      padding: 0.625rem 0.875rem;
      border: 1px solid var(--border);
      border-radius: 0.5rem;
      font-size: 1rem;
      margin-bottom: 1.25rem;
      outline: none;
      transition: border-color 0.2s;
    }
    input:focus, select:focus { border-color: var(--primary); box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1); }
    
    .amount-wrap { position: relative; display: flex; align-items: center; }
    .amount-wrap input { margin-bottom: 0; padding-right: 3rem; }
    .amount-unit { position: absolute; right: 1rem; color: var(--text-muted); pointer-events: none; }

    .submit-btn {
      width: 100%;
      background: var(--primary);
      color: white;
      border: none;
      padding: 0.75rem;
      border-radius: 0.5rem;
      font-size: 1rem;
      font-weight: 600;
      cursor: pointer;
      transition: background 0.2s;
      margin-top: 0.5rem;
    }
    .submit-btn:hover { background: var(--primary-hover); }
    
    #message {
      margin-top: 1rem;
      padding: 0.75rem;
      border-radius: 0.5rem;
      font-size: 0.875rem;
      display: none;
    }
    #message.ok { display: block; background: #ecfdf5; color: #065f46; border: 1px solid #d1fae5; }
    #message.err { display: block; background: #fef2f2; color: #991b1b; border: 1px solid #fee2e2; }

    .table-container { overflow-x: auto; margin: -1.5rem; margin-top: 0; }
    table { width: 100%; border-collapse: collapse; font-size: 0.875rem; }
    th { text-align: left; padding: 0.75rem 1rem; background: #f8fafc; color: var(--text-muted); font-weight: 600; border-bottom: 1px solid var(--border); }
    td { padding: 0.75rem 1rem; border-bottom: 1px solid var(--border); }
    tr:last-child td { border-bottom: none; }
    .del-btn {
      background: #fee2e2;
      color: #dc2626;
      border: none;
      border-radius: 0.375rem;
      padding: 0.25rem 0.5rem;
      cursor: pointer;
      font-weight: 600;
      transition: all 0.2s;
    }
    .del-btn:hover { background: #fecaca; }

    @media (max-width: 480px) {
      main { margin: 1rem auto; }
      header { padding: 0.75rem 1rem; }
    }
  </style>
</head>
<body>
  <header>
    <h1>🏠 Kakeibo</h1>
    <button class="logout-btn" onclick="logout()">ログアウト</button>
  </header>

  <main>
    <section>
      <h2>支出を入力</h2>
      <form id="entryForm">
        <label>日付</label>
        <input type="date" name="date" value="${today}" required>

        <label>金額</label>
        <div class="amount-wrap" style="margin-bottom: 1.25rem;">
          <input type="number" name="amount" min="1" placeholder="0" required>
          <span class="amount-unit">JPY</span>
        </div>

        <label>店舗名</label>
        <input type="text" name="shop" placeholder="例: セブンイレブン 渋谷店" required>

        <label>カテゴリ</label>
        <select name="category" required>
          <option value="">-- 手動選択 --</option>
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
        <input type="text" name="memo" placeholder="...">

        <button type="submit" class="submit-btn" id="submitBtn">登録する</button>
        <div id="message"></div>
      </form>
    </section>

    <section>
      <h2 style="display: flex; justify-content: space-between; align-items: center;">
        履歴（直近10件）
        <span style="font-size: 0.75rem; font-weight: normal; cursor: pointer; color: var(--primary);" onclick="loadRecent()">更新</span>
      </h2>
      <div class="table-container">
        <table id="recentTable">
          <thead>
            <tr><th>日付</th><th>カテゴリ</th><th style="text-align:right">金額</th><th>削除</th></tr>
          </thead>
          <tbody id="recentBody"></tbody>
        </table>
      </div>
    </section>
  </main>

  <script>
    const token = '${token}';
    const scriptUrl = window.location.href.split('?')[0];

    function logout() {
      localStorage.removeItem('kakeibo_token');
      window.location.href = scriptUrl;
    }

    function showMessage(text, isOk) {
      const el = document.getElementById('message');
      el.textContent = text;
      el.className = isOk ? 'ok' : 'err';
      setTimeout(() => { el.style.display = 'none'; }, 5000);
    }

    async function loadRecent() {
      // GET はリダイレクトが問題にならないため fetch を維持
      const url = scriptUrl + '?action=list&token=' + token;
      try {
        const r = await fetch(url);
        const rows = await r.json();
        const tbody = document.getElementById('recentBody');
        tbody.innerHTML = '';
        rows.forEach((row) => {
          const tr = document.createElement('tr');
          tr.innerHTML =
            '<td style="white-space:nowrap">' + row.date + '</td>' +
            '<td><span style="font-size:0.75rem; color:#64748b">' + escapeHtml(row.shop) + '</span><br>' + escapeHtml(row.category) + '</td>' +
            '<td style="text-align:right; font-weight:600">' + Number(row.amount).toLocaleString() + '</td>' +
            '<td><button class="del-btn" data-row="' + row.rowNumber + '">×</button></td>';
          tbody.appendChild(tr);
        });
        document.querySelectorAll('.del-btn').forEach((btn) => {
          btn.addEventListener('click', (e) => deleteRow(e.target.dataset.row));
        });
      } catch (e) {}
    }

    function deleteRow(rowNumber) {
      if (!confirm('この行を削除しますか？')) return;
      const btn = event.target;
      btn.disabled = true;

      google.script.run
        .withSuccessHandler((res) => {
          showMessage(res.message || '削除しました。', !res.error);
          loadRecent();
        })
        .withFailureHandler(() => {
          showMessage('削除に失敗しました。', false);
          btn.disabled = false;
        })
        .apiDeleteEntry(rowNumber, token);
    }

    document.getElementById('entryForm').addEventListener('submit', (ev) => {
      ev.preventDefault();
      const btn = document.getElementById('submitBtn');
      btn.disabled = true;
      btn.textContent = '登録中...';

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
 * セッションを検証する。
 *
 * @param {string} token
 * @returns {boolean}
 */
function getSession_(token) {
  if (!token) return false;
  const session = CacheService.getScriptCache().get('session_' + token);
  return session === 'authenticated';
}

/**
 * セッションを保存する（6時間有効）。
 *
 * @param {string} token
 */
function setSession_(token) {
  CacheService.getScriptCache().put('session_' + token, 'authenticated', 21600);
}

/**
 * ログイン画面の HTML 文字列を生成する。
 *
 * @returns {string}
 */
function buildLoginHtml_() {
  return `<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>ログイン - 家計簿</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap" rel="stylesheet">
  <style>
    :root {
      --primary: #2563eb;
      --primary-hover: #1d4ed8;
      --bg: #f8fafc;
      --card-bg: #ffffff;
      --text-main: #1e293b;
      --text-muted: #64748b;
      --error: #ef4444;
    }
    *, *::before, *::after { box-sizing: border-box; }
    body {
      font-family: 'Inter', -apple-system, sans-serif;
      background: linear-gradient(135deg, #e2e8f0 0%, #cbd5e1 100%);
      height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      margin: 0;
      color: var(--text-main);
    }
    .login-card {
      background: var(--card-bg);
      padding: 2.5rem;
      border-radius: 1.5rem;
      box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
      width: 100%;
      max-width: 400px;
      text-align: center;
      animation: slideUp 0.5s ease-out;
    }
    @keyframes slideUp {
      from { opacity: 0; transform: translateY(20px); }
      to { opacity: 1; transform: translateY(0); }
    }
    h1 { font-size: 1.75rem; font-weight: 600; margin-bottom: 0.5rem; color: var(--text-main); }
    p { color: var(--text-muted); margin-bottom: 2rem; font-size: 0.95rem; }
    .form-group { text-align: left; margin-bottom: 1.5rem; }
    label { display: block; font-size: 0.875rem; font-weight: 600; margin-bottom: 0.5rem; color: var(--text-muted); }
    input {
      width: 100%;
      padding: 0.75rem 1rem;
      border: 1px solid #e2e8f0;
      border-radius: 0.75rem;
      font-size: 1rem;
      transition: all 0.2s;
      outline: none;
    }
    input:focus {
      border-color: var(--primary);
      box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1);
    }
    button {
      width: 100%;
      background: var(--primary);
      color: white;
      border: none;
      padding: 0.75rem;
      border-radius: 0.75rem;
      font-size: 1rem;
      font-weight: 600;
      cursor: pointer;
      transition: background 0.2s;
    }
    button:hover { background: var(--primary-hover); }
    button:active { transform: scale(0.98); }
    #message { margin-top: 1rem; font-size: 0.875rem; color: var(--error); min-height: 1.25rem; }
    
    /* Loading animation */
    .loading { pointer-events: none; opacity: 0.7; }
  </style>
</head>
<body>
  <div class="login-card">
    <h1>🏠 Kakeibo</h1>
    <p>管理画面へログイン</p>
    <form id="loginForm">
      <div class="form-group">
        <label for="password">パスワード</label>
        <input type="password" id="password" name="password" placeholder="••••••••" required autofocus>
      </div>
      <button type="submit" id="submitBtn">ログイン</button>
      <div id="message"></div>
    </form>
  </div>

  <script>
    const loginForm = document.getElementById('loginForm');
    const submitBtn = document.getElementById('submitBtn');
    const messageEl = document.getElementById('message');

    loginForm.addEventListener('submit', (e) => {
      e.preventDefault();
      
      messageEl.textContent = '';
      submitBtn.classList.add('loading');
      submitBtn.textContent = '認証中...';

      const password = document.getElementById('password').value;

      google.script.run
        .withSuccessHandler((result) => {
          if (result.token) {
            localStorage.setItem('kakeibo_token', result.token);
            const url = new URL(window.location.href);
            url.searchParams.set('token', result.token);
            window.location.href = url.toString();
          } else {
            messageEl.textContent = result.error || 'ログインに失敗しました。';
          }
          submitBtn.classList.remove('loading');
          submitBtn.textContent = 'ログイン';
        })
        .withFailureHandler(() => {
          messageEl.textContent = '通信エラーが発生しました。';
          submitBtn.classList.remove('loading');
          submitBtn.textContent = 'ログイン';
        })
        .apiLogin(password);
    });

    // 画面中央に遷移させるエフェクト
    window.addEventListener('load', () => {
      document.body.style.opacity = 1;
    });
  </script>
</body>
</html>`;
}
