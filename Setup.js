/**
 * Setup.js - 初期セットアップ・デバッグ
 *
 * 主要な関数:
 *   setupSheets()      : 必要なシートをすべて作成し、ヘッダーと初期データを投入する
 *   setupTriggers()    : 自動取込・固定費登録のトリガーを設定する
 *   debugEmailBody()   : 「家計簿/処理済み」ラベルの直近メール本文をログ出力（パース調査用）
 *
 * 使い方:
 *   GAS エディタ上で setupSheets() を一度実行するだけで環境が整う。
 */

/**
 * パース失敗したメールの本文を確認するためのデバッグ関数。
 * 「家計簿/処理済み」ラベルの直近スレッドのメール本文を全文ログ出力する。
 * パース失敗の原因調査後は不要になるため、確認できたら削除してよい。
 *
 * 使い方: GAS エディタで debugEmailBody を選択して実行 → ログを確認
 */
function debugEmailBody() {
  const label = GmailApp.getUserLabelByName(GMAIL_LABELS.UNPROCESSED);
  if (!label) {
    console.log('「' + GMAIL_LABELS.UNPROCESSED + '」ラベルが見つかりません。');
    return;
  }

  const threads = label.getThreads(0, 5);
  console.log('未処理スレッド数: ' + threads.length);

  threads.forEach((thread, ti) => {
    thread.getMessages().forEach((message, mi) => {
      console.log('=== スレッド' + ti + ' メッセージ' + mi + ' ===');
      console.log('from: ' + message.getFrom());
      console.log('subject: ' + message.getSubject());

      const stripped = stripHtml_(message.getBody());
      console.log('--- stripHtml_ 後（先頭1000文字）---');
      console.log(stripped.substring(0, 1000));
      console.log('--- ここまで ---');
    });
  });
}

/**
 * 各シートを作成し、ヘッダー行・初期データ・書式を設定する。
 * すでにシートが存在する場合はスキップする。
 */
function setupSheets() {
  const ss = getSpreadsheet();

  setupRawSheet_(ss);
  setupShopRulesSheet_(ss);
  setupFixedMasterSheet_(ss);
  setupMonthlySummarySheet_(ss);
  refreshMonthlySummary();
  setupTriggers();

  console.log('セットアップ完了。');
}

/**
 * 自動取込と固定費登録のトリガーを設定する。
 * 既存の同名関数のトリガーは削除してから再登録する。
 */
function setupTriggers() {
  const targetFunctions = ['runAutoImport'];

  // 既存トリガーを削除
  ScriptApp.getProjectTriggers().forEach((trigger) => {
    if (targetFunctions.includes(trigger.getHandlerFunction())) {
      ScriptApp.deleteTrigger(trigger);
    }
  });

  // 自動取込: 毎日 AM 7:00
  ScriptApp.newTrigger('runAutoImport')
    .timeBased()
    .everyDays(1)
    .atHour(7)
    .create();

  console.log('トリガー設定完了。');
}

// ---- プライベートヘルパー ----

/** 生データシートを作成する */
function setupRawSheet_(ss) {
  let sheet = ss.getSheetByName(SHEET_NAMES.RAW);
  if (!sheet) {
    sheet = ss.insertSheet(SHEET_NAMES.RAW);
  }

  const headers = ['日付', '金額', '店舗名', '決済手段', 'カテゴリ', 'メモ', '登録方法', '重複排除キー'];
  sheet.getRange(1, 1, 1, headers.length).setValues([headers]).setFontWeight('bold');

  // H 列（重複排除キー）を非表示にする
  sheet.hideColumns(COL.DEDUP_KEY + 1);

  // 日付列の書式
  sheet.getRange('A:A').setNumberFormat('yyyy-MM-dd');

  console.log(SHEET_NAMES.RAW + ' シート作成完了。');
}

/** 店舗ルールシートを作成する */
function setupShopRulesSheet_(ss) {
  let sheet = ss.getSheetByName(SHEET_NAMES.SHOP_RULES);
  if (!sheet) {
    sheet = ss.insertSheet(SHEET_NAMES.SHOP_RULES);
  }

  const headers = ['店舗名キーワード', 'カテゴリ名'];
  sheet.getRange(1, 1, 1, headers.length).setValues([headers]).setFontWeight('bold');

  console.log(SHEET_NAMES.SHOP_RULES + ' シート作成完了。');
}

/** 固定費マスタシートを作成する */
function setupFixedMasterSheet_(ss) {
  let sheet = ss.getSheetByName(SHEET_NAMES.FIXED_MASTER);
  if (!sheet) {
    sheet = ss.insertSheet(SHEET_NAMES.FIXED_MASTER);
  }

  const headers = ['店舗名/支払先', '金額', 'カテゴリ名', '決済手段', '開始月', 'メモ'];
  sheet.getRange(1, 1, 1, headers.length).setValues([headers]).setFontWeight('bold');

  // E列（開始月）を YYYY-MM 表示の日付形式に設定
  sheet.getRange('E2:E1000').setNumberFormat('yyyy/MM');

  console.log(SHEET_NAMES.FIXED_MASTER + ' シート作成完了。');
}

/**
 * 月次集計シートを作成する。
 * A〜C列（カテゴリ・予算・集計対象）はユーザーが管理するマスター列。
 * D列以降の実績・差額は refreshMonthlySummary() で自動生成する。
 */
function setupMonthlySummarySheet_(ss) {
  let sheet = ss.getSheetByName(SHEET_NAMES.MONTHLY_SUMMARY);
  if (!sheet) {
    sheet = ss.insertSheet(SHEET_NAMES.MONTHLY_SUMMARY);
  }

  // C列（集計対象）にチェックボックスを設定
  sheet
    .getRange('C2:C1000')
    .setDataValidation(SpreadsheetApp.newDataValidation().requireCheckbox().build());

  // 初期カテゴリを投入（既存データがある場合はスキップ）
  if (sheet.getLastRow() < 2) {
    const initialCategories = [
      ['食費', 0, true],
      ['日用雑貨', 0, true],
      ['交通', 0, true],
      ['通信', 0, true],
      ['医療・保険', 0, true],
      ['エンタメ', 0, true],
      ['旅行', 0, true],
      ['住宅', 0, true],
      ['サブスクリプション', 0, true],
      ['その他', 0, true],
      ['対象外', 0, false],
    ];
    sheet.getRange(2, 1, initialCategories.length, 3).setValues(initialCategories);
  }

  console.log(SHEET_NAMES.MONTHLY_SUMMARY + ' シート作成完了。');
}

/**
 * 生データシートの空行（中身が空の行）を削除して上に詰める（超高速フィルタ版）。
 */
function compactRawSheet() {
  const ss = getSpreadsheet();
  const sheet = ss.getSheetByName(SHEET_NAMES.RAW);
  if (!sheet) return;

  const fullRange = sheet.getDataRange();
  const values = fullRange.getValues();
  if (values.length <= 1) return;

  // 1行目はヘッダーなので保持しつつ、2行目以降で日付・金額・店舗のいずれかがある行だけ抽出
  const filtered = values.filter((row, i) => {
    if (i === 0) return true; // ヘッダーは残す
    return row[0] || row[1] || row[2]; // どれかデータがあれば残す
  });

  if (values.length > filtered.length) {
    sheet.clearContents();
    sheet.getRange(1, 1, filtered.length, filtered[0].length).setValues(filtered);
    console.log((values.length - filtered.length) + ' 行の空行を詰めました。');
  }
}
