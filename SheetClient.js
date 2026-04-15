/**
 * SheetClient.js - スプレッドシート操作
 *
 * 主要な関数:
 *   getSpreadsheet()           : スプレッドシートオブジェクトを取得
 *   appendTransaction(data)    : 生データシートに1行追加
 *   isDuplicateHash(hash)      : ハッシュキーの重複判定（手動入力の二重登録防止）
 *   getCategories()            : カテゴリマスタから一覧取得
 *   getCategoryMasterRows()    : カテゴリマスタを全列取得（予算・集計対象含む）
 *   getShopRules()             : 店舗ルールを取得
 *   addShopRule(shop, cat)     : 店舗ルールを末尾に追加
 *   getRecentTransactions(n)   : 末尾 n 件を取得
 *   deleteTransactionByRow(r)  : 指定行を削除
 *   refreshMonthlySummary()    : 月次集計シートを再構築
 */

/**
 * スプレッドシートオブジェクトを返す。
 * スプレッドシートにバインドされた GAS のため getActiveSpreadsheet() を使用する。
 */
function getSpreadsheet() {
  return SpreadsheetApp.getActiveSpreadsheet();
}

/**
 * 生データシートに1行追加する。
 *
 * @param {Object} data
 *   date     {string}  "YYYY-MM-DD"
 *   amount   {number}  金額（円）
 *   shop     {string}  店舗名
 *   source   {string}  決済手段
 *   category {string}  カテゴリ名
 *   memo     {string}  メモ（任意）
 *   method   {string}  "auto" | "fixed" | "manual"
 *   dedupKey {string}  重複排除キー（SHA-256 ハッシュ）
 * @param {boolean} highlightCategory  true の場合 E 列（カテゴリ）を黄色に塗る
 */
function appendTransaction(data, highlightCategory) {
  // 先に空行を詰める
  compactRawSheet();
  
  const ss = getSpreadsheet();
  const sheet = ss.getSheetByName(SHEET_NAMES.RAW);
  const row = [
    data.date,
    data.amount,
    data.shop,
    data.source,
    data.category,
    data.memo || '',
    data.method,
    data.dedupKey,
  ];
  sheet.appendRow(row);

  if (highlightCategory) {
    const lastRow = sheet.getLastRow();
    sheet.getRange(lastRow, COL.CATEGORY + 1).setBackground(LLM_CELL_COLOR);
  }
}

/**
 * ハッシュキーが生データシートの H 列に存在するかを判定する（手動・固定費用）。
 *
 * @param {string} hash  SHA-256 ハッシュ文字列
 * @returns {boolean}
 */
function isDuplicateHash(hash) {
  const ss = getSpreadsheet();
  const sheet = ss.getSheetByName(SHEET_NAMES.RAW);
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return false;
  const keys = sheet
    .getRange(2, COL.DEDUP_KEY + 1, lastRow - 1, 1)
    .getValues()
    .flat();
  return keys.includes(hash);
}

/**
 * 月次集計シートのA列からカテゴリ名の配列を返す。
 * Gemini API プロンプトや Web アプリの選択肢に使用するため「対象外」含む全件を返す。
 *
 * @returns {string[]}
 */
function getCategories() {
  const ss = getSpreadsheet();
  const sheet = ss.getSheetByName(SHEET_NAMES.MONTHLY_SUMMARY);
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return [];
  return sheet
    .getRange(2, 1, lastRow - 1, 1)
    .getValues()
    .flat()
    .filter((v) => v !== '' && v !== '合計');
}

/**
 * 月次集計シートのマスター列（A〜C列）を取得する。
 * ヘッダー行・合計行を除いた [[name, budget, include], ...] の形式。
 *
 * @returns {Array[]}
 */
function getCategoryMasterRows() {
  const ss = getSpreadsheet();
  const sheet = ss.getSheetByName(SHEET_NAMES.MONTHLY_SUMMARY);
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return [];
  return sheet
    .getRange(2, 1, lastRow - 1, 3)
    .getValues()
    .filter((row) => row[0] !== '' && row[0] !== '合計');
}

/**
 * 店舗ルールシートのデータを返す。
 * ヘッダー行を除いた [[keyword, category], ...] の形式。
 *
 * @returns {string[][]}
 */
function getShopRules() {
  const ss = getSpreadsheet();
  const sheet = ss.getSheetByName(SHEET_NAMES.SHOP_RULES);
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return [];
  return sheet.getRange(2, 1, lastRow - 1, 2).getValues();
}

/**
 * 店舗ルールシートの末尾に新しいルールを追加する。
 * AI 判定結果を次回以降ルールヒットさせるために使用する。
 *
 * @param {string} shopName  店舗名（キーワードとして登録）
 * @param {string} category  カテゴリ名
 */
function addShopRule(shopName, category) {
  const ss = getSpreadsheet();
  const sheet = ss.getSheetByName(SHEET_NAMES.SHOP_RULES);
  sheet.appendRow([shopName, category]);
  const lastRow = sheet.getLastRow();
  sheet.getRange(lastRow, 1, 1, 2).setBackground(LLM_CELL_COLOR);
}

/**
 * 生データシートの末尾 n 件をオブジェクト配列で返す。
 * Web アプリの直近一覧表示に使用する。
 *
 * @param {number} n
 * @returns {Object[]}
 */
function getRecentTransactions(n) {
  const ss = getSpreadsheet();
  const sheet = ss.getSheetByName(SHEET_NAMES.RAW);
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return [];
  const startRow = Math.max(2, lastRow - n + 1);
  const numRows = lastRow - startRow + 1;
  const rows = sheet.getRange(startRow, 1, numRows, 8).getValues();
  return rows
    .map((row, i) => ({
      rowNumber: startRow + i,
      date: row[COL.DATE],
      amount: row[COL.AMOUNT],
      shop: row[COL.SHOP],
      source: row[COL.SOURCE],
      category: row[COL.CATEGORY],
      memo: row[COL.MEMO],
      method: row[COL.METHOD],
    }))
    .reverse();
}

/**
 * 指定した行番号の行を生データシートから削除する。
 *
 * @param {number} rowNumber  1始まりの行番号
 */
function deleteTransactionByRow(rowNumber) {
  const ss = getSpreadsheet();
  const sheet = ss.getSheetByName(SHEET_NAMES.RAW);
  sheet.deleteRow(rowNumber);
}

/**
 * 月次集計シートを最新状態に再構築する。
 *
 * A〜C列（カテゴリ・予算・集計対象）はユーザー管理データとして読み取り後に書き戻す。
 * D列以降（実績・差額）は SUMIFS 数式で自動生成する。
 * 集計対象=FALSE の行は実績欄を空にし、合計行の SUMIF からも除外される。
 */
function refreshMonthlySummary() {
  const ss = getSpreadsheet();
  const sheet = ss.getSheetByName(SHEET_NAMES.MONTHLY_SUMMARY);
  if (!sheet) return;

  // A〜C列のマスターデータを読み取る（再構築前に保存）
  const masterRows = getCategoryMasterRows();
  if (masterRows.length === 0) return;

  const months = buildMonthList_(6);

  // シートをクリア（書式・データバリデーションは保持）
  sheet.clearContents();

  // ヘッダー行
  // A: カテゴリ, B: 月次予算, C: 集計対象, D: 当月実績, E: 差額, F〜J: 前月〜5ヶ月前
  const headers = [
    'カテゴリ', '月次予算', '集計対象',
    months[0].label + ' 実績', '差額（予算比）',
  ];
  for (let i = 1; i < months.length; i++) {
    headers.push(months[i].label + ' 実績');
  }
  const totalCols = headers.length;
  sheet.getRange(1, 1, 1, totalCols).setValues([headers]).setFontWeight('bold');

  // カテゴリ行（全行を書き戻す。集計対象=FALSE は実績欄を空に）
  const categoryRowsData = masterRows.map((row, idx) => {
    const r = idx + 2;
    const name = row[CAT_COL.NAME];
    const budget = row[CAT_COL.BUDGET] || 0;
    const include = row[CAT_COL.INCLUDE];
    const isActive = include !== false;

    const rowData = [name, budget, include];
    if (isActive) {
      rowData.push(buildSumifsFormula_(r, months[0].year, months[0].month)); // D: 当月実績
      rowData.push('=B' + r + '-D' + r); // E: 差額（予算 − 実績）
      for (let i = 1; i < months.length; i++) {
        rowData.push(buildSumifsFormula_(r, months[i].year, months[i].month));
      }
    } else {
      for (let i = 0; i < months.length + 1; i++) rowData.push('');
    }
    return rowData;
  });

  sheet.getRange(2, 1, categoryRowsData.length, totalCols).setValues(categoryRowsData);

  // 合計行（集計対象=TRUE の行のみ SUMIF で集計）
  const totalRow = masterRows.length + 2;
  const lastDataRow = totalRow - 1;
  const totalData = [
    '合計',
    '=SUMIF(C2:C' + lastDataRow + ',TRUE,B2:B' + lastDataRow + ')', // B: 予算合計
    '', // C: チェックボックスなし
    '=SUMIF(C2:C' + lastDataRow + ',TRUE,D2:D' + lastDataRow + ')', // D: 実績合計
    '=B' + totalRow + '-D' + totalRow, // E: 差額
  ];
  for (let i = 1; i < months.length; i++) {
    const col = colIndexToLetter_(5 + i); // F, G, H, I, J
    totalData.push('=SUMIF(C2:C' + lastDataRow + ',TRUE,' + col + '2:' + col + lastDataRow + ')');
  }
  sheet.getRange(totalRow, 1, 1, totalCols).setValues([totalData]).setFontWeight('bold');

  // 数値書式
  sheet.getRange(2, 2, totalRow - 1, 1).setNumberFormat('#,##0'); // B列（予算）
  sheet.getRange(2, 4, totalRow - 1, totalCols - 3).setNumberFormat('#,##0'); // D列以降（実績・差額）

  // 差額列（E列=5列目）：予算超過をマイナス赤字で表示
  sheet.getRange(2, 5, totalRow - 1, 1).setNumberFormat('[Red]-#,##0;[Black]#,##0;0');

  console.log('月次集計を更新しました。');
}

// ---- refreshMonthlySummary プライベートヘルパー ----

/**
 * 前月から count ヶ月分の年月リストを返す（新しい順）。
 * 楽天カード等の利用通知が約半月遅れるため、毎月15日前後に前月分を集計する運用に合わせ、
 * 先頭を前月（1ヶ月前）とする。
 *
 * @param {number} count
 * @returns {{ label: string, year: number, month: number }[]}
 */
function buildMonthList_(count) {
  const months = [];
  const now = new Date();
  for (let i = 1; i <= count; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    months.push({
      label: d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0'),
      year: d.getFullYear(),
      month: d.getMonth() + 1,
    });
  }
  return months;
}

/**
 * 指定カテゴリ行・年月の実績数式文字列を生成する。
 * 生データ（変動費）+ 固定費マスタ の両方を合算する。
 *
 * @param {number} row   行番号（1始まり）
 * @param {number} year
 * @param {number} month
 * @returns {string}
 */
function buildSumifsFormula_(row, year, month) {
  const variable =
    'SUMIFS(生データ!$B:$B,' +
    '生データ!$E:$E,$A' + row + ',' +
    '生データ!$A:$A,">="&DATE(' + year + ',' + month + ',1),' +
    '生データ!$A:$A,"<="&EOMONTH(DATE(' + year + ',' + month + ',1),0))';
  // E列（開始月）が空または集計月以前の行のみを合算する
  const fixed =
    'SUMIFS(固定費マスタ!$B:$B,' +
    '固定費マスタ!$C:$C,$A' + row + ',' +
    '固定費マスタ!$E:$E,"<="&DATE(' + year + ',' + month + ',1))';
  return '=' + variable + '+' + fixed;
}

/**
 * 列番号（1始まり）をアルファベット文字列に変換する。
 * 例: 1→A, 5→E, 27→AA
 *
 * @param {number} colIndex  1始まりの列番号
 * @returns {string}
 */
function colIndexToLetter_(colIndex) {
  let result = '';
  while (colIndex > 0) {
    colIndex--;
    result = String.fromCharCode(65 + (colIndex % 26)) + result;
    colIndex = Math.floor(colIndex / 26);
  }
  return result;
}

