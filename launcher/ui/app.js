// TotK Launcher page, laid out after the Figma design. Talks to launcher.pyw through window.pywebview.api (every call
// returns a Promise).
"use strict";

const api = () => window.pywebview.api;
window.addEventListener("error", (e) => { try { api().log(`${e.message} @${e.lineno}:${e.colno}`); } catch (_) {} });
window.addEventListener("unhandledrejection", (e) => {
  // a Python error in an API call: show it instead of a button that seems to do nothing
  const msg = e.reason && (e.reason.message || e.reason);
  try { api().log(`promise: ${e.reason && (e.reason.stack || msg)}`); } catch (_) {}
  try { toast(`Error: ${msg}`); } catch (_) {}
});
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const el = (html) => { const t = document.createElement("template"); t.innerHTML = html.trim(); return t.content.firstElementChild; };

let S = {};          // strings in the current language
let BOOT = null;     // api.boot()
let PAGE = "home";
let STATE = "ready";

// ------------------------------------------------------------------ icons (from the design)
const ICON = {
  home: '<path d="m3 10 9-7 9 7"/><path d="M5 9v11h14V9M9 20v-6h6v6"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.83 2.83-.06-.06a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1 1.55V21h-4v-.08a1.7 1.7 0 0 0-1-1.55 1.7 1.7 0 0 0-1.88.34l-.06.06-2.83-2.83.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-1.55-1H3v-4h.08a1.7 1.7 0 0 0 1.55-1 1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.83-2.83.06.06A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-1.55V3h4v.08a1.7 1.7 0 0 0 1 1.55 1.7 1.7 0 0 0 1.88-.34l.06-.06 2.83 2.83-.06.06A1.7 1.7 0 0 0 19.4 9a1.7 1.7 0 0 0 1.55 1H21v4h-.08a1.7 1.7 0 0 0-1.52 1Z"/>',
  controls: '<path d="M8 7h8a6 6 0 0 1 5.7 7.9l-1 3a2.7 2.7 0 0 1-4.4 1.1l-1.8-1.7h-5L7.7 19a2.7 2.7 0 0 1-4.4-1.1l-1-3A6 6 0 0 1 8 7Z"/><path d="M7 11v4M5 13h4"/><circle cx="17" cy="11.5" r=".7" fill="currentColor"/><circle cx="19" cy="14" r=".7" fill="currentColor"/>',
  saves: '<path d="M5 3h12l3 3v15H4V4a1 1 0 0 1 1-1Z"/><path d="M8 3v6h8V3M8 21v-7h8v7"/>',
  achievements: '<circle cx="12" cy="9" r="6"/><path d="m8.5 14-1 7 4.5-2 4.5 2-1-7"/><path d="m12 6 .8 1.7 1.9.2-1.4 1.3.4 1.8-1.7-.9-1.7.9.4-1.8-1.4-1.3 1.9-.2Z"/>',
  cheats: '<path d="M9 3h6M10 3v5l-5.8 9.5A2.3 2.3 0 0 0 6.2 21h11.6a2.3 2.3 0 0 0 2-3.5L14 8V3"/><path d="M7.5 15h9M9 12h6"/>',
  folder: '<path d="M3 6h7l2 2h9v11H3Z"/><path d="M3 6V4h6l2 2"/>',
  refresh: '<path d="M20 6v5h-5"/><path d="M19 11a7.5 7.5 0 1 0 .1 4"/>',
  external: '<path d="M14 4h6v6M20 4l-9 9"/><path d="M18 13v7H4V6h7"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  gamepad: '<rect x="3" y="6" width="18" height="12" rx="5"/><path d="M8 9v6M5 12h6M16 10h.01M19 14h.01"/>',
  chip: '<rect x="7" y="7" width="10" height="10" rx="1"/><path d="M9 1v3M15 1v3M9 20v3M15 20v3M1 9h3M1 15h3M20 9h3M20 15h3"/>',
  layers: '<path d="m12 2 9 5-9 5-9-5Z"/><path d="m3 12 9 5 9-5M3 17l9 5 9-5"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  download: '<path d="M12 3v12M7 10l5 5 5-5M4 20h16"/>',
  trash: '<path d="M4 7h16M9 3h6l1 4M6 7l1 14h10l1-14M10 11v6M14 11v6"/>',
  restore: '<path d="M4 9V4h5"/><path d="M5 5a9 9 0 1 1-1 10"/>',
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  minus: '<path d="M5 12h14"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7h.01"/>',
  play: '<path d="m8 5 11 7-11 7Z"/>',
  chevron: '<path d="m9 6 6 6-6 6"/>',
};
const icon = (name, size = 18) => `<svg class="i" width="${size}" height="${size}" viewBox="0 0 24 24" aria-hidden="true">${ICON[name]}</svg>`;

// ------------------------------------------------------------------ building blocks
const pageHeader = (title, desc, eyebrow) =>
  `<div class="page-header"><div>${eyebrow ? `<span class="eyebrow">${esc(eyebrow)}</span>` : ""}<h1>${esc(title)}</h1><p>${esc(desc)}</p></div></div>`;
const section = (title, desc, body, cls = "") =>
  `<section class="section ${cls}"><div class="section-head"><div><h2>${esc(title)}</h2>${desc ? `<p>${esc(desc)}</p>` : ""}</div></div>${body}</section>`;
const field = (label, hint, control) =>
  `<div class="field"><div class="field-copy"><label>${esc(label)}</label><p>${esc(hint || "")}</p></div><div class="field-control">${control}</div></div>`;
const button = (label, { variant = "secondary", ic = null, attrs = "" } = {}) =>
  `<button type="button" class="button ${variant}" ${attrs}>${ic ? icon(ic, 16) : ""}${esc(label)}</button>`;
const toggle = (on, attrs = "") => `<button type="button" class="toggle ${on ? "on" : ""}" aria-pressed="${on}" ${attrs}><span></span></button>`;
const select = (options, current, attrs = "") =>
  `<select ${attrs}>${options.map(([v, l]) => `<option value="${esc(v)}" ${String(v) === String(current) ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>`;
const segmented = (options, current, cls = "segmented", attrs = "") =>
  `<div class="${cls}" ${attrs}>${options.map(([v, l]) => `<button type="button" data-v="${esc(v)}" class="${v === current ? "active" : ""}">${esc(l)}</button>`).join("")}</div>`;
const range = (id, lo, hi, value, suffix = "", step = 1) =>
  `<div class="range-control"><input type="range" id="${id}" min="${lo}" max="${hi}" step="${step}" value="${esc(value)}" data-suffix="${suffix}"><output>${esc(value)}${suffix}</output></div>`;

function bindSegmented(root, onPick) {
  $$("button", root).forEach((b) => b.addEventListener("click", () => {
    $$("button", root).forEach((x) => x.classList.toggle("active", x === b));
    onPick(b.dataset.v);
  }));
}
function bindToggles(root) {
  $$(".toggle", root).forEach((t) => t.addEventListener("click", () => {
    const on = !t.classList.contains("on");
    t.classList.toggle("on", on); t.setAttribute("aria-pressed", on);
    t.dispatchEvent(new CustomEvent("toggle", { detail: on }));
  }));
}
function bindRanges(root) {
  $$("input[type=range]", root).forEach((r) => r.addEventListener("input", () => { r.nextElementSibling.textContent = r.value + (r.dataset.suffix || ""); }));
}

function toast(msg) {
  if (!msg) return;
  const t = el(`<div class="toast">${esc(msg)}</div>`);
  $("#toasts").append(t);
  setTimeout(() => { t.classList.add("out"); setTimeout(() => t.remove(), 260); }, 2800);
}

function unlockPopup(ev) {
  const t = el(`<div class="toast unlock"><span>${esc(ev.icon)}</span><div><b>${esc(S.ach_unlocked)}</b><em>${esc(ev.title)}</em>${esc(ev.desc)}</div></div>`);
  $("#toasts").append(t);
  setTimeout(() => { t.classList.add("out"); setTimeout(() => t.remove(), 260); }, 5000);
}

function confirmBox(title, body = "") {
  return new Promise((resolve) => {
    const d = el(`<div class="dialog-backdrop"><div class="dialog">
      <h2>${esc(title)}</h2><p>${esc(body)}</p>
      <div>${button(S.no_cancel, { attrs: 'data-v="0"' })}${button(S.yes_continue, { variant: "primary", attrs: 'data-v="1"' })}</div></div></div>`);
    document.body.append(d);
    const done = (v) => { d.remove(); resolve(v); };
    $$("[data-v]", d).forEach((b) => b.addEventListener("click", () => done(b.dataset.v === "1")));
    d.addEventListener("mousedown", (e) => { if (e.target === d) done(false); });
  });
}

// ------------------------------------------------------------------ theme
function applyTheme() {
  const theme = (BOOT && BOOT.cfg.theme) === "night" ? "night" : "light";
  document.documentElement.dataset.theme = theme;
  try { api().title_bar(theme === "night", theme === "night" ? "#182935" : "#f2d4ac"); } catch (_) {}
}

// ------------------------------------------------------------------ shell
const PAGES_ORDER = ["home", "settings", "controls", "mods", "saves", "achievements", "cheats"];
const pageName = (p) => (p === "mods" ? S.mods_page : S[p]);
const FPS = () => [["30", "30"], ["60", "60"], ["120", "120"], ["144", "144"], ["display", S.monitor]];

function renderShell() {
  document.documentElement.lang = BOOT.lang;
  $("#root").innerHTML = `<div class="app-shell">
    <aside class="sidebar">
      <div class="brand"><img src="img/icon.png" alt=""><div class="wordmark">TotK Launcher<span>Tears of the Kingdom</span></div></div>
      <nav>${PAGES_ORDER.map((p) => `<button type="button" data-page="${p}"><span>${esc(pageName(p))}</span>${p === "achievements" ? '<i id="achcount" class="hidden"></i>' : ""}</button>`).join("")}</nav>
      <div class="sidebar-bottom">
        <div class="mod-toggle"><div><strong>${esc(S.load_mods)}</strong><span>romfs_mods</span></div>${toggle(BOOT.cfg.mods, 'id="mods"')}</div>
        <div class="play-panel"><button type="button" class="play-button" data-play></button><span class="playstate"><i></i><em></em></span></div>
      </div>
    </aside>
    <div class="main-column">
      <header class="titlebar"><div><span class="titlebar-page" id="pagename"></span><span class="path">${esc(BOOT.root)}\\totk.exe</span></div></header>
      <main id="main"></main>
    </div>
  </div>`;
  $$("nav button").forEach((b) => b.addEventListener("click", () => go(b.dataset.page)));
  $$("[data-play]").forEach((b) => b.addEventListener("click", play));
  bindToggles($(".mod-toggle"));
  $("#mods").addEventListener("toggle", async (e) => {
    BOOT.cfg.mods = e.detail;
    await api().set_option("mods", e.detail);
    if (["home", "controls", "mods"].includes(PAGE)) go(PAGE, true);
  });
  showState(STATE);
  achCount();
}

async function achCount() {
  const d = await api().achievements();
  const n = d.items.filter((a) => a.unlocked).length, badge = $("#achcount");
  if (!badge) return;
  badge.textContent = n;
  badge.classList.toggle("hidden", n === 0);
}

function showState(state) {
  STATE = state;
  const label = { ready: S.play, preparing: S.preparing, running: S.running, closed: S.play_again }[state];
  const busy = state === "preparing" || state === "running";
  $$("[data-play]").forEach((btn) => {
    btn.className = "play-button " + state;
    btn.innerHTML = (busy ? "" : '<svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 3.5v17L20 12z"/></svg>') + esc(label);
  });
  $$(".playstate").forEach((st) => {
    $("i", st).className = state;
    $("em", st).textContent = { ready: S.st_ready, running: S.st_running, closed: S.st_closed, preparing: S.st_preparing }[state];
  });
}

async function play() {
  if (STATE === "running" || STATE === "preparing") return;
  const res = await api().play();
  if (!res.ok) toast(res.message); else showState("preparing");
}

async function poll() {
  try {
    const st = await api().status();
    if (st.state !== STATE) showState(st.state);
    for (const ev of st.events) {
      if (ev.type === "toast") toast(ev.message);
      else if (ev.type === "achievement") unlockPopup(ev);
      else if (ev.type === "achievements_changed") { achCount(); if (PAGE === "achievements" && !CAPTURE) go("achievements", true); }
    }
  } catch (e) { /* the window is closing */ }
  setTimeout(poll, 1200);
}

async function go(page, keepScroll = false) {
  PAGE = page;
  CAPTURE = null;
  $$("nav button").forEach((b) => b.classList.toggle("active", b.dataset.page === page));
  $("#pagename").textContent = pageName(page);
  $("#main").classList.toggle("home", page === "home");
  $(".app-shell").classList.toggle("on-home", page === "home");
  const main = $("#main");
  const y = main.scrollTop;
  const out = await PAGES[page]();
  if (PAGE !== page) return;           // another page was chosen meanwhile
  main.innerHTML = out.html;
  main.scrollTop = keepScroll ? y : 0;
  bindToggles(main); bindRanges(main);
  out.after && out.after(main);
}

// ------------------------------------------------------------------ pages
const PAGES = {};

let LOG_OPEN = false;
const num = (v, digits = 0) => Number(v).toLocaleString(BOOT.lang, { minimumFractionDigits: digits, maximumFractionDigits: digits });
function duration(sec) {
  const tr = BOOT.lang === "tr", m = Math.round(sec / 60);
  if (sec < 60) return `${Math.round(sec)} ${tr ? "sn" : "s"}`;
  if (m < 60) return `${m} ${tr ? "dk" : "min"}`;
  return `${Math.floor(m / 60)} ${tr ? "sa" : "h"} ${m % 60} ${tr ? "dk" : "min"}`;
}

const played = (play) => (play && play.seconds > 0
  ? `${duration(play.seconds)} · ${num(play.sessions)} ${S.sessions}` : "");

PAGES.home = async () => {
  const d = await api().home();
  const ss = d.session;
  const cell = (label, value, note = "", id = "") =>
    `<div class="fact"${id ? ` id="${id}"` : ""}><span>${esc(label)}</span><b>${value}</b><small>${note}</small></div>`;
  const sessions = d.play && d.play.sessions ? ` · ${num(d.play.sessions)} ${esc(S.sessions)}` : "";
  const board = [
    cell(S.play_time, d.play_time ? esc(duration(d.play_time)) : esc(S.no_play), d.play_time ? esc(S.from_save) + sessions : sessions.slice(3)),
    cell(S.last_session, esc(d.last || "—"), ss ? `${esc(duration(ss.seconds))} · ${esc(S.fps_avg)} <em>${num(ss.mean, 1)} FPS</em> · ${esc(S.low_fps)} ${num(ss.low, 1)}` : ""),
    cell(S.game_ver, esc(d.game_version || "?"), d.exe ? `<i class="ok">totk.exe ✓</i>` : `<i class="bad">totk.exe ${esc(S.not_found)}</i>`),
    cell(S.recomp_ver, esc(d.recomp || "?"), esc(d.recomp_build || ""), "recompcell"),
    cell(S.gpu, esc((d.gpu || S.unknown).replace(/\s*\((TM|R)\)/gi, "")), "", "gpucell"),
    cell(S.mods, `${d.mods} ${esc(S.files)}`, `${esc(d.mods_on ? S.on : S.off)} · romfs-patches: ${d.patches}`),
  ].join("");
  return {
    html: `<h1 class="home-title">${esc(S.game_title)}</h1>
      <div class="board">${board}</div>
      <div class="updates" id="updates"></div>
      <div class="launch"><span class="playstate"><i></i><em></em></span><button type="button" class="play-button" data-play></button></div>`,
    after(p) {
      $$("[data-play]", p).forEach((b) => b.addEventListener("click", play));
      showState(STATE);
      api().updates().then((u) => {
        if (!u) return;
        const rc = $("#recompcell small", p);
        if (rc) rc.innerHTML = u.recomp
          ? `<i class="new">${esc(u.recomp.tag)} ${esc(S.available)}</i> · <a class="link" data-url="${esc(u.recomp.url)}">${esc(S.release_notes)}</a>`
          : `${esc(d.recomp_build || "")}${d.recomp_build ? " · " : ""}${esc(S.up_to_date)}`;
        const box = $("#updates", p);
        if (box && u.launcher) box.innerHTML = `<p>${esc(S.update_launcher)}: <b>${esc(u.launcher.tag)}</b> (${esc(S.update_have)} ${esc(u.launcher.have)})
          · <a class="link" data-url="${esc(u.launcher.url)}">${esc(S.release_notes)}</a></p>`;
        $$("[data-url]", p).forEach((a) => a.addEventListener("click", () => api().open_url(a.dataset.url)));
      }).catch(() => {});
    },
  };
};

// "FRAME RATE" -> "Frame rate" (the settings schema writes its group titles in capitals)
const sentence = (s) => { const l = s.toLocaleLowerCase(BOOT.lang); return l.charAt(0).toLocaleUpperCase(BOOT.lang) + l.slice(1); };

PAGES.settings = async () => {
  const d = await api().settings();
  const control = (it) => {
    const id = `s_${it.key}`;
    if (it.kind === "bool") return toggle(!["", "0", "false", "off"].includes(String(it.value)), `id="${id}"`);
    if (it.kind === "scale") return range(id, it.choices[0], it.choices[1], it.value, "", it.choices[2] || 1);
    if (it.kind === "gpu") return select([["", S.automatic], ...d.gpus.map(([i, n]) => [i, `${i}: ${n}`])], it.value, `id="${id}"`);
    if (it.kind === "combo") return `<input type="text" class="combo" id="${id}" list="${id}_l" value="${esc(it.value)}"><datalist id="${id}_l">${it.choices.map((c) => `<option value="${esc(c)}">`).join("")}</datalist>`;
    const choices = it.choices.includes(it.value) ? it.choices : [it.value, ...it.choices];
    return select(choices.map((c) => [c, c]), it.value, `id="${id}"`);
  };
  return {
    html: `${pageHeader(S.settings, S.settings_sub)}
      ${section(S.launcher, "", field(S.ui_lang, S.lang_hint, select(BOOT.langs, BOOT.lang, 'id="lang"'))
        + field(S.theme, S.theme_help, select([["light", S.theme_light], ["night", S.theme_night]], BOOT.cfg.theme, 'id="theme"'))
        + field(S.game_folder, S.folder_hint, `<div class="inline-control"><input value="${esc(BOOT.root)}" readonly>${button(S.change, { attrs: 'id="chgame"' })}</div>`)
        + field(S.check_updates, S.check_updates_hint, toggle(BOOT.cfg.check_updates, 'id="checkupd"'))
        + field(S.shortcut, S.shortcut_hint, button(S.shortcut, { attrs: 'id="shortcut"' })))}
      ${d.groups.map((g) => section(sentence(g.title), "", g.items.map((it) => field(it.label, it.help, control(it))).join(""))).join("")}
      <section class="section log-section">
        <button type="button" class="section-toggle" id="logtoggle"><div><h2>${esc(S.recent_log)}</h2><p>${esc(S.log_sub)}</p></div><span class="${LOG_OPEN ? "rotate" : ""}">${icon("chevron")}</span></button>
        <div id="logbody" class="${LOG_OPEN ? "" : "hidden"}"><div class="log-box" id="log"><code></code></div>
          <div class="button-row">${button(S.refresh, { attrs: 'id="refresh"' })}${button(S.log_folder, { attrs: 'data-open="logs"' })}${button(S.game_folder_btn, { attrs: 'data-open="game"' })}</div></div>
      </section>
      <div class="sticky-actions"><span>${esc(S.backup_note)}</span><div>
        ${button(S.open_ini, { variant: "ghost", attrs: 'id="openini"' })}${button(S.reset_defaults, { attrs: 'id="reset"' })}${button(S.save_settings, { variant: "primary", attrs: 'id="save"' })}</div></div>`,
    after(p) {
      $("#lang", p).addEventListener("change", async (e) => { BOOT = await api().set_lang(e.target.value); S = BOOT.strings; renderShell(); go("settings"); });
      $("#theme", p).addEventListener("change", async (e) => { BOOT.cfg.theme = e.target.value; await api().set_option("theme", e.target.value); applyTheme(); });
      $("#chgame", p).addEventListener("click", async () => { const r = await api().choose_game(); if (r.message) toast(r.message); });
      $("#openini", p).addEventListener("click", () => api().open_ini());
      $("#checkupd", p).addEventListener("toggle", (e) => { BOOT.cfg.check_updates = e.detail; api().set_option("check_updates", e.detail); });
      $("#shortcut", p).addEventListener("click", async () => toast((await api().shortcut()).message));
      const loadLog = async () => {
        const text = (await api().recent_log()) || S.no_log, log = $("#log", p);
        if (!log) return;
        $("code", log).innerHTML = text.split("\n").map((line) => {
          if (/ready|started|success/i.test(line)) return `<span class="log-ok">${esc(line)}</span>`;
          const m = /^(\[[^\]]*\])(.*)$/.exec(line);
          return m ? `<span class="log-muted">${esc(m[1])}</span>${esc(m[2])}` : esc(line);
        }).join("\n");
        log.scrollTop = log.scrollHeight;
      };
      if (LOG_OPEN) loadLog();
      $("#logtoggle", p).addEventListener("click", (e) => {
        LOG_OPEN = !LOG_OPEN;
        $("span", e.currentTarget).classList.toggle("rotate", LOG_OPEN);
        $("#logbody", p).classList.toggle("hidden", !LOG_OPEN);
        if (LOG_OPEN) loadLog();
      });
      $("#refresh", p).addEventListener("click", loadLog);
      $$("[data-open]", p).forEach((b) => b.addEventListener("click", () => api().open_folder(b.dataset.open)));
      $("#save", p).addEventListener("click", async () => {
        const values = {};
        d.groups.forEach((g) => g.items.forEach((it) => {
          const x = $(`#s_${it.key}`, p);
          values[it.key] = it.kind === "bool" ? x.classList.contains("on") : x.value;
        }));
        toast((await api().save_settings(values)).message);
      });
      $("#reset", p).addEventListener("click", async () => {
        if (await confirmBox(S.reset_defaults + "?", S.settings_sub)) { toast((await api().reset_settings()).message); go("settings"); }
      });
    },
  };
};

// key capture: KeyboardEvent.code -> the game's key names
const CODE_KEYS = {
  Space: "space", Tab: "tab", Enter: "enter", Backspace: "backspace", ShiftLeft: "lshift", ShiftRight: "rshift",
  ControlLeft: "lctrl", ControlRight: "rctrl", AltLeft: "lalt", CapsLock: "capslock", Insert: "insert", Delete: "delete",
  Home: "home", End: "end", PageUp: "pageup", PageDown: "pagedown", ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left",
  ArrowRight: "right", F2: "f2", F3: "f3", F4: "f4", F5: "f5", F6: "f6", F7: "f7", F9: "f9", F12: "f12",
  NumpadAdd: "num_add", NumpadSubtract: "num_sub", NumpadMultiply: "num_mul", NumpadDivide: "num_div",
  NumpadDecimal: "num_decimal", Minus: "minus", Equal: "equals", BracketLeft: "lbracket", BracketRight: "rbracket",
  Semicolon: "semicolon", Quote: "apostrophe", Comma: "comma", Period: "period", Slash: "slash", Backslash: "backslash",
  Backquote: "grave", IntlBackslash: "backslash",
};
function keyFromCode(code) {
  if (/^Key[A-Z]$/.test(code)) return code.slice(3).toLowerCase();
  if (/^Digit\d$/.test(code)) return code.slice(5);
  if (/^Numpad\d$/.test(code)) return "num" + code.slice(6);
  return CODE_KEYS[code] || null;
}
const MOUSE_KEYS = ["mouse_l", "mouse_m", "mouse_r", "mouse_x1", "mouse_x2"];
let CAPTURE = null;   // {b, i, armed}
let CTRL = null;      // controls page state

document.addEventListener("keydown", (e) => {
  if (!CAPTURE) return;
  e.preventDefault();
  if (e.code === "Escape") { CAPTURE = null; CTRL.draw(); return; }
  const k = keyFromCode(e.code);
  if (k) CTRL.assign(k); else toast(`${S.unknown_key} (${e.key})`);
}, true);
document.addEventListener("mousedown", (e) => {
  if (!CAPTURE || !CAPTURE.armed) return;
  e.preventDefault(); e.stopPropagation();
  const k = MOUSE_KEYS[e.button];
  if (!k) return;
  if (CTRL.isStick(CAPTURE.b)) { toast(S.keys_only); CAPTURE = null; CTRL.draw(); return; }
  CTRL.assign(k);
}, true);
document.addEventListener("contextmenu", (e) => e.preventDefault());

PAGES.controls = async () => {
  const d = await api().controls();
  const binds = JSON.parse(JSON.stringify(d.binds));
  const sets = d.prompt_sets.map(([v, label]) => [v, label ? S[label] : "Switch"]);
  let prompt = d.prompts, previewTimer = null;
  const padOpts = [["default", S.default], ["none", S.none], ...d.pads];

  CTRL = {
    isStick: (b) => d.buttons.find((x) => x.id === b).stick,
    draw() {
      $$("[data-key]").forEach((c) => {
        const keys = binds[c.dataset.b].keys, i = +c.dataset.i;
        const cap = CAPTURE && CAPTURE.b === c.dataset.b && CAPTURE.i === i;
        c.classList.toggle("listening", !!cap);
        c.classList.toggle("empty", !cap && i >= keys.length);
        c.textContent = cap ? S.press_key : i < keys.length ? d.key_labels[keys[i]] || keys[i] : "—";
      });
    },
    assign(k) {
      const { b, i } = CAPTURE;
      CAPTURE = null;
      const moved = [];
      for (const [other, v] of Object.entries(binds)) {
        if (other !== b && v.keys.includes(k)) { v.keys = v.keys.filter((x) => x !== k); moved.push(d.buttons.find((x) => x.id === other).label); }
      }
      const keys = binds[b].keys.filter((x) => x !== k);
      if (i < keys.length) keys[i] = k; else keys.push(k);
      binds[b].keys = keys;
      CTRL.draw(); schedulePreview();
      if (moved.length) toast(`${d.key_labels[k]} ${S.moved_from} ${moved.join(", ")}`);
    },
  };
  function schedulePreview() { clearTimeout(previewTimer); previewTimer = setTimeout(loadPreview, 250); }
  async function loadPreview() {
    const box = $("#preview"); if (!box) return;
    const r = await api().preview(prompt, binds);
    if ($("#preview") !== box) return;
    box.innerHTML = r.ok ? `<img src="${r.src}" alt="">` : esc(r.message);
  }

  let group = null;
  const rows = d.buttons.map((b) => {
    const head = b.group !== group ? `<div class="binding-group">${esc((group = b.group))}</div>` : "";
    const pad = b.stick ? `<div class="stick">${esc(b.id.startsWith("L") ? S.left_stick : S.right_stick)}</div>`
      : select(padOpts, binds[b.id].pad, `data-pad="${b.id}"`);
    return `${head}<div class="binding-row"><strong>${esc(b.label)}</strong>
      <button type="button" data-key data-b="${b.id}" data-i="0"></button><button type="button" data-key data-b="${b.id}" data-i="1"></button>${pad}</div>`;
  }).join("");

  return {
    html: `${pageHeader(S.controls, S.controls_sub)}
      ${section(S.button_prompts, S.prompts_sub, `<div class="prompt-row">${segmented(sets, prompt, "segmented", 'id="pset"')}
        ${d.available ? "" : `<div class="prompt-note">${esc(S.no_romfs)}</div>`}
        <div class="prompt-strip" id="preview"></div></div>`)}
      ${section(S.input, "", field(S.controller_layout, S.layout_help, select([["auto", S.layout_auto], ["nintendo", S.layout_nintendo], ["xbox", S.layout_xbox], ["xbox_prompts", S.layout_xbox_prompts]], d.pad_layout, 'id="layout"'))
        + field(S.mouse_camera, S.mouse_help, range("sens", 0, 10, d.mouse_sens)))}
      ${section(S.key_bindings, S.bind_help, `<div class="binding-table"><div class="binding-head"><span>${esc(S.action)}</span><span>${esc(S.key1)}</span><span>${esc(S.key2)}</span><span>${esc(S.controller)}</span></div>${rows}</div>`)}
      <div class="sticky-actions"><span>${d.buttons.length} ${esc(S.actions_n)}</span><div>
        ${button(S.undo, { variant: "ghost", attrs: 'id="undo"' })}${button(S.reset_bindings, { attrs: 'id="reset"' })}${button(S.save_bindings, { variant: "primary", attrs: 'id="save"' })}</div></div>`,
    after(p) {
      CTRL.draw(); loadPreview();
      bindSegmented($("#pset", p), async (v) => { prompt = v; await api().set_option("prompts", v); BOOT.cfg.prompts = v; loadPreview(); });
      $$("[data-key]", p).forEach((c) => {
        c.addEventListener("click", () => {
          CAPTURE = { b: c.dataset.b, i: +c.dataset.i, armed: false };
          CTRL.draw();
          setTimeout(() => { if (CAPTURE) CAPTURE.armed = true; }, 150);
        });
        c.addEventListener("contextmenu", () => {
          if (CAPTURE) return;
          const keys = binds[c.dataset.b].keys, i = +c.dataset.i;
          if (i < keys.length) keys.splice(i, 1);
          CTRL.draw(); schedulePreview();
        });
      });
      $("#save", p).addEventListener("click", async () => {
        const pads = {};
        $$("select[data-pad]", p).forEach((s) => { pads[s.dataset.pad] = s.value; });
        toast((await api().save_controls(binds, pads, $("#layout", p).value, +$("#sens", p).value)).message);
        go("controls", true);
      });
      $("#undo", p).addEventListener("click", () => go("controls", true));
      $("#reset", p).addEventListener("click", async () => {
        if (await confirmBox(S.reset_bindings + "?")) { toast((await api().reset_controls()).message); go("controls", true); }
      });
    },
  };
};

PAGES.mods = async () => {
  const d = await api().mods();
  const row = (m) => `<div class="mod-row ${m.on && d.on ? "" : "off"}"><div><strong>${esc(m.name)}</strong>
      <span>${m.files} ${esc(S.files)} · ${m.size} MiB${m.base ? " · " + esc(S.base_mod) : ""}</span>
      ${m.overrides.length ? `<span class="over">${esc(S.replaces)} ${esc(m.overrides.join(", "))}</span>` : ""}</div>
    ${m.base ? `<em>${esc(d.on ? S.on : S.off)}</em>` : toggle(m.on, `data-mod="${esc(m.name)}"`)}</div>`;
  const others = d.items.filter((m) => !m.base);
  return {
    html: `${pageHeader(S.mods_page, S.mods_sub)}
      ${d.on ? "" : `<div class="notice warning"><div><strong>${esc(S.mods_master_off)}</strong></div></div>`}
      ${section(S.mod_list, d.folder, d.items.map(row).join("") + (others.length ? "" : `<div class="empty-note">${esc(S.no_mods)}</div>`)
        + `<div class="button-row padded">${button(S.add_mod, { variant: "primary", attrs: 'id="addmod"' })}${button(S.mods_folder, { attrs: 'data-open="mods"' })}</div>`)}`,
    after(p) {
      $$("[data-mod]", p).forEach((t) => t.addEventListener("toggle", async (e) => { await api().set_mod(t.dataset.mod, e.detail); go("mods", true); }));
      $("#addmod", p).addEventListener("click", async () => { const r = await api().add_mod(); if (r.message) toast(r.message); if (r.ok) go("mods", true); });
      $$("[data-open]", p).forEach((b) => b.addEventListener("click", () => api().open_folder(b.dataset.open)));
    },
  };
};

PAGES.saves = async () => {
  const d = await api().saves();
  const c = BOOT.cfg;
  const kind = (name) => {
    const tag = name.split(" ").slice(2).join(" ");
    return { auto: S.kind_auto, otomatik: S.kind_auto, manual: S.kind_manual, "before-restore": S.kind_before_restore, "before-cheats": S.kind_before_cheats }[tag] || tag;
  };
  const list = d.backups.length ? d.backups.map((b) => `<div class="backup-item">
      <div><strong>${esc(b.name)}</strong><span>${esc(kind(b.name))}</span></div><span class="backup-size">${b.size} MiB</span>
      <div class="backup-actions">${button(S.restore, { attrs: `data-restore="${esc(b.name)}"` })}
        ${button(S.delete, { variant: "ghost danger", attrs: `data-delete="${esc(b.name)}"` })}</div></div>`).join("")
    : `<div class="empty-note">${esc(S.no_backups)}</div>`;
  return {
    html: `${pageHeader(S.saves, S.saves_sub)}
      ${d.slots.length ? section(S.slots, S.slots_sub, `<div class="slot-table">
        <div class="head"></div><div class="head">${esc(S.saved_at)}</div><div class="head">${esc(S.hearts_s)}</div>
        <div class="head">${esc(S.stamina_s)}</div><div class="head">${esc(S.battery_s)}</div><div class="head">${esc(S.rupees_s)}</div><div class="head">${esc(S.play_time)}</div>
        ${d.slots.map((x) => `<div class="name">${esc(x.name)}</div><div>${esc(x.time)}</div><div>${x.hearts ?? "—"}</div>
          <div>${x.stamina == null ? "—" : num(x.stamina, x.stamina % 1 ? 1 : 0)}</div><div>${x.battery ?? "—"}</div><div>${x.rupee == null ? "—" : num(x.rupee)}</div><div>${x.playtime ? esc(duration(x.playtime)) : "—"}</div>`).join("")}
      </div>`) : ""}
      ${section(S.auto_backup, "", field(S.backup_on_play, S.backup_on_play_hint, toggle(c.backup_before_play, 'id="bop"'))
        + field(S.keep, S.keep_hint, `<input class="number-input" type="number" id="keep" min="1" max="100" value="${c.backup_keep}">`)
        + field(S.close_on_play, S.close_hint, toggle(c.close_on_play, 'id="cop"'))
        + `<div class="button-row padded">${button(S.backup_now, { variant: "primary", attrs: 'id="now"' })}${button(S.save_folder, { attrs: 'data-open="saves"' })}${button(S.backup_folder, { attrs: 'data-open="backups"' })}</div>`)}
      ${section(S.backups, S.newest_first, `<div class="backup-list">${list}</div>`)}`,
    after(p) {
      $("#bop", p).addEventListener("toggle", (e) => { BOOT.cfg.backup_before_play = e.detail; api().set_option("backup_before_play", e.detail); });
      $("#cop", p).addEventListener("toggle", (e) => { BOOT.cfg.close_on_play = e.detail; api().set_option("close_on_play", e.detail); });
      $("#keep", p).addEventListener("change", (e) => { BOOT.cfg.backup_keep = Math.max(1, Math.min(100, +e.target.value || 10)); api().set_option("backup_keep", BOOT.cfg.backup_keep); });
      $("#now", p).addEventListener("click", async () => { toast((await api().backup_now()).message); go("saves", true); });
      $$("[data-open]", p).forEach((b) => b.addEventListener("click", () => api().open_folder(b.dataset.open)));
      $$("[data-restore]", p).forEach((b) => b.addEventListener("click", async () => {
        if (await confirmBox(`${S.restore}: ${b.dataset.restore}?`)) { toast((await api().restore(b.dataset.restore)).message); go("saves", true); }
      }));
      $$("[data-delete]", p).forEach((b) => b.addEventListener("click", async () => {
        if (await confirmBox(`${S.delete}: ${b.dataset.delete}?`)) { await api().delete_backup(b.dataset.delete); go("saves", true); }
      }));
    },
  };
};

let ACH_FILTER = "all";
PAGES.achievements = async () => {
  const d = await api().achievements();
  const done = d.items.filter((a) => a.unlocked).length, total = d.items.length, pct = Math.round((100 * done) / total);
  const cats = Object.fromEntries(d.categories);
  const shown = d.items.filter((a) => ACH_FILTER === "all" || a.cat === ACH_FILTER || (ACH_FILTER === "locked" && !a.unlocked));
  const fmt = (v) => (Number.isInteger(v) ? v.toLocaleString() : (+v).toFixed(1));
  const card = (a) => {
    const progress = !a.unlocked && a.target > 1 && a.value !== null;
    const state = a.unlocked ? `${S.unlocked_on} ${a.unlocked}` : progress ? `${fmt(a.value)} / ${fmt(a.target)}` : S.locked;
    const bar = progress ? `<div class="mini-progress"><i style="width:${Math.min(100, (100 * a.value) / a.target)}%"></i></div>` : "";
    return `<article class="achievement-card ${a.unlocked ? "" : "locked"}"><div class="achievement-icon"><b>${esc(a.icon)}</b>${a.unlocked ? `<span>${icon("check", 12)}</span>` : ""}</div>
      <div class="achievement-copy"><span>${esc(cats[a.cat])}</span><h3>${esc(a.title)}</h3><p>${esc(a.desc)}</p><div class="achievement-state">${esc(state)}</div>${bar}</div></article>`;
  };
  return {
    html: `${pageHeader(S.achievements, S.ach_sub)}
      <div class="achievement-summary"><div class="progress-ring"><svg viewBox="0 0 44 44"><circle cx="22" cy="22" r="19"/><circle class="ring-value" cx="22" cy="22" r="19" pathLength="100" stroke-dasharray="${pct} 100"/></svg><strong>${pct}%</strong></div>
        <div><span>${esc(S.overall)}</span><h2>${done} <small>/ ${total}</small></h2><div class="wide-progress"><i style="width:${pct}%"></i></div>
          ${d.play_time ? `<div class="played">${esc(S.play_time)}: ${esc(duration(d.play_time))}</div>` : ""}</div>
        ${button(S.check_now, { attrs: 'id="check"' })}</div>
      <div class="filter-bar" id="filter">${[["all", S.all], ...d.categories, ["locked", S.locked]].map(([v, l]) => `<button type="button" data-v="${v}" class="${v === ACH_FILTER ? "active" : ""}">${esc(l)}</button>`).join("")}</div>
      <div class="achievement-grid">${shown.map(card).join("")}</div>
      <p class="credit">${esc(S.ach_credit)}</p>`,
    after(p) {
      $$("#filter button", p).forEach((b) => b.addEventListener("click", () => { ACH_FILTER = b.dataset.v; go("achievements", true); }));
      $("#check", p).addEventListener("click", async () => { await api().check_achievements(); achCount(); go("achievements", true); });
    },
  };
};

let CHEAT_SLOT = null;
PAGES.cheats = async () => {
  const d = await api().cheats(CHEAT_SLOT);
  if (!d.slots.length) return { html: `${pageHeader(S.cheats, S.cheats_sub)}<div class="notice warning"><div><strong>${esc(d.error || S.no_save)}</strong></div></div>` };
  const fmt = (v) => (Number.isInteger(v) ? String(v) : (+v).toFixed(1));
  const editor = (f) => `<div class="value-editor"><div><label>${esc(f.label)}</label><span>${esc(S.now)}: <strong>${fmt(f.value)}</strong>${f.help ? " · " + esc(f.help) : ""}</span></div>
    <div class="value-input"><button type="button" data-step="-1" data-f="${f.key}">${icon("minus", 15)}</button>
      <input type="number" id="c_${f.key}" min="${f.min}" max="${Math.max(f.max, f.value)}" step="${f.step}" value="${fmt(f.value)}">
      <button type="button" data-step="1" data-f="${f.key}">${icon("plus", 15)}</button></div>
    <button type="button" class="max-button" data-max="${f.key}">${esc(S.max)}</button></div>`;
  return {
    html: `${pageHeader(S.cheats, S.cheats_sub)}
      <div class="notice ${d.running ? "warning" : ""}"><div><strong>${esc(d.running ? S.game_running_warn : S.notice_ok)}</strong><span>${esc(d.running ? S.notice_run_sub : S.notice_ok_sub)}</span></div></div>
      ${section(S.save_slot, "", field(S.selected_save, S.slot_hint, select(d.slots.map((s) => [s.id, s.label]), d.slot, 'id="slot"')))}
      ${section(S.values, S.values_sub, `<div class="value-list">${d.fields.map(editor).join("")}</div>`)}
      ${section(S.inventory, S.inventory_sub, `<div class="value-list">${d.pouch_fields.map(editor).join("")}</div>`
        + (d.missing.length ? `<p class="credit">${esc(S.not_owned)} ${esc(d.missing.join(", "))}</p>` : "")
        + field(S.repair, `${S.repair_hint} (${d.worn} ${S.worn_n})`, toggle(false, 'id="repair"')))}
      <p class="credit">${esc(S.cheats_note)}</p>
      <div class="sticky-actions"><span>${esc(d.running ? S.locked_edit : S.safe_edit)}</span><div>
        ${button(S.max_all, { attrs: 'id="maxall"' })}${button(S.apply_changes, { variant: "primary", attrs: 'id="apply"' })}</div></div>`,
    after(p) {
      const all = [...d.fields, ...d.pouch_fields];
      $("#slot", p).addEventListener("change", (e) => { CHEAT_SLOT = e.target.value; go("cheats", true); });
      const max = (key) => { const f = all.find((x) => x.key === key); $(`#c_${key}`, p).value = f.max; };
      $$("[data-max]", p).forEach((b) => b.addEventListener("click", () => max(b.dataset.max)));
      $$("[data-step]", p).forEach((b) => b.addEventListener("click", () => {
        const f = all.find((x) => x.key === b.dataset.f), inp = $(`#c_${f.key}`, p);
        const v = Math.min(Math.max(f.max, f.value), Math.max(f.min, (+inp.value || 0) + f.step * +b.dataset.step));
        inp.value = fmt(Math.round(v * 10) / 10);
      }));
      $("#maxall", p).addEventListener("click", () => all.forEach((f) => max(f.key)));
      $("#apply", p).addEventListener("click", async () => {
        const values = {};
        all.forEach((f) => { values[f.key] = $(`#c_${f.key}`, p).value; });
        values.repair = $("#repair", p).classList.contains("on");
        const r = await api().apply_cheats(d.slot, values);
        toast(r.message);
        if (r.ok) go("cheats", true);
      });
    },
  };
};

// ------------------------------------------------------------------ first setup (game not found)
function renderSetup() {
  document.documentElement.lang = BOOT.lang;
  $("#root").innerHTML = `<div class="setup-screen"><div class="dialog-backdrop"><div class="dialog find-game">
    <img class="find-game-icon" src="img/icon.png" alt=""><span class="eyebrow">${esc(S.first_setup)}</span>
    <h2>${esc(S.find_game)}</h2><p>${esc(S.find_game_text)}</p>
    <label>${esc(S.ui_lang)}</label>${select(BOOT.langs, BOOT.lang, 'id="lang"')}
    <div>${button(S.select_exe, { variant: "primary", attrs: 'id="pick"' })}</div></div></div></div>`;
  $("#pick").addEventListener("click", async () => { const r = await api().choose_game(); if (r.message) toast(r.message); });
  $("#lang").addEventListener("change", async (e) => { BOOT = await api().set_lang(e.target.value); S = BOOT.strings; renderSetup(); });
}

// ------------------------------------------------------------------ start
async function start() {
  BOOT = await api().boot();
  S = BOOT.strings;
  applyTheme();
  if (!BOOT.found) return renderSetup();
  renderShell();
  go(PAGES[location.hash.slice(1)] ? location.hash.slice(1) : BOOT.start_page || "home");
  poll();
}
if (window.pywebview && window.pywebview.api) start(); else window.addEventListener("pywebviewready", start);
