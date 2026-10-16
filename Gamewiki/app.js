"use strict";

const STATE = {
  data: null,
  game: "gs",
  search: "",
  onlyMissing: false,
  stars: new Set(),   // 选中的星级筛选，空=全部
  collapsed: new Set(),
};

const GAME_LABELS = { gs: "原神", sr: "崩坏：星穹铁道", zzz: "绝区零" };

function $(sel) { return document.querySelector(sel); }

async function loadData() {
  // 优先走本地服务接口（实时），失败则回退到快照文件
  try {
    const r = await fetch("/api/data", { cache: "no-store" });
    if (r.ok) return await r.json();
  } catch (e) { /* file:// 场景 */ }
  try {
    const r = await fetch("data/characters.json", { cache: "no-store" });
    if (r.ok) return await r.json();
  } catch (e) {}
  return null;
}

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.remove("hidden");
  clearTimeout(t._t);
  t._t = setTimeout(() => t.classList.add("hidden"), 2200);
}

function renderTabs() {
  const tabs = $("#tabs");
  tabs.innerHTML = "";
  for (const g of Object.keys(STATE.data.games)) {
    const el = document.createElement("div");
    el.className = "tab" + (g === STATE.game ? " active" : "");
    el.textContent = STATE.data.games[g].label || GAME_LABELS[g];
    el.onclick = () => { STATE.game = g; renderAll(); };
    tabs.appendChild(el);
  }
}

// 绝区零：S/A 级显示（内部仍用 5/4 便于排序与筛选）
function zzzRank(s) { s = parseInt(s) || 0; return s >= 5 ? "S" : s >= 4 ? "A" : ""; }
function starText(game, s) {
  s = parseInt(s) || 0;
  return game === "zzz" ? (zzzRank(s) ? zzzRank(s) + "级" : "") : "★".repeat(s);
}

function renderStarFilter(g) {
  const f = $("#starFilter");
  f.innerHTML = "";
  const game = STATE.data.games[g];
  if (game.status !== "ok") return;
  const stars = new Set();
  for (const el of Object.keys(game.elements || {}))
    for (const s of Object.keys(game.elements[el]))
      stars.add(s);
  for (const s of ["5", "4", "3", "2", "1"]) {
    if (!stars.has(s)) continue;
    const el = document.createElement("div");
    el.className = "chip" + (STATE.stars.has(s) ? " on" : "");
    el.textContent = g === "zzz" ? zzzRank(parseInt(s)) : "★" + s;
    el.onclick = () => {
      if (STATE.stars.has(s)) STATE.stars.delete(s); else STATE.stars.add(s);
      renderAll();
    };
    f.appendChild(el);
  }
}

function renderSummary(g) {
  const game = STATE.data.games[g];
  const s = $("#summary");
  if (game.status !== "ok") { s.textContent = ""; return; }
  const pct = game.total ? Math.round(game.added / game.total * 100) : 0;
  s.innerHTML = `总数 <b>${game.total}</b> · ` +
    `<span class="ok">已添加 ${game.added}</span> · ` +
    `<span class="miss">未添加 ${game.missing}</span> · 完成度 <b>${pct}%</b>`;
}

function charMatch(c) {
  if (STATE.onlyMissing && c.added) return false;
  if (STATE.stars.size && !STATE.stars.has(String(c.star))) return false;
  if (STATE.search && !c.name.includes(STATE.search)) return false;
  return true;
}

function renderContent() {
  const c = $("#content");
  const game = STATE.data.games[STATE.game];
  c.innerHTML = "";

  if (game.status === "pending") {
    const d = document.createElement("div");
    d.className = "pending";
    d.innerHTML = `<div class="big">${game.label} · 待定</div>` +
      `<div>${game.note || ""}</div>`;
    c.appendChild(d);
    return;
  }

  const elements = game.elements || {};
  const elemIcons = game.elemIcons || {};
  let shownTotal = 0, shownMiss = 0;
  for (const el of Object.keys(elements)) {
    const starsMap = elements[el];
    const charsInEl = [];
    for (const s of Object.keys(starsMap))
      for (const ch of starsMap[s])
        if (charMatch(ch)) charsInEl.push(ch);
    if (!charsInEl.length) continue;

    const elMiss = charsInEl.filter(x => !x.added).length;
    const coEl = document.createElement("div");
    coEl.className = "group";
    const head = document.createElement("div");
    head.className = "group-head";
    const icon = elemIcons[el];
    const iconHtml = icon ? `<img class="elem-icon" src="${icon}" alt="${el}" onerror="this.style.display='none'"/>` : "";
    head.innerHTML = `${iconHtml}<h2>${el}</h2><span class="cnt">${charsInEl.length} 个</span>` +
      (elMiss ? `<span class="misscnt">未添加 ${elMiss}</span>` : "");
    const body = document.createElement("div");
    body.style.display = STATE.collapsed.has(el) ? "none" : "block";
    head.onclick = () => {
      if (STATE.collapsed.has(el)) STATE.collapsed.delete(el);
      else STATE.collapsed.add(el);
      body.style.display = STATE.collapsed.has(el) ? "none" : "block";
    };
    coEl.appendChild(head);

    for (const s of Object.keys(starsMap).sort((a, b) => b - a)) {
      const row = starsMap[s].filter(charMatch);
      if (!row.length) continue;
      const sb = document.createElement("div");
      sb.className = "starblock";
      const lab = document.createElement("div");
      lab.className = "starlabel";
      lab.textContent = STATE.game === "zzz"
        ? `${zzzRank(parseInt(s))} 级 (${row.length})`
        : "★".repeat(parseInt(s)) + ` ${s} 星 (${row.length})`;
      sb.appendChild(lab);
      const grid = document.createElement("div");
      grid.className = "cards";
      for (const ch of row) {
        const el = document.createElement("div");
        el.className = `card rarity-${ch.star || 0} g-${STATE.game} ${ch.added ? "added" : "missing"}`;
        const av = ch.avatar
          ? `<img class="card-face" src="${encodeURI(ch.avatar)}" loading="lazy" alt="${ch.name}" onerror="this.style.display='none'"/>`
          : `<div class="card-noface">${ch.elem || ""}</div>`;
        const lv = ch.levels || {};
        const lvKeys = Object.keys(lv);
        const lvTotal = lvKeys.reduce((s, k) => s + (parseInt(lv[k]) || 0), 0);
        const lvGrid = lvKeys.map(k => `<div class="cl-h">${k === "R" ? "R" : k.slice(1)}</div>`).join("") +
          lvKeys.map(k => `<div class="cl-v ${lv[k] ? "on" : "off"}" title="${k}: ${lv[k]} 张">${lv[k]}</div>`).join("");
        el.innerHTML =
          `<div class="card-bg">${av}</div>` +
          `<div class="card-info">` +
            `<div class="card-stars">${starText(STATE.game, ch.star)}</div>` +
            `<div class="card-name">${ch.name}</div>` +
            (lvKeys.length
              ? `<div class="card-levels">${lvGrid}</div><div class="cl-total">总计 <b>${lvTotal}</b></div>`
              : "") +
          `</div>`;
        el.onclick = ch.added
          ? () => openRepoImages(STATE.game, ch.name)
          : () => openAddModal(STATE.game, ch.name);
        grid.appendChild(el);
        shownTotal++; if (!ch.added) shownMiss++;
      }
      sb.appendChild(grid);
      body.appendChild(sb);
    }
    coEl.appendChild(body);
    c.appendChild(coEl);
  }
  if (!shownTotal) {
    c.innerHTML = `<div class="pending">没有匹配的角色</div>`;
  } else {
    const extra = $("#summary");
    extra.innerHTML += ` · 当前显示 <b>${shownTotal}</b>` +
      (shownMiss ? ` <span class="miss">(其中未添加 ${shownMiss})</span>` : "");
  }
}

function renderAll() {
  renderTabs();
  renderStarFilter(STATE.game);
  renderSummary(STATE.game);
  renderContent();
}

function closeRepoLb() {
  const lb = document.getElementById("repoLb");
  if (lb) lb.classList.remove("on");
}

async function openRepoImages(game, name) {
  let lb = document.getElementById("repoLb");
  if (!lb) {
    lb = document.createElement("div");
    lb.id = "repoLb";
    lb.className = "repo-lb";
    lb.onclick = (e) => { if (e.target === lb) closeRepoLb(); };
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeRepoLb(); });
    document.body.appendChild(lb);
  }
  lb.innerHTML = `<div class="repo-lb-box"><div class="repo-lb-head">` +
    `<span>加载中…</span><button class="repo-lb-close" onclick="closeRepoLb()">关闭</button></div></div>`;
  lb.classList.add("on");
  let data;
  try {
    const r = await fetch(`/api/imgs?game=${encodeURIComponent(game)}&name=${encodeURIComponent(name)}`);
    if (!r.ok) throw new Error("HTTP " + r.status);
    data = await r.json();
  } catch (err) {
    lb.querySelector(".repo-lb-head span").textContent =
      `无法加载仓库图片（${err.message}）—— 请通过 http://127.0.0.1:11002 打开本页`;
    return;
  }
  const imgs = data.images || [];
  const byLv = {};
  for (const im of imgs) (byLv[im.level] || (byLv[im.level] = [])).push(im);
  let body = "";
  for (const lv of Object.keys(byLv)) {
    body += `<div class="repo-lv">${lv} · ${byLv[lv].length} 张</div><div class="repo-grid">` +
      byLv[lv].map(im =>
        `<figure class="repo-item"><img src="${im.url}" loading="lazy" alt="${im.file}"/>` +
        `<figcaption title="${im.file}">${im.file}</figcaption></figure>`).join("") +
      `</div>`;
  }
  if (!imgs.length) {
    body = `<div class="repo-empty">该角色在仓库中还没有图片<br>` +
      `<code>Miao-MBT-MLY/${gameDir(game)}/R/normal-character/${name}/</code></div>`;
  }
  lb.innerHTML = `<div class="repo-lb-box"><div class="repo-lb-head">` +
    `<span>${name} · ${imgs.length} 张</span>` +
    `<button class="repo-lb-close" onclick="closeRepoLb()">关闭</button></div>` +
    `<div class="repo-lb-body">${body}</div></div>`;
}

function openAddModal(game, name) {
  $("#modalTitle").textContent = `添加角色：${name}`;
  const levels = STATE.data.games[game] ? (window.__rLevels || ["R", "R17", "R18"]) : ["R", "R17", "R18"];
  let sel = "R";
  const body = $("#modalBody");
  body.innerHTML = `<div>选择要创建到哪个分级目录（数据仓库 <code>Miao-MBT-MLY/${gameDir(game)}/&lt;分级&gt;/normal-character/${name}/</code>）：</div>` +
    `<div class="rlevel-row" id="rrow"></div>` +
    `<div class="hint" id="addHint"></div>`;
  const row = $("#rrow");
  for (const lv of levels) {
    const b = document.createElement("button");
    b.className = "btn" + (lv === sel ? " sel" : "");
    b.textContent = lv;
    b.onclick = () => { sel = lv; [...row.children].forEach(x => x.classList.remove("sel")); b.classList.add("sel"); };
    row.appendChild(b);
  }
  const hint = $("#addHint");
  hint.innerHTML = "点击“确认添加”将在数据仓库创建该角色目录（仅建文件夹，图片请后续自行放入）。";
  const ok = document.createElement("button");
  ok.className = "btn";
  ok.textContent = "确认添加";
  ok.style.marginTop = "12px";
  ok.style.width = "100%";
  ok.onclick = async () => {
    await doAdd(game, name, sel);
    closeModal();
  };
  body.appendChild(ok);
  $("#modal").classList.remove("hidden");
}

function gameDir(g) {
  return { gs: "genshin", sr: "starrail", zzz: "zzz" }[g] || g;
}

async function doAdd(game, name, rlevel) {
  try {
    const r = await fetch("/api/add", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ game, name, rlevel }),
    });
    if (r.ok) {
      toast(`已添加 ${name} → ${rlevel}`);
      await refresh();
      return;
    }
    const e = await r.json().catch(() => ({}));
    throw new Error(e.error || "添加失败");
  } catch (err) {
    // 没有服务端（file:// 直接打开）时，给出命令行提示
    toast("未连接服务，请用命令行添加");
    const body = $("#modalBody");
    body.innerHTML = `<div class="hint">当前网页以 <code>file://</code> 方式打开，无法自动写入文件。请运行：</div>` +
      `<div class="hint"><code>python Gamewiki/add.py ${game} ${name} ${rlevel}</code></div>` +
      `<div class="hint">或先启动服务：<code>python Gamewiki/server.py</code> 再点刷新。</div>`;
    $("#modal").classList.remove("hidden");
  }
}

function closeModal() { $("#modal").classList.add("hidden"); }

async function refresh() {
  STATE.data = await loadData();
  if (!STATE.data) {
    $("#content").innerHTML = `<div class="pending">无法加载数据。请运行 <code>python Gamewiki/server.py</code> 后打开 http://127.0.0.1:11002，或直接用浏览器打开本页（需先执行 <code>python Gamewiki/server.py --export</code> 生成快照）。</div>`;
    return;
  }
  $("#genTime").textContent = "数据时间: " + (STATE.data.generatedAt || "");
  renderAll();
}

function bind() {
  $("#refreshBtn").onclick = refresh;
  $("#search").oninput = (e) => { STATE.search = e.target.value.trim(); renderContent(); };
  $("#onlyMissing").onchange = (e) => { STATE.onlyMissing = e.target.checked; renderContent(); };
  $("#modalClose").onclick = closeModal;
  $("#modal").onclick = (e) => { if (e.target.id === "modal") closeModal(); };
  // 预取分级列表
  fetch("/api/config").then(r => r.json()).then(j => { window.__rLevels = j.rLevels; }).catch(() => {});
}

(async function init() {
  bind();
  await refresh();
})();
