/**
 * LifeOS専用 Google Apps Script API
 *
 * 使い方:
 * 1. Google Apps Scriptで新規プロジェクトを作り、このファイルを貼り付ける
 * 2. スクリプト プロパティに API_TOKEN を設定する（Render側と同じ秘密値）
 * 3. 初回のみ setupLifeOSDatabase() を手動実行し、権限を承認する
 * 4. ウェブアプリとしてデプロイする
 *
 * EA-detaのスプレッドシートやAPIは使用しません。
 * RenderのFlaskサーバーからサーバー間通信で呼び出す設計です。
 */

const LIFEOS_SHEET_NAMES = {
  tasks: 'Tasks',
  notes: 'Notes',
  sites: 'Sites'
};

function setupLifeOSDatabase() {
  const props = PropertiesService.getScriptProperties();
  let spreadsheetId = props.getProperty('SPREADSHEET_ID');
  let spreadsheet;

  if (spreadsheetId) {
    spreadsheet = SpreadsheetApp.openById(spreadsheetId);
  } else {
    spreadsheet = SpreadsheetApp.create('LifeOS Database');
    props.setProperty('SPREADSHEET_ID', spreadsheet.getId());
  }

  ensureSheet_(spreadsheet, LIFEOS_SHEET_NAMES.tasks,
    ['id', 'title', 'done', 'created_at']);
  ensureSheet_(spreadsheet, LIFEOS_SHEET_NAMES.notes,
    ['note_date', 'content']);
  ensureSheet_(spreadsheet, LIFEOS_SHEET_NAMES.sites,
    ['id', 'name', 'url', 'category', 'description', 'repo_url', 'created_at']);

  return spreadsheet.getUrl();
}

function doGet() {
  return jsonOutput_({ ok: true, service: 'LifeOS API', version: 1 });
}

function doPost(e) {
  try {
    const payload = JSON.parse((e && e.postData && e.postData.contents) || '{}');
    const token = PropertiesService.getScriptProperties().getProperty('API_TOKEN');
    if (!token || !constantTimeEquals_(String(payload.token || ''), token)) {
      return jsonOutput_({ ok: false, error: 'Unauthorized' });
    }

    const result = dispatch_(String(payload.action || ''), payload.args || {});
    return jsonOutput_({ ok: true, data: result });
  } catch (err) {
    return jsonOutput_({ ok: false, error: String(err && err.message ? err.message : err) });
  }
}

function dispatch_(action, args) {
  const db = getDatabase_();
  switch (action) {
    case 'get_all':
      return {
        tasks: readRows_(db.getSheetByName(LIFEOS_SHEET_NAMES.tasks)),
        notes: readRows_(db.getSheetByName(LIFEOS_SHEET_NAMES.notes)),
        sites: readRows_(db.getSheetByName(LIFEOS_SHEET_NAMES.sites))
      };
    case 'task_add':
      return addRow_(db.getSheetByName(LIFEOS_SHEET_NAMES.tasks), {
        title: requiredText_(args.title, 120),
        done: 0,
        created_at: requiredText_(args.created_at, 40)
      });
    case 'task_toggle':
      return updateById_(db.getSheetByName(LIFEOS_SHEET_NAMES.tasks), args.id, row => {
        row.done = Number(row.done) === 1 ? 0 : 1;
        return row;
      });
    case 'task_delete':
      return deleteById_(db.getSheetByName(LIFEOS_SHEET_NAMES.tasks), args.id);
    case 'note_save':
      return saveNote_(db.getSheetByName(LIFEOS_SHEET_NAMES.notes), args);
    case 'site_add':
      return addRow_(db.getSheetByName(LIFEOS_SHEET_NAMES.sites), {
        name: requiredText_(args.name, 100),
        url: validateUrl_(args.url),
        category: optionalText_(args.category, 40) || 'その他',
        description: optionalText_(args.description, 500),
        repo_url: validateRepoUrl_(args.repo_url),
        created_at: requiredText_(args.created_at, 40)
      });
    case 'site_delete':
      return deleteById_(db.getSheetByName(LIFEOS_SHEET_NAMES.sites), args.id);
    case 'backup_replace':
      return replaceData_(db, args.data || {});
    default:
      throw new Error('Unknown action');
  }
}

function getDatabase_() {
  const id = PropertiesService.getScriptProperties().getProperty('SPREADSHEET_ID');
  if (!id) throw new Error('Database is not initialized. Run setupLifeOSDatabase() first.');
  return SpreadsheetApp.openById(id);
}

function ensureSheet_(spreadsheet, name, headers) {
  let sheet = spreadsheet.getSheetByName(name);
  if (!sheet) sheet = spreadsheet.insertSheet(name);
  if (sheet.getLastRow() === 0) sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
}

function readRows_(sheet) {
  const values = sheet.getDataRange().getValues();
  if (values.length < 2) return [];
  const headers = values.shift().map(String);
  return values.filter(row => row.some(value => value !== '')).map(row => {
    const item = {};
    headers.forEach((header, index) => item[header] = row[index]);
    if ('done' in item) item.done = Number(item.done) ? 1 : 0;
    if ('id' in item) item.id = Number(item.id);
    return item;
  });
}

function addRow_(sheet, item) {
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0].map(String);
    if ('id' in headers) item.id = nextId_(sheet);
    sheet.appendRow(headers.map(header => item[header] === undefined ? '' : item[header]));
    return item;
  } finally {
    lock.releaseLock();
  }
}

function nextId_(sheet) {
  if (sheet.getLastRow() < 2) return 1;
  const ids = sheet.getRange(2, 1, sheet.getLastRow() - 1, 1).getValues()
    .map(row => Number(row[0]) || 0);
  return Math.max.apply(null, ids.concat([0])) + 1;
}

function updateById_(sheet, id, transform) {
  const target = Number(id);
  if (!Number.isInteger(target) || target < 1) throw new Error('Invalid ID');
  const rows = readRows_(sheet);
  const item = rows.find(row => Number(row.id) === target);
  if (!item) throw new Error('Record not found');
  const updated = transform(item);
  writeRows_(sheet, rows.map(row => Number(row.id) === target ? updated : row));
  return updated;
}

function deleteById_(sheet, id) {
  const target = Number(id);
  if (!Number.isInteger(target) || target < 1) throw new Error('Invalid ID');
  const rows = readRows_(sheet);
  const remaining = rows.filter(row => Number(row.id) !== target);
  if (remaining.length === rows.length) throw new Error('Record not found');
  writeRows_(sheet, remaining);
  return { deleted: true, id: target };
}

function saveNote_(sheet, args) {
  const noteDate = requiredText_(args.note_date, 10);
  const content = String(args.content || '');
  if (content.length > 5000) throw new Error('Note exceeds 5000 characters');
  const rows = readRows_(sheet);
  const existing = rows.find(row => String(row.note_date) === noteDate);
  if (existing) {
    existing.content = content;
    writeRows_(sheet, rows);
    return existing;
  }
  sheet.appendRow([noteDate, content]);
  return { note_date: noteDate, content: content };
}

function replaceData_(spreadsheet, data) {
  ['tasks', 'notes', 'sites'].forEach(key => {
    if (!Array.isArray(data[key])) throw new Error('Invalid backup data: ' + key);
  });
  const tasks = data.tasks.map(item => ({
    id: Number(item.id) || 0,
    title: requiredText_(item.title, 120),
    done: Number(item.done) ? 1 : 0,
    created_at: requiredText_(item.created_at, 40)
  }));
  const notes = data.notes.map(item => ({
    note_date: requiredText_(item.note_date, 10),
    content: String(item.content || '')
  }));
  const sites = data.sites.map(item => ({
    id: Number(item.id) || 0,
    name: requiredText_(item.name, 100),
    url: validateUrl_(item.url),
    category: optionalText_(item.category, 40) || 'その他',
    description: optionalText_(item.description, 500),
    repo_url: validateRepoUrl_(item.repo_url),
    created_at: requiredText_(item.created_at, 40)
  }));
  writeRows_(spreadsheet.getSheetByName(LIFEOS_SHEET_NAMES.tasks), tasks);
  writeRows_(spreadsheet.getSheetByName(LIFEOS_SHEET_NAMES.notes), notes);
  writeRows_(spreadsheet.getSheetByName(LIFEOS_SHEET_NAMES.sites), sites);
  return { restored: true };
}

function writeRows_(sheet, items) {
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0].map(String);
  const oldRows = Math.max(sheet.getLastRow() - 1, 0);
  if (oldRows) sheet.getRange(2, 1, oldRows, sheet.getLastColumn()).clearContent();
  if (!items.length) return;
  const values = items.map(item => headers.map(header => item[header] === undefined ? '' : item[header]));
  sheet.getRange(2, 1, values.length, headers.length).setValues(values);
}

function requiredText_(value, maxLength) {
  const text = String(value == null ? '' : value).trim();
  if (!text || text.length > maxLength) throw new Error('Invalid text field');
  return text;
}

function optionalText_(value, maxLength) {
  const text = String(value == null ? '' : value).trim();
  if (text.length > maxLength) throw new Error('Text field is too long');
  return text;
}

function validateUrl_(value) {
  const url = requiredText_(value, 2048);
  if (!/^https?:\/\//i.test(url)) throw new Error('URL must start with http:// or https://');
  return url;
}

function validateRepoUrl_(value) {
  const url = optionalText_(value, 2048);
  if (!url) return '';
  if (!/^https?:\/\/(www\.)?github\.com\/[^/]+\/[^/]+(?:\/.*)?$/i.test(url)) {
    throw new Error('Invalid GitHub repository URL');
  }
  return url;
}

function constantTimeEquals_(a, b) {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

function jsonOutput_(object) {
  return ContentService.createTextOutput(JSON.stringify(object))
    .setMimeType(ContentService.MimeType.JSON);
}
