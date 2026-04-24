/**
 * Config.js - 設定・定数定義
 *
 * スプレッドシートにバインドされた GAS として動作する。
 * SpreadsheetApp.getActiveSpreadsheet() でバインド先を取得するため
 * SPREADSHEET_ID のスクリプトプロパティは不要。
 *
 * スクリプトプロパティ（PropertiesService）で管理するキー:
 *   GEMINI_API_KEY : Gemini API キー
 *
 * Gmail ラベル運用:
 *   LABEL_UNPROCESSED のラベルを Gmail フィルタで決済通知メールに自動付与しておく。
 *   GAS は未処理ラベルのスレッドを処理し、完了後に処理済みラベルへ付け替える。
 *   これにより SEARCH_TARGET_DAYS_AGO / PROCESSED_MESSAGE_IDS は不要。
 */

/** Gemini API キーをスクリプトプロパティから取得する */
function getGeminiApiKey() {
  const key = PropertiesService.getScriptProperties().getProperty('GEMINI_API_KEY');
  if (!key) throw new Error('スクリプトプロパティ GEMINI_API_KEY が未設定です。');
  return key;
}

/** Web アプリ用パスワードをスクリプトプロパティから取得する */
function getWebPassword() {
  return PropertiesService.getScriptProperties().getProperty('WEB_PASSWORD') || 'admin'; // デフォルトは admin
}

/**
 * Gmail ラベル名定数
 * Gmail フィルタで LABEL_UNPROCESSED を決済通知メールに自動付与しておく。
 */
const GMAIL_LABELS = {
  UNPROCESSED: '家計簿/未処理',
  PROCESSED: '家計簿/処理済',
};

/**
 * メールパーサーマッピング
 * from/subject で各決済サービスのメールを識別し、対応するパーサーを選択する。
 * GAS はラベルでスレッドを絞り込んだ後、このルールでパーサーを決定する。
 *
 * from    : 送信元アドレスの部分一致文字列
 * subject : 件名の部分一致文字列（省略可）
 * parser  : Parsers オブジェクトのメソッド名
 * source  : 決済手段として生データシートに記録する文字列
 */
const MAIL_FILTERS = [
  {
    from: 'no-reply@pay.rakuten.co.jp',
    subject: '楽天ペイアプリご利用内容',
    parser: 'rakutenPay',
    source: '楽天ペイ',
  },
  {
    from: 'payment@checkout.rakuten.co.jp',
    subject: '楽天ペイ（オンライン決済）',
    parser: 'rakutenPayOnline',
    source: '楽天ペイ(オンライン)',
  },
  {
    from: 'info@mail.rakuten-card.co.jp',
    subject: 'カード利用のお知らせ',
    parser: 'rakutenCard',
    source: '楽天カード',
  },
];

/** シート名定数 */
const SHEET_NAMES = {
  RAW: '生データ',
  SHOP_RULES: '店舗ルール',
  FIXED_MASTER: '固定費マスタ',
  MONTHLY_SUMMARY: '月次集計',
};

/** 生データシートの列インデックス（0始まり） */
const COL = {
  DATE: 0,
  AMOUNT: 1,
  SHOP: 2,
  SOURCE: 3,
  CATEGORY: 4,
  MEMO: 5,
  METHOD: 6,
  DEDUP_KEY: 7,
};

/** 月次集計シートのマスター列インデックス（0始まり、A〜C列） */
const CAT_COL = {
  NAME: 0,
  BUDGET: 1,
  INCLUDE: 2,
};

/** カテゴリを Gemini で判定した場合のセル背景色 */
const LLM_CELL_COLOR = '#FFF2CC';
