(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const state = { tasks: [], notes: [], sites: [] };
  const today = new Date();
  const todayKey = [today.getFullYear(), String(today.getMonth()+1).padStart(2,"0"), String(today.getDate()).padStart(2,"0")].join("-");
  $("today-date").textContent = todayKey;
  $("heading-date").textContent = todayKey;

  const API_URL = "https://script.google.com/macros/s/AKfycby_zE6lY6V2bW852BSiYyiBW8BW_5jeHjuqbfhDRj9mYrFmaAu-REdS4wEv4GV1nC_E/exec";
  const pending = new Map();
  let requestCounter = 0;

  function setStatus(message, isError = false) {
    const node = $("status-message");
    node.textContent = message;
    node.classList.toggle("error", isError);
    $("sidebar-status").textContent = isError ? "接続エラー" : "Google Sheets";
  }

  function callApi(action, args = {}) {
    return new Promise((resolve, reject) => {
      const requestId = "lifeos-" + Date.now() + "-" + (++requestCounter);
      const timer = setTimeout(() => {
        pending.delete(requestId);
        reject(new Error("Google Apps Scriptから応答がありません。デプロイ設定を確認してください。"));
      }, 25000);
      pending.set(requestId, { resolve, reject, timer });
      $("bridge-payload").value = JSON.stringify({
        transport: "iframe-postMessage", requestId, action, args
      });
      $("bridge-form").action = API_URL;
      $("bridge-form").submit();
    });
  }

  window.addEventListener("message", (event) => {
    if (event.source !== $("lifeos-api-frame").contentWindow) return;
    const data = event.data;
    if (!data || data.type !== "EA_DATA_RESULT" || typeof data.requestId !== "string") return;
    const item = pending.get(data.requestId);
    if (!item) return;
    clearTimeout(item.timer);
    pending.delete(data.requestId);
    if (data.ok) item.resolve(data.data);
    else item.reject(new Error(data.error || "Google保存APIでエラーが発生しました。"));
  });

  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
      "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"
    }[ch]));
  }
  function normalizeDate(value) {
    if (!value) return "";
    if (typeof value === "string") return value.slice(0, 10);
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? String(value).slice(0,10) : date.toISOString().slice(0,10);
  }
  function showEmpty(container, message, hint) {
    container.innerHTML = '<div class="empty-state"><span>◇</span><p>' + esc(message) + '</p><small>' + esc(hint) + '</small></div>';
  }
  function renderTasks() {
    const list = $("task-list");
    const done = state.tasks.filter(t => Number(t.done) === 1).length;
    const active = state.tasks.length - done;
    $("active-count").innerHTML = active + "<small> 件</small>";
    $("done-count").innerHTML = done + "<small> 件</small>";
    $("task-total").textContent = state.tasks.length;
    const donePercent = state.tasks.length ? Math.round(done / state.tasks.length * 100) : 0;
    $("active-bar").style.width = (100-donePercent) + "%";
    $("done-bar").style.width = donePercent + "%";
    if (!state.tasks.length) {
      showEmpty(list, "タスクはまだありません。", "まずは、今日やりたいことをひとつ追加してみよう。");
      return;
    }
    list.innerHTML = state.tasks.slice().sort((a,b) => Number(a.done)-Number(b.done) || Number(b.id)-Number(a.id)).map(task =>
      '<div class="task-row ' + (Number(task.done) ? "is-done" : "") + '">' +
        '<button class="check-button" type="button" data-task-toggle="' + Number(task.id) + '" aria-label="完了状態を切り替える">' + (Number(task.done) ? "✓" : "") + '</button>' +
        '<div class="task-info"><span class="task-title">' + esc(task.title) + '</span><small>' + (Number(task.done) ? "完了" : "取り組み中") + '</small></div>' +
        '<button type="button" class="icon-button" data-task-delete="' + Number(task.id) + '" aria-label="タスクを削除">×</button>' +
      '</div>'
    ).join("");
  }
  function renderSites() {
    const list = $("site-list");
    $("site-total").textContent = state.sites.length;
    if (!state.sites.length) {
      showEmpty(list, "まだサイトが登録されていません。", "公開URLとGitHubリポジトリURLを登録して、自分のサイトを整理しよう。");
      return;
    }
    list.innerHTML = state.sites.slice().sort((a,b) => Number(b.id)-Number(a.id)).map(site =>
      '<article class="site-card"><div class="site-card-top"><span class="site-symbol">⌘</span><span class="site-category">' + esc(site.category || "その他") + '</span></div>' +
      '<h3>' + esc(site.name) + '</h3><p class="site-description">' + esc(site.description || "説明はまだありません。") + '</p>' +
      '<a class="site-url" href="' + esc(site.url) + '" target="_blank" rel="noopener noreferrer"><span>' + esc(site.url) + '</span><span>↗</span></a>' +
      (site.repo_url ? '<a class="site-url repo-url" href="' + esc(site.repo_url) + '" target="_blank" rel="noopener noreferrer"><span>GitHub リポジトリ</span><span>↗</span></a>' : '') +
      '<div class="site-card-actions"><a class="button secondary" href="' + esc(site.url) + '" target="_blank" rel="noopener noreferrer">サイトを開く ↗</a>' +
      (site.repo_url ? '<a class="button backup-button" href="' + esc(site.repo_url) + '" target="_blank" rel="noopener noreferrer">GitHubを見る ↗</a>' : '') +
      '<button class="icon-button" type="button" data-site-delete="' + Number(site.id) + '" aria-label="サイトを削除">×</button></div></article>'
    ).join("");
  }
  async function reloadData() {
    setStatus("Google保存先に接続しています…");
    const data = await callApi("get_all");
    state.tasks = Array.isArray(data.tasks) ? data.tasks : [];
    state.notes = Array.isArray(data.notes) ? data.notes : [];
    state.sites = Array.isArray(data.sites) ? data.sites : [];
    renderTasks();
    renderSites();
    const note = state.notes.find(n => normalizeDate(n.note_date) === todayKey);
    $("daily-note").value = note ? String(note.content || "") : "";
    setStatus("Googleスプレッドシートに接続済み。変更はGoogle側に保存されます。");
  }
  async function runAction(action, args, successMessage) {
    setStatus("保存しています…");
    try {
      await callApi(action, args);
      await reloadData();
      if (successMessage) setStatus(successMessage);
    } catch (error) {
      setStatus(error.message || "処理に失敗しました。", true);
    }
  }

  $("task-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const title = $("task-title").value.trim();
    if (!title) return;
    await runAction("task_add", { title, created_at: todayKey }, "タスクを保存しました。");
    $("task-title").value = "";
  });
  $("task-list").addEventListener("click", async (event) => {
    const toggle = event.target.closest("[data-task-toggle]");
    const del = event.target.closest("[data-task-delete]");
    if (toggle) await runAction("task_toggle", { id: Number(toggle.dataset.taskToggle) }, "タスクを更新しました。");
    if (del && confirm("このタスクを削除しますか？")) await runAction("task_delete", { id: Number(del.dataset.taskDelete) }, "タスクを削除しました。");
  });
  $("site-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const site = {
      name: $("site-name").value.trim(),
      url: $("site-url").value.trim(),
      repo_url: $("site-repo").value.trim(),
      category: $("site-category").value,
      description: $("site-description").value.trim(),
      created_at: new Date().toISOString()
    };
    if (!site.name || !site.url) return;
    await runAction("site_add", site, "サイト情報を保存しました。");
    $("site-form").reset();
  });
  $("site-list").addEventListener("click", async (event) => {
    const del = event.target.closest("[data-site-delete]");
    if (del && confirm("このサイト情報を削除しますか？")) {
      await runAction("site_delete", { id: Number(del.dataset.siteDelete) }, "サイト情報を削除しました。");
    }
  });
  $("note-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    await runAction("note_save", { note_date: todayKey, content: $("daily-note").value }, "今日のノートを保存しました。");
  });
  $("refresh-button").addEventListener("click", () => reloadData().catch(error => setStatus(error.message, true)));
  $("export-button").addEventListener("click", async () => {
    try {
      const data = await callApi("get_all");
      const backup = {
        app: "LifeOS", version: 1, exported_at: new Date().toISOString(),
        tasks: data.tasks || [], notes: data.notes || [], sites: data.sites || []
      };
      const blob = new Blob([JSON.stringify(backup, null, 2)], {type:"application/json"});
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = "lifeos-backup-" + todayKey + ".json"; a.click();
      URL.revokeObjectURL(url);
      setStatus("バックアップを書き出しました。");
    } catch(error) { setStatus(error.message, true); }
  });
  $("backup-file").addEventListener("change", async (event) => {
    const file = event.target.files && event.target.files[0];
    if (!file) return;
    try {
      const backup = JSON.parse(await file.text());
      if (!Array.isArray(backup.tasks) || !Array.isArray(backup.notes) || !Array.isArray(backup.sites)) {
        throw new Error("バックアップ形式が正しくありません。");
      }
      if (!confirm("現在のタスク・ノート・サイト情報をこのバックアップで置き換えますか？")) {
        event.target.value = "";
        return;
      }
      await runAction("backup_replace", {data: {
        tasks: backup.tasks, notes: backup.notes, sites: backup.sites
      }}, "バックアップから復元しました。");
    } catch(error) {
      setStatus(error.message || "バックアップを読み込めませんでした。", true);
    } finally { event.target.value = ""; }
  });

  reloadData().catch(error => setStatus(
    "Google保存APIに接続できませんでした。Apps Scriptを「自分のみ」で再デプロイし、Googleにログインした状態で再読み込みしてください。詳細: " + error.message,
    true
  ));
})();