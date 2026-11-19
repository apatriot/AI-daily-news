/**
 * AI 日报 · 反馈与行为数据后端（Google Apps Script）
 *
 * 部署步骤：
 * 1. 新建一个 Google Sheet，打开「扩展程序 → Apps Script」
 * 2. 把本文件内容整体粘贴进去，替换 READ_TOKEN
 * 3. 运行一次 setup() 授权并创建表头
 * 4. 部署 → 新建部署 → 类型「网络应用」
 *    - 执行身份：我
 *    - 访问权限：任何人
 * 5. 复制部署 URL：
 *    - 页面埋点用：https://script.google.com/macros/s/XXX/exec   （FEEDBACK_POST_URL）
 *    - Actions 读取用：上面 URL + ?read=<READ_TOKEN>            （FEEDBACK_READ_URL）
 *    - Actions 回写用：上面 URL + ?write=<READ_TOKEN>           （FEEDBACK_WRITE_URL）
 *
 * 注意：每次修改代码后要「管理部署 → 编辑 → 版本：新版本」才会生效。
 */

const READ_TOKEN = 'CHANGE_ME_TO_A_LONG_RANDOM_STRING';
const TZ = 'Asia/Shanghai';

const EVENT_HEADERS = [
  'received_at', 'client_ts', 'date', 'uid', 'sid', 'type', 'page',
  'story_id', 'section', 'position', 'cluster', 'source', 'dwell_ms',
  'scroll', 'action'
];
const PROFILE_HEADERS = ['updated_at', 'payload'];
const STORY_HEADERS = ['date', 'story_id', 'section', 'cluster', 'source', 'title', 'url', 'scores'];

function setup() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  ensureSheet(ss, 'events', EVENT_HEADERS);
  ensureSheet(ss, 'profile_snapshots', PROFILE_HEADERS);
  ensureSheet(ss, 'stories', STORY_HEADERS);
}

function ensureSheet(ss, name, headers) {
  let sh = ss.getSheetByName(name);
  if (!sh) sh = ss.insertSheet(name);
  if (sh.getLastRow() === 0) {
    sh.appendRow(headers);
    sh.setFrozenRows(1);
  }
  return sh;
}

function sheet(name, headers) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  return ensureSheet(ss, name, headers);
}

function text(value) {
  return ContentService.createTextOutput(String(value));
}

function json(value) {
  return ContentService
    .createTextOutput(JSON.stringify(value))
    .setMimeType(ContentService.MimeType.JSON);
}

/** 页面埋点写入 */
function doPost(e) {
  const params = (e && e.parameter) || {};
  let body = {};
  try {
    body = JSON.parse((e && e.postData && e.postData.contents) || '{}');
  } catch (err) {
    body = {};
  }

  if (params.write === READ_TOKEN) {
    return writeSnapshot(body);
  }
  return appendEvent(body);
}

/** Actions 读取：?read=TOKEN&since=<epoch_ms> */
function doGet(e) {
  const params = (e && e.parameter) || {};
  if (params.read !== READ_TOKEN) return text('forbidden');

  const since = Number(params.since || 0);
  return json({
    ok: true,
    events: readEvents(since),
    profile: latestProfile(),
    stories: params.stories === '1' ? readStories() : []
  });
}

function appendEvent(p) {
  if (!p || !p.type) return text('ignored');
  const sh = sheet('events', EVENT_HEADERS);
  sh.appendRow([
    new Date(),
    Number(p.ts || 0),
    p.date || '',
    p.uid || '',
    p.sid || '',
    p.type || '',
    p.page || '',
    p.story_id || '',
    p.section || '',
    p.position || '',
    p.cluster || '',
    p.source || '',
    p.dwell_ms || '',
    p.scroll || '',
    p.action || ''
  ]);
  return text('ok');
}

function writeSnapshot(payload) {
  const sh = sheet('profile_snapshots', PROFILE_HEADERS);
  sh.appendRow([new Date(), JSON.stringify(payload || {})]);

  const stories = (payload && payload.stories) || [];
  if (stories.length) {
    const st = sheet('stories', STORY_HEADERS);
    const date = (payload && payload.date) || '';
    stories.forEach(function (s) {
      st.appendRow([
        date, s.id || '', s.section || '', s.cluster || '', s.source || '',
        s.title || '', s.url || '', JSON.stringify(s.scores || {})
      ]);
    });
  }
  return text('ok');
}

function readEvents(since) {
  const sh = sheet('events', EVENT_HEADERS);
  const last = sh.getLastRow();
  if (last < 2) return [];
  const rows = sh.getRange(2, 1, last - 1, EVENT_HEADERS.length).getValues();
  const out = [];
  rows.forEach(function (r) {
    const clientTs = Number(r[1] || 0);
    if (clientTs && clientTs <= since) return;
    out.push({
      received_at: r[0] instanceof Date ? r[0].toISOString() : String(r[0]),
      ts: clientTs,
      date: r[2], uid: r[3], sid: r[4], type: r[5], page: r[6],
      story_id: r[7], section: r[8], position: r[9], cluster: r[10],
      source: r[11], dwell_ms: r[12], scroll: r[13], action: r[14]
    });
  });
  return out;
}

function latestProfile() {
  const sh = sheet('profile_snapshots', PROFILE_HEADERS);
  const last = sh.getLastRow();
  if (last < 2) return null;
  const raw = sh.getRange(last, 2).getValue();
  try {
    return JSON.parse(raw);
  } catch (err) {
    return null;
  }
}

function readStories() {
  const sh = sheet('stories', STORY_HEADERS);
  const last = sh.getLastRow();
  if (last < 2) return [];
  return sh.getRange(2, 1, last - 1, STORY_HEADERS.length).getValues();
}
