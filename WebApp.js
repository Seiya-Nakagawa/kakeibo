/**
 * Web アプリのエントリポイント。
 */
function doGet(e) {
  const action = e && e.parameter && e.parameter.action;

  if (action === 'list') {
    const rows = getRecentTransactions(10);
    return jsonOk_(rows);
  }

  const categories = getCategories();
  const html = buildHtml_(categories);
  return HtmlService.createHtmlOutput(html);
}

/**
 * 手動入力画面の HTML 文字列を生成する。
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
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>家計簿</title>
  <style>
    html, body {
      width: 100%;
      height: 100%;
      margin: 0;
      padding: 0;
      background: #ffffff;
      color: #1e293b;
      font-family: -apple-system, BlinkMacSystemFont, sans-serif;
      font-size: 20px; /* 全体の基準をさらにアップ */
    }
    .container {
      width: 100%;
      padding: 0 16px 40px;
      box-sizing: border-box;
    }
    .app-header {
      padding: 30px 0 10px;
      text-align: center;
    }
    .app-header h1 { font-size: 2.2rem; margin: 0; }
    
    .form-container {
      width: 100%;
    }
    
    label {
      display: block;
      font-size: 1.5rem; /* 超特大 */
      font-weight: 900;
      margin: 30px 0 10px;
      color: #334155;
    }
    input, select {
      width: 100%;
      height: 80px; /* 究極の高さ */
      padding: 0 20px;
      border: 3px solid #e2e8f0;
      border-radius: 18px;
      font-size: 24px; /* 入力文字も巨大に */
      box-sizing: border-box;
      background: #fff;
      -webkit-appearance: none;
    }
    input:focus, select:focus { border-color: #2563eb; outline: none; }
    
    .btn {
      width: 100%;
      height: 90px; /* 特大ボタン */
      background: #2563eb;
      color: #fff;
      border: none;
      border-radius: 20px;
      font-size: 1.8rem;
      font-weight: 900;
      margin-top: 50px;
      cursor: pointer;
      box-shadow: 0 10px 20px rgba(37,99,235,0.3);
    }
    .btn:active { transform: scale(0.96); opacity: 0.9; }
    
    #message { margin-top: 30px; padding: 20px; border-radius: 12px; display: none; text-align: center; font-weight: 800; font-size: 1.2rem; }
  </style>
</head>
<body>
  <div class="container">
    <div class="app-header">
      <h1>💰 家計簿入力</h1>
    </div>
    
    <div class="form-container">
      <form id="entryForm">
        <label>📅 日付 <span id="dayOfWeek" style="font-weight: normal; font-size: 1.2rem; margin-left: 10px; color: #64748b;"></span></label>
        <input type="date" name="date" value="${today}" required>
        
        <label>💴 金額</label>
        <input type="number" name="amount" placeholder="0" inputmode="numeric" required>
        
        <label>🛒 店舗・内容</label>
        <input type="text" name="shop" placeholder="どこで？" required>
        
        <label>🏷️ カテゴリ</label>
        <select name="category" required>${categoryOptions}</select>
        
        <label>📝 備考</label>
        <input type="text" name="memo" placeholder="メモ（任意）">

        <label>💳 支払方法</label>
        <select name="source" required>
          <option value="現金">現金</option>
          <option value="楽天ペイ">楽天ペイ</option>
          <option value="楽天カード">楽天カード</option>
          <option value="口座引落">口座引落</option>
        </select>
        
        <button type="submit" class="btn" id="submitBtn">登録する</button>
        <div id="message"></div>
      </form>
    </div>
  </div>

  <script>
    function showMessage(text, color) {
      const msg = document.getElementById('message');
      msg.textContent = text;
      msg.style.display = 'block';
      msg.style.background = color === 'green' ? '#ecfdf5' : '#fef2f2';
      msg.style.color = color === 'green' ? '#065f46' : '#991b1b';
      setTimeout(() => { msg.style.display = 'none'; }, 5000);
    }

    const dayOfWeekSpan = document.getElementById('dayOfWeek');
    const dateInput = document.querySelector('[name=date]');
    const weekDays = ['日', '月', '火', '水', '木', '金', '土'];

    function updateDayOfWeek() {
      const dateVal = dateInput.value;
      if (dateVal) {
        const date = new Date(dateVal);
        const day = weekDays[date.getDay()];
        dayOfWeekSpan.textContent = '(' + day + ')';
      } else {
        dayOfWeekSpan.textContent = '';
      }
    }

    dateInput.addEventListener('change', updateDayOfWeek);
    updateDayOfWeek(); // 初期表示

    document.getElementById('entryForm').addEventListener('submit', function(e) {
      e.preventDefault();
      const btn = document.getElementById('submitBtn');
      btn.disabled = true;
      btn.textContent = '登録中...';

      const data = {
        date: e.target.date.value,
        amount: e.target.amount.value,
        shop: e.target.shop.value,
        category: e.target.category.value,
        source: e.target.source.value,
        memo: e.target.memo.value
      };

      google.script.run.withSuccessHandler(function(res) {
        if (res.success) {
          showMessage('登録しました ✅', 'green');
          e.target.reset();
          document.querySelector('[name=date]').value = '${today}';
          updateDayOfWeek();
        } else {
          showMessage('エラー: ' + res.error, 'red');
        }
        btn.disabled = false;
        btn.textContent = '登録する';
      }).withFailureHandler(function() {
        showMessage('通信エラーが発生しました', 'red');
        btn.disabled = false;
        btn.textContent = '登録する';
      }).apiAddEntry(data);
    });
  </script>
</body>
</html>`;
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

/**
 * HTML 特殊文字をエスケープする。
 */
function escapeHtml_(str) {
  if (!str) return '';
  return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function jsonOk_(data) {
  return ContentService.createTextOutput(JSON.stringify(data)).setMimeType(ContentService.MimeType.JSON);
}
