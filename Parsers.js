/**
 * Parsers.js - メールパース
 *
 * zaim-importer/src/Parsers.js のパターンを参考に実装。
 * getBody()（HTML）を受け取り、タグ除去・空白正規化してから抽出する。
 *
 * 戻り値の形式:
 *   rakutenPay        : { date, amount, shop } | null
 *   rakutenPayOnline  : { date, amount, shop } | null
 *   rakutenCard       : [{ date, amount, shop, skip }, ...] | null
 *                       ※楽天カードは1通に複数明細があるため配列を返す
 */

const Parsers = {
  /**
   * 楽天ペイ（アプリ決済）のパース。
   *
   * メール本文例:
   *   ご利用日時  2026/04/15(火) 14:30
   *   ご利用店舗  〇〇コンビニ
   *   決済総額    1,234円
   *
   * @param {string} body  getBody() の戻り値（HTML or プレーンテキスト）
   * @returns {{ date: string, amount: number, shop: string } | null}
   */
  rakutenPay(body) {
    const text = stripHtml_(body);

    const shopMatch = text.match(/ご利用店舗\s+([^\r\n]+)/);
    const amountMatch = text.match(/決済総額\s+[¥￥]?([\d,]+)/);
    const dateMatch = text.match(/ご利用日時\s+(\d{4}\/\d{1,2}\/\d{1,2})/);

    const shop = shopMatch ? shopMatch[1].trim() : null;
    const amount = amountMatch ? parseInt(amountMatch[1].replace(/,/g, ''), 10) : null;
    const date = dateMatch ? dateMatch[1].replace(/\//g, '-') : null;

    if (!shop || !amount || !date) return null;
    return { date, amount, shop };
  },

  /**
   * 楽天ペイ（オンライン決済）のパース。
   * HTML メールのためタグ除去・空白正規化してから抽出する。
   *
   * メール本文（タグ除去後）:
   *   提携サイト「Jリーグチケット」にて楽天ペイ（オンライン決済）をご利用...
   *   ご注文日： 2026-04-15 14:30:00
   *   注文合計 2,110円
   *
   * @param {string} body  getBody() の戻り値（HTML）
   * @returns {{ date: string, amount: number, shop: string } | null}
   */
  rakutenPayOnline(body) {
    const text = stripHtml_(body);

    // ショップ名: 「提携サイト「...」」または「ショップ名 ： ...」
    const shopMatch = text.match(/提携サイト「([^」]+)」/) || text.match(/ショップ名\s*[：:]\s*([^\r\n]+)/);
    const shop = shopMatch ? (shopMatch[1] || shopMatch[2]).trim() : null;

    // 日付: 「ご注文日： ...」「注文日時： ...」「[日時] ...」など
    const dateMatch = text.match(/(?:ご注文日|注文日時|利用日時)[：:]\s*(\d{4}[-\/]\d{1,2}[-\/]\d{1,2})/) ||
                    text.match(/\[日時\]\s*(\d{4}[-\/]\d{1,2}[-\/]\d{1,2})/);
    const date = dateMatch
      ? dateMatch[1].replace(/\//g, '-')
      : null;

    // お支払い金額 → 注文合計 → 合計 → 明細合計の順で取得
    let amount = null;
    const amountPatterns = [
      /お支払い金額[：:]\s*([\d,]+)円/,
      /注文合計\s*([\d,]+)円/,
      /合計\s*([\d,]+)円/
    ];

    for (const pattern of amountPatterns) {
      const match = text.match(pattern);
      if (match) {
        amount = parseInt(match[1].replace(/,/g, ''), 10);
        break;
      }
    }

    if (!amount) {
      // 明細行の「＝ X,XXX円」を合計（例: 2,000円 × 1個 ＝ 2,000円）
      const lineMatches = text.match(/＝\s*([\d,]+)円/g);
      if (lineMatches) {
        amount = 0;
        lineMatches.forEach((match) => {
          const val = match.match(/([\d,]+)/)[1].replace(/,/g, '');
          amount += parseInt(val, 10);
        });
      }
    }

    if (!shop || !amount || !date) return null;
    return { date, amount, shop };
  },

  /**
   * 楽天カード利用お知らせメールのパース。
   * 1通に複数明細が含まれるため、配列で返す。
   *
   * メール本文例（明細ブロック）:
   *   ■利用日: 2026/04/15
   *   ■利用先: 〇〇スーパー
   *   ■利用金額: 1,234
   *
   * @param {string} body  getBody() の戻り値（HTML or プレーンテキスト）
   * @returns {Array<{ date: string, amount: number, shop: string, skip: boolean }> | null}
   */
  rakutenCard(body) {
    const text = stripHtml_(body);
    const results = [];

    // テーブル形式: "2026/04/06 バイエルオンラインショップ 6,805 円"
    const regex = /(\d{4}\/\d{1,2}\/\d{1,2})\s+(.+?)\s+([\d,]+)\s*円/g;
    let match;
    while ((match = regex.exec(text)) !== null) {
      const date = match[1].replace(/\//g, '-');
      const shop = match[2].trim();
      const amount = parseInt(match[3].replace(/,/g, ''), 10);

      if (!shop || !amount) continue;

      const skip =
        shop.includes('楽天キャッシュ') || shop.includes('楽天証券投信積立');

      results.push({ date, amount, shop, skip });
    }

    return results.length > 0 ? results : null;
  },
};

// ---- プライベートヘルパー ----

/**
 * HTML タグを除去し、空白・改行を正規化した文字列を返す。
 * プレーンテキストの場合は実質ノーオペレーション。
 *
 * @param {string} html
 * @returns {string}
 */
function stripHtml_(html) {
  return html
    .replace(/<style[^>]*>[\s\S]*?<\/style>/gi, '')  // style ブロックを丸ごと削除
    .replace(/<script[^>]*>[\s\S]*?<\/script>/gi, '') // script ブロックを丸ごと削除
    .replace(/<[^>]*>/g, ' ')   // 残りのタグをスペースに置換
    .replace(/&nbsp;/g, ' ')    // HTML エンティティ
    .replace(/&yen;/gi, '¥')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&')
    .replace(/[ \t]+/g, ' ')    // 水平空白を1スペースに
    .replace(/\n[ \t]+/g, '\n') // 行頭の空白を除去
    .trim();
}
