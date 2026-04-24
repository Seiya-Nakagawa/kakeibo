/**
 * Code.js - エントリーポイント
 *
 * 主要な関数:
 *   runAutoImport() : 「家計簿/未処理」ラベルのメールを取込む（時間トリガー・日次）
 *
 * ラベル運用:
 *   Gmail フィルタで決済通知メールに「家計簿/未処理」ラベルを自動付与しておく。
 *   GAS 処理後、ラベルを「家計簿/処理済み」に付け替える。
 */

/** エラー通知先メールアドレス */
const ALERT_EMAIL = 'aibdlnew1.work@gmail.com';

/**
 * 「家計簿/未処理」ラベルのスレッドを取込む。
 * 処理後はラベルを「家計簿/処理済み」に付け替える。
 * パース失敗があった場合は ALERT_EMAIL に通知する。
 */
function runAutoImport() {
  const unprocessedLabel = GmailApp.getUserLabelByName(GMAIL_LABELS.UNPROCESSED);
  if (!unprocessedLabel) {
    const msg = 'Gmail ラベル "' + GMAIL_LABELS.UNPROCESSED + '" が存在しません。Gmail フィルタでラベルを作成・設定してください。';
    console.error(msg);
    sendErrorAlert_('【家計簿】ラベル未設定エラー', msg);
    return;
  }
  const processedLabel = getOrCreateLabel_(GMAIL_LABELS.PROCESSED);

  const threads = unprocessedLabel.getThreads();
  console.log('未処理スレッド数: ' + threads.length);

  const errors = [];

  threads.forEach((thread) => {
    let threadOk = true;

    thread.getMessages().forEach((message) => {
      const filter = detectFilter_(message);
      if (!filter) {
        const err = 'パーサー特定できず\n  from: ' + message.getFrom() + '\n  subject: ' + message.getSubject();
        errors.push(err);
        threadOk = false;
        return;
      }

      const body = message.getBody();
      const parsed = Parsers[filter.parser](body);

      if (!parsed) {
        const stripped = stripHtml_(body);
        const err = 'パース失敗\n  from: ' + message.getFrom() + '\n  subject: ' + message.getSubject() +
                    '\n  stripHtml後: ' + stripped.substring(0, 500);
        errors.push(err);
        threadOk = false;
        return;
      }

      // rakutenCard は複数明細の配列、その他は単一オブジェクトを返す
      const items = Array.isArray(parsed) ? parsed : [parsed];

      items.forEach((item) => {
        if (item.skip) {
          return;
        }

        const { category, method } = getCategory(item.shop);
        const dedupKey = computeHash_(
          item.date + item.amount + item.shop + filter.source
        );

        appendTransaction(
          {
            date: item.date,
            amount: item.amount,
            shop: item.shop,
            source: filter.source,
            category,
            memo: '',
            method: 'auto',
            dedupKey,
          },
          method === 'llm'
        );

        if (method === 'llm') {
          const keyword = extractShopKeyword(item.shop);
          addShopRule(keyword, category);
          console.log('店舗ルール追加(AI判定): ' + keyword + ' → ' + category);
        }

        console.log('登録完了: ' + item.shop + ' ' + item.amount + '円 [' + category + ']');
      });
    });

    // 全メッセージの処理が成功した場合のみ処理済みに移動
    // 失敗があった場合は未処理ラベルのままにして再処理できるようにする
    if (threadOk) {
      thread.removeLabel(unprocessedLabel);
      thread.addLabel(processedLabel);
      console.log('処理済みに移動: ' + thread.getFirstMessageSubject());
    } else {
      console.warn('未処理のまま保留: ' + thread.getFirstMessageSubject());
    }
  });

  // 月次集計を更新
  refreshMonthlySummary();

  // エラーがあった場合はメール通知
  if (errors.length > 0) {
    const subject = '【家計簿】取込エラー ' + errors.length + '件';
    const body = '以下のメールの取込に失敗しました。パーサーの正規表現を確認してください。\n\n' +
                 errors.map((e, i) => (i + 1) + '. ' + e).join('\n\n');
    sendErrorAlert_(subject, body);
    console.warn('エラー通知を送信しました: ' + ALERT_EMAIL);
  }
}


// ---- プライベートヘルパー ----

/**
 * メッセージの送信元・件名から MAIL_FILTERS のエントリを特定する。
 *
 * @param {GoogleAppsScript.Gmail.GmailMessage} message
 * @returns {{ parser: string, source: string } | null}
 */
function detectFilter_(message) {
  const from = message.getFrom();
  const subject = message.getSubject();

  for (const filter of MAIL_FILTERS) {
    if (!from.includes(filter.from)) continue;
    if (filter.subject && !subject.includes(filter.subject)) continue;
    return filter;
  }

  console.warn('フィルタ未ヒット: \n  from: ' + from + '\n  subject: ' + subject);
  return null;
}

/**
 * Gmail ラベルを取得する。存在しない場合は新規作成する。
 *
 * @param {string} labelName
 * @returns {GoogleAppsScript.Gmail.GmailLabel}
 */
function getOrCreateLabel_(labelName) {
  return (
    GmailApp.getUserLabelByName(labelName) ||
    GmailApp.createLabel(labelName)
  );
}

/**
 * エラー通知メールを送信する。
 *
 * @param {string} subject
 * @param {string} body
 */
function sendErrorAlert_(subject, body) {
  try {
    GmailApp.sendEmail(ALERT_EMAIL, subject, body);
  } catch (e) {
    console.error('エラー通知メール送信失敗: ' + e.message);
  }
}

/**
 * 文字列から SHA-256 ハッシュ（16進数文字列）を生成する。
 *
 * @param {string} input
 * @returns {string}
 */
function computeHash_(input) {
  const bytes = Utilities.computeDigest(
    Utilities.DigestAlgorithm.SHA_256,
    input,
    Utilities.Charset.UTF_8
  );
  return bytes
    .map((b) => (b < 0 ? b + 256 : b).toString(16).padStart(2, '0'))
    .join('');
}
