// TotK Launcher page. Talks to launcher.pyw through window.pywebview.api (every call returns a Promise).
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

// ------------------------------------------------------------------ art
const EMBLEM = `<svg viewBox="0 0 64 64" aria-hidden="true">
  <defs><linearGradient id="eg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fbe9b4"/><stop offset="1" stop-color="#b48a41"/></linearGradient></defs>
  <circle cx="32" cy="32" r="29" fill="none" stroke="url(#eg)" stroke-width="1.6"/>
  <circle cx="32" cy="32" r="21" fill="none" stroke="url(#eg)" stroke-width="1" opacity=".7"/>
  ${[0, 45, 90, 135, 180, 225, 270, 315].map((a) => `<line x1="32" y1="5" x2="32" y2="${a % 90 ? 10 : 13}" stroke="url(#eg)" stroke-width="1.6" transform="rotate(${a} 32 32)"/>`).join("")}
  <path d="M32 15 L40 32 L32 49 L24 32 Z" fill="url(#eg)"/>
  <path d="M32 21 L36 32 L32 43 L28 32 Z" fill="#0a161b"/>
  <circle cx="32" cy="32" r="2.4" fill="url(#eg)"/>
</svg>`;

function rnd(seed) { let s = seed; return () => (s = (s * 16807) % 2147483647) / 2147483647; }

function heroArt() {
  const r = rnd(7);
  let stars = "";
  for (let i = 0; i < 70; i++) {
    const x = r() * 1000, y = r() * 130, s = r() * 1.3 + 0.3;
    stars += `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${s.toFixed(2)}" fill="#fff" opacity="${(0.35 + r() * 0.6).toFixed(2)}" ${i % 4 === 0 ? `class="twinkle" style="animation-delay:${(r() * 3).toFixed(1)}s"` : ""}/>`;
  }
  const island = (x, y, w, cls) => `<g transform="translate(${x} ${y}) scale(${w})"><g class="${cls}">
      <path d="M-60 0 Q-40 -10 0 -9 Q40 -10 62 0 L48 10 L36 26 L22 20 L10 44 L-4 28 L-18 36 L-30 18 L-44 16 Z" fill="#0b2328"/>
      <path d="M-60 0 Q-40 -10 0 -9 Q40 -10 62 0 Q40 -4 0 -3 Q-40 -4 -60 0 Z" fill="#2f6b5c"/>
      <rect x="20" y="4" width="3" height="70" fill="url(#fall)" opacity=".7"/>
      <path d="M-28 -9 L-24 -26 L-20 -9 Z M-14 -9 L-9 -32 L-4 -9 Z" fill="#163a35"/>
    </g></g>`;
  return `<svg viewBox="0 0 1000 230" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
    <defs>
      <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="#081427"/><stop offset=".55" stop-color="#14394a"/><stop offset="1" stop-color="#2d6662"/>
      </linearGradient>
      <radialGradient id="moon" cx="0.82" cy="0.22" r="0.35"><stop offset="0" stop-color="#f3e2a8" stop-opacity=".55"/><stop offset="1" stop-color="#f3e2a8" stop-opacity="0"/></radialGradient>
      <linearGradient id="fall" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#bfe9e2"/><stop offset="1" stop-color="#bfe9e2" stop-opacity="0"/></linearGradient>
      <filter id="blur"><feGaussianBlur stdDeviation="8"/></filter>
    </defs>
    <rect width="1000" height="230" fill="url(#sky)"/>
    <rect width="1000" height="230" fill="url(#moon)"/>
    <circle cx="820" cy="52" r="16" fill="#f7ecc8" opacity=".9"/>
    ${stars}
    <ellipse cx="300" cy="120" rx="180" ry="14" fill="#fff" opacity=".06" filter="url(#blur)"/>
    <ellipse cx="760" cy="150" rx="220" ry="16" fill="#fff" opacity=".05" filter="url(#blur)"/>
    ${island(640, 92, 1.15, "drift")}
    ${island(880, 128, 0.7, "drift2")}
    ${island(470, 70, 0.55, "drift2")}
    <path d="M0 190 L80 150 L150 172 L240 128 L330 168 L420 140 L520 176 L610 146 L700 178 L800 150 L900 182 L1000 160 L1000 230 L0 230 Z" fill="#123139" opacity=".95"/>
    <path d="M0 210 L110 182 L210 202 L320 176 L430 206 L560 184 L690 208 L820 186 L930 206 L1000 196 L1000 230 L0 230 Z" fill="#0a1f25"/>
    <rect y="170" width="1000" height="60" fill="url(#sky)" opacity=".15"/>
  </svg>`;
}

const ICONS = {
  home: '<path d="M3 11 12 4l9 7v9H5v-9"/><path d="M10 20v-6h4v6"/>',
  settings: '<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0"/><circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/>',
  controls: '<rect x="2.5" y="7" width="19" height="11" rx="5"/><path d="M7 10.5v4M5 12.5h4"/><circle cx="16" cy="11.5" r="1"/><circle cx="18" cy="14" r="1"/>',
  saves: '<path d="M5 3h11l3 3v15H5z"/><path d="M8 3v6h8V3M8 21v-7h8v7"/>',
  achievements: '<path d="M8 4h8v5a4 4 0 0 1-8 0z"/><path d="M8 6H5a3 3 0 0 0 3 4M16 6h3a3 3 0 0 1-3 4M12 13v4M8 21h8M9 17h6"/>',
  cheats: '<path d="M4 20 15 9M14 4l1.5 3 3 1.5-3 1.5L14 13l-1.5-3-3-1.5 3-1.5z"/><path d="M19 14v4M17 16h4"/>',
};

// ------------------------------------------------------------------ helpers
function toast(msg) {
  if (!msg) return;
  const t = el(`<div class="toast">${esc(msg)}</div>`);
  $("#toasts").append(t);
  setTimeout(() => { t.classList.add("out"); setTimeout(() => t.remove(), 300); }, 4200);
}

function unlockPopup(ev) {
  const t = el(`<div class="toast unlock"><div class="medal">${esc(ev.icon)}</div>
    <div><div class="k">${esc(S.ach_unlocked)}</div><div class="t">${esc(ev.title)}</div><div class="d">${esc(ev.desc)}</div></div></div>`);
  $("#toasts").append(t);
  setTimeout(() => { t.classList.add("out"); setTimeout(() => t.remove(), 300); }, 5200);
}

function confirmBox(text, okLabel, danger = false) {
  return new Promise((resolve) => {
    const m = $("#modal");
    m.innerHTML = `<div class="card"><h3>${esc(S.confirm)}</h3><p>${esc(text)}</p>
      <div class="actions"><span class="spacer"></span><button class="btn" data-v="0">${esc(S.cancel)}</button>
      <button class="btn ${danger ? "danger" : "gold"}" data-v="1">${esc(okLabel || S.yes)}</button></div></div>`;
    m.classList.remove("hidden");
    const done = (v) => { m.classList.add("hidden"); m.innerHTML = ""; resolve(v); };
    $$("button", m).forEach((b) => b.addEventListener("click", () => done(b.dataset.v === "1")));
    m.addEventListener("click", (e) => { if (e.target === m) done(false); }, { once: true });
  });
}

const seg = (options, current, attr) =>
  `<div class="seg" ${attr}>${options.map(([v, label]) => `<button data-v="${esc(v)}" class="${v === current ? "on" : ""}">${esc(label)}</button>`).join("")}</div>`;

function bindSeg(root, onPick) {
  $$("button", root).forEach((b) => b.addEventListener("click", () => {
    $$("button", root).forEach((x) => x.classList.toggle("on", x === b));
    onPick(b.dataset.v);
  }));
}

const divider = (label) => `<div class="divider"><span>${esc(label)}</span></div>`;
const header = (title, sub) => `<h1 class="page-title">${esc(title)}</h1>${sub ? `<p class="page-sub">${esc(sub)}</p>` : ""}`;

// ------------------------------------------------------------------ shell
function renderShell() {
  document.documentElement.lang = BOOT.lang;
  $("#root").innerHTML = `<div class="app">
    <aside class="side">
      <div class="brand">${EMBLEM}<div><div class="name">TOTK</div><div class="tag">${esc(S.subtitle)}</div></div></div>
      <nav class="nav">${["home", "settings", "controls", "saves", "achievements", "cheats"].map((p) =>
        `<button data-page="${p}"><svg viewBox="0 0 24 24">${ICONS[p]}</svg>${esc(S[p])}</button>`).join("")}</nav>
      <div class="side-bottom">
        <div class="state" id="state"><i></i><span></span></div>
        <button class="play" id="play"></button>
        <label class="check small dim"><span class="switch"><input type="checkbox" id="mods" ${BOOT.cfg.mods ? "checked" : ""}><span></span></span>${esc(S.load_mods)}</label>
      </div>
    </aside>
    <main class="main" id="main"></main>
  </div>`;
  $$(".nav button").forEach((b) => b.addEventListener("click", () => go(b.dataset.page)));
  $("#play").addEventListener("click", play);
  $("#mods").addEventListener("change", async (e) => {
    BOOT.cfg.mods = e.target.checked;
    await api().set_option("mods", e.target.checked);
    if (PAGE === "home" || PAGE === "controls") go(PAGE);
  });
  showState(STATE);
}

function showState(state) {
  STATE = state;
  const st = $("#state"), btn = $("#play");
  if (!st) return;
  st.className = "state " + state;
  $("span", st).textContent = { ready: S.st_ready, running: S.st_running, closed: S.st_closed, preparing: S.st_preparing }[state];
  const busy = state === "running" || state === "preparing";
  btn.classList.toggle("busy", busy);
  btn.textContent = state === "preparing" ? S.preparing : state === "running" ? S.running : S.play;
}

async function play() {
  if (STATE === "running" || STATE === "preparing") return;
  const res = await api().play();
  if (!res.ok) toast(res.message); else showState("preparing");
}

async function poll() {
  try {
    const st = await api().status();
    showState(st.state);
    for (const ev of st.events) {
      if (ev.type === "toast") toast(ev.message);
      else if (ev.type === "achievement") unlockPopup(ev);
      else if (ev.type === "achievements_changed" && PAGE === "achievements" && !CAPTURE) go("achievements", true);
    }
  } catch (e) { /* the window is closing */ }
  setTimeout(poll, 1200);
}

async function go(page, keepScroll = false) {
  PAGE = page;
  CAPTURE = null;
  $$(".nav button").forEach((b) => b.classList.toggle("active", b.dataset.page === page));
  const main = $("#main");
  const y = main.scrollTop;
  const html = await PAGES[page]();
  if (PAGE !== page) return;           // another page was chosen meanwhile
  main.innerHTML = `<div class="page">${html.html}</div>`;
  if (keepScroll) main.scrollTop = y; else main.scrollTop = 0;
  html.after && html.after($(".page", main));
}

// ------------------------------------------------------------------ pages
const PAGES = {};

let LOG_OPEN = false;   // the recent log is folded away until asked for
PAGES.home = async () => {
  const d = await api().home();
  const stat = (k, v, cls = "") => `<div class="stat"><div class="k">${esc(k)}</div><div class="v ${cls}" title="${esc(v)}">${esc(v)}</div></div>`;
  const fps = [["30", "30"], ["60", "60"], ["120", "120"], ["144", "144"], ["display", S.monitor]];
  return {
    html: `<div class="hero">${heroArt()}<div class="title"><h1>Tears of the Kingdom</h1><p>${esc(S.subtitle)}</p></div></div>
      <div class="stats">
        ${stat(S.game, "totk.exe " + (d.exe ? S.found : S.not_found), d.exe ? "ok" : "bad")}
        ${stat(S.version, d.version)}
        ${stat(S.gpu, d.gpu || S.unknown)}
        ${stat(S.mods, d.mods ? `${d.mods} ${S.files} · ${d.mods_on ? S.on : S.off}` : "—", d.mods && d.mods_on ? "ok" : "warn")}
      </div>
      ${divider(S.quick_fps)}
      <div class="card"><div class="actions">${seg(fps, d.fps, 'id="fps"')}<span class="spacer"></span>
        <span class="dim small">${esc(S.last_start)}: ${esc(d.last || "—")}</span></div></div>
      <div class="card" style="margin-top:16px">
        <div class="actions">
          <button class="btn logtoggle ${LOG_OPEN ? "open" : ""}" id="logtoggle"><span class="chev">›</span>${esc(S.recent_log)}</button>
          <button class="btn" data-open="logs">${esc(S.log_folder)}</button>
          <button class="btn" data-open="game">${esc(S.game_folder_btn)}</button>
          <span class="spacer"></span><button class="btn" id="shortcut">${esc(S.shortcut)}</button>
        </div>
        <div class="logwrap ${LOG_OPEN ? "open" : ""}" id="logwrap"><div>
          <pre class="log" id="log">${esc(d.log || S.no_log)}</pre>
          <div class="actions" style="margin-top:10px"><span class="spacer"></span><button class="btn small" id="refresh">${esc(S.refresh)}</button></div>
        </div></div>
      </div>`,
    after(p) {
      const log = $("#log", p); log.scrollTop = log.scrollHeight;
      $("#logtoggle", p).addEventListener("click", (e) => {
        LOG_OPEN = !LOG_OPEN;
        e.currentTarget.classList.toggle("open", LOG_OPEN);
        $("#logwrap", p).classList.toggle("open", LOG_OPEN);
        if (LOG_OPEN) log.scrollTop = log.scrollHeight;
      });
      bindSeg($("#fps", p), async (v) => { await api().quick_fps(v); toast(`${S.quick_fps}: ${v === "display" ? S.monitor : v}`); });
      $("#refresh", p).addEventListener("click", () => go("home", true));
      $$("[data-open]", p).forEach((b) => b.addEventListener("click", () => api().open_folder(b.dataset.open)));
      $("#shortcut", p).addEventListener("click", async () => toast((await api().shortcut()).message));
    },
  };
};

PAGES.settings = async () => {
  const d = await api().settings();
  const input = (it) => {
    const id = `s_${it.key}`;
    if (it.kind === "bool") {
      const on = !["", "0", "false", "off"].includes(String(it.value));
      return `<label class="switch"><input type="checkbox" id="${id}" ${on ? "checked" : ""}><span></span></label>`;
    }
    if (it.kind === "scale") {
      const [lo, hi] = it.choices;
      return `<div class="range"><input type="range" id="${id}" min="${lo}" max="${hi}" value="${esc(it.value)}"><output>${esc(it.value)}</output></div>`;
    }
    if (it.kind === "gpu") {
      return `<select id="${id}"><option value="">${esc(S.automatic)}</option>${d.gpus.map(([i, n]) =>
        `<option value="${esc(i)}" ${String(i) === String(it.value) ? "selected" : ""}>${esc(i)}: ${esc(n)}</option>`).join("")}</select>`;
    }
    if (it.kind === "combo") {
      return `<input type="text" id="${id}" list="${id}_l" value="${esc(it.value)}"><datalist id="${id}_l">${it.choices.map((c) => `<option value="${esc(c)}">`).join("")}</datalist>`;
    }
    const choices = it.choices.includes(it.value) ? it.choices : [it.value, ...it.choices];
    return `<select id="${id}">${choices.map((c) => `<option ${c === it.value ? "selected" : ""}>${esc(c)}</option>`).join("")}</select>`;
  };
  return {
    html: `${header(S.settings, S.settings_sub)}
      <div class="card"><h3>${esc(S.launcher)}</h3>
        <div class="row"><div><div class="label">${esc(S.ui_lang)}</div></div>${seg(BOOT.langs, BOOT.lang, 'id="lang"')}</div>
        <div class="row"><div><div class="label">${esc(S.game_folder)}</div><div class="help">${esc(BOOT.root)}</div></div>
          <button class="btn" id="chgame">${esc(S.change)}</button></div>
      </div>
      ${d.groups.map((g) => `<div class="card"><h3>${esc(g.title)}</h3>${g.items.map((it) =>
        `<div class="row"><div><div class="label">${esc(it.label)}</div>${it.help ? `<div class="help">${esc(it.help)}</div>` : ""}</div>${input(it)}</div>`).join("")}</div>`).join("")}
      <div class="actions" style="margin-top:20px"><button class="btn" id="openini">${esc(S.open_ini)}</button><span class="spacer"></span>
        <button class="btn" id="reset">${esc(S.reset_defaults)}</button><button class="btn gold" id="save">${esc(S.save)}</button></div>`,
    after(p) {
      bindSeg($("#lang", p), async (code) => { BOOT = await api().set_lang(code); S = BOOT.strings; renderShell(); go("settings"); });
      $("#chgame", p).addEventListener("click", async () => { const r = await api().choose_game(); if (r.message) toast(r.message); });
      $$("input[type=range]", p).forEach((r) => r.addEventListener("input", () => { r.nextElementSibling.textContent = r.value; }));
      $("#openini", p).addEventListener("click", () => api().open_ini());
      $("#save", p).addEventListener("click", async () => {
        const values = {};
        d.groups.forEach((g) => g.items.forEach((it) => {
          const x = $(`#s_${it.key}`, p);
          values[it.key] = it.kind === "bool" ? x.checked : x.value;
        }));
        toast((await api().save_settings(values)).message);
      });
      $("#reset", p).addEventListener("click", async () => {
        if (await confirmBox(S.reset_defaults + "?", S.reset_defaults, true)) { toast((await api().reset_settings()).message); go("settings"); }
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
  const groups = [];
  d.buttons.forEach((b) => { if (!groups.length || groups[groups.length - 1].name !== b.group) groups.push({ name: b.group, items: [] }); groups[groups.length - 1].items.push(b); });
  const padOpts = (cur) => [["default", S.default], ["none", S.none], ...d.pads].map(([v, l]) => `<option value="${esc(v)}" ${v === cur ? "selected" : ""}>${esc(l)}</option>`).join("");
  let prompt = d.prompts;
  let previewTimer = null;

  CTRL = {
    isStick: (b) => d.buttons.find((x) => x.id === b).stick,
    draw() {
      $$(".key").forEach((c) => {
        const keys = binds[c.dataset.b].keys, i = +c.dataset.i;
        const cap = CAPTURE && CAPTURE.b === c.dataset.b && CAPTURE.i === i;
        c.classList.toggle("capture", !!cap);
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
    box.innerHTML = r.ok ? `<img src="${r.src}" alt="">` : `<span class="dim small">${esc(r.message)}</span>`;
  }

  return {
    html: `${header(S.controls, S.controls_sub)}
      <div class="card"><h3>${esc(S.prompts_devices)}</h3>
        <div class="row wide"><div class="label">${esc(S.button_prompts)}</div><div>${seg(sets, prompt, 'id="pset"')}
          ${d.available ? "" : `<div class="help" style="color:var(--warn)">${esc(S.no_romfs)}</div>`}
          <div class="help">${esc(S.prompts_help)}</div><div class="preview" id="preview"></div></div></div>
        <div class="row wide"><div class="label">${esc(S.controller_layout)}</div><div>
          ${seg([["auto", S.layout_auto], ["nintendo", S.layout_nintendo], ["xbox", S.layout_xbox]], d.pad_layout, 'id="layout"')}
          <div class="help">${esc(S.layout_help)}</div></div></div>
        <div class="row wide"><div class="label">${esc(S.mouse_camera)}</div><div>
          <div class="range"><input type="range" id="sens" min="0" max="10" value="${d.mouse_sens}"><output>${d.mouse_sens}</output></div>
          <div class="help">${esc(S.mouse_help)}</div></div></div>
      </div>
      <p class="page-sub" style="margin-top:22px">${esc(S.bind_help)}</p>
      ${groups.map((g) => `${divider(g.name)}<div class="card"><div class="binds">
        <div></div><div class="head">${esc(S.key1)}</div><div class="head">${esc(S.key2)}</div><div class="head">${esc(S.controller)}</div>
        ${g.items.map((b) => `<div class="desc">${esc(b.label)}</div>
          <div class="key" data-b="${b.id}" data-i="0"></div><div class="key" data-b="${b.id}" data-i="1"></div>
          ${b.stick ? `<div class="stick">${esc(b.id.startsWith("L") ? S.left_stick : S.right_stick)}</div>`
            : `<select data-pad="${b.id}">${padOpts(binds[b.id].pad)}</select>`}`).join("")}
      </div></div>`).join("")}
      <div class="actions" style="margin-top:20px"><button class="btn" id="undo">${esc(S.undo)}</button><span class="spacer"></span>
        <button class="btn" id="reset">${esc(S.reset_bindings)}</button><button class="btn gold" id="save">${esc(S.save)}</button></div>`,
    after(p) {
      CTRL.draw(); loadPreview();
      let layout = d.pad_layout;
      bindSeg($("#pset", p), async (v) => { prompt = v; await api().set_option("prompts", v); BOOT.cfg.prompts = v; loadPreview(); });
      bindSeg($("#layout", p), (v) => { layout = v; });
      const sens = $("#sens", p);
      sens.addEventListener("input", () => { sens.nextElementSibling.textContent = sens.value; });
      $$(".key", p).forEach((c) => {
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
        toast((await api().save_controls(binds, pads, layout, +sens.value)).message);
        go("controls", true);
      });
      $("#undo", p).addEventListener("click", () => go("controls", true));
      $("#reset", p).addEventListener("click", async () => {
        if (await confirmBox(S.reset_bindings + "?", S.reset_bindings, true)) { toast((await api().reset_controls()).message); go("controls", true); }
      });
    },
  };
};

PAGES.saves = async () => {
  const d = await api().saves();
  const c = BOOT.cfg;
  return {
    html: `${header(S.saves, S.saves_sub)}
      <div class="card"><h3>${esc(S.auto_backup)}</h3>
        <div class="row"><div class="label">${esc(S.backup_on_play)}</div><label class="switch"><input type="checkbox" id="bop" ${c.backup_before_play ? "checked" : ""}><span></span></label></div>
        <div class="row"><div class="label">${esc(S.keep)}</div><input type="number" id="keep" min="1" max="100" value="${c.backup_keep}"></div>
        <div class="row"><div class="label">${esc(S.close_on_play)}</div><label class="switch"><input type="checkbox" id="cop" ${c.close_on_play ? "checked" : ""}><span></span></label></div>
      </div>
      <div class="actions" style="margin:18px 0"><button class="btn gold" id="now">${esc(S.backup_now)}</button>
        <button class="btn" data-open="saves">${esc(S.save_folder)}</button><button class="btn" data-open="backups">${esc(S.backup_folder)}</button></div>
      <div class="card list"><h3>${esc(S.backups)}</h3>
        ${d.backups.length ? d.backups.map((b) => `<div class="item"><div class="name">${esc(b.name)}</div><div class="meta">${b.size} MiB</div>
          <button class="btn small" data-restore="${esc(b.name)}">${esc(S.restore)}</button>
          <button class="btn small danger" data-delete="${esc(b.name)}">${esc(S.delete)}</button></div>`).join("")
          : `<div class="dim">${esc(S.no_backups)}</div>`}
      </div>`,
    after(p) {
      const opt = (id, key, read) => $(id, p).addEventListener("change", (e) => { BOOT.cfg[key] = read(e.target); api().set_option(key, BOOT.cfg[key]); });
      opt("#bop", "backup_before_play", (x) => x.checked);
      opt("#cop", "close_on_play", (x) => x.checked);
      opt("#keep", "backup_keep", (x) => Math.max(1, Math.min(100, +x.value || 10)));
      $("#now", p).addEventListener("click", async () => { toast((await api().backup_now()).message); go("saves", true); });
      $$("[data-open]", p).forEach((b) => b.addEventListener("click", () => api().open_folder(b.dataset.open)));
      $$("[data-restore]", p).forEach((b) => b.addEventListener("click", async () => {
        if (await confirmBox(`${S.restore}: ${b.dataset.restore}?`, S.restore)) { toast((await api().restore(b.dataset.restore)).message); go("saves", true); }
      }));
      $$("[data-delete]", p).forEach((b) => b.addEventListener("click", async () => {
        if (await confirmBox(`${S.delete}: ${b.dataset.delete}?`, S.delete, true)) { await api().delete_backup(b.dataset.delete); go("saves", true); }
      }));
    },
  };
};

let ACH_FILTER = "all";
PAGES.achievements = async () => {
  const d = await api().achievements();
  const done = d.items.filter((a) => a.unlocked).length, total = d.items.length, pct = Math.round((100 * done) / total);
  const shown = d.items.filter((a) => ACH_FILTER === "all" || a.cat === ACH_FILTER || (ACH_FILTER === "locked" && !a.unlocked));
  const fmt = (v) => (Number.isInteger(v) ? v.toLocaleString() : (+v).toFixed(1));
  return {
    html: `${header(S.achievements, S.ach_sub)}
      <div class="card"><div class="ach-top"><div class="ach-count">${done} / ${total}</div>
        <div class="bar"><i style="width:${pct}%"></i></div><div class="ach-pct">${pct}%</div>
        <button class="btn" id="check">${esc(S.check_now)}</button></div></div>
      <div style="margin-top:18px">${seg([["all", S.all], ...d.categories, ["locked", S.locked]], ACH_FILTER, 'id="filter"')}</div>
      <div class="achs">${shown.map((a) => `<div class="ach ${a.unlocked ? "done" : ""}"><div class="medal">${esc(a.icon)}</div><div style="flex:1;min-width:0">
        <div class="t">${esc(a.title)}</div><div class="d">${esc(a.desc)}</div>
        ${a.unlocked ? `<div class="when">${esc(S.unlocked_on)} · ${esc(a.unlocked)}</div>`
          : a.target > 1 && a.value !== null ? `<div class="p"><div class="bar"><i style="width:${(100 * a.value) / a.target}%"></i></div>${fmt(a.value)} / ${fmt(a.target)}</div>` : ""}
      </div></div>`).join("")}</div>
      <p class="dim small" style="margin-top:22px">${esc(S.ach_credit)}</p>`,
    after(p) {
      bindSeg($("#filter", p), (v) => { ACH_FILTER = v; go("achievements", true); });
      $("#check", p).addEventListener("click", async () => { await api().check_achievements(); go("achievements", true); });
    },
  };
};

let CHEAT_SLOT = null;
PAGES.cheats = async () => {
  const d = await api().cheats(CHEAT_SLOT);
  if (!d.slots.length) return { html: `${header(S.cheats, S.cheats_sub)}<div class="card"><span style="color:var(--warn)">${esc(d.error || S.no_save)}</span></div>` };
  const fmt = (v) => (Number.isInteger(v) ? String(v) : (+v).toFixed(1));
  return {
    html: `${header(S.cheats, S.cheats_sub)}
      ${d.running ? `<div class="card" style="border-color:var(--warn)"><span style="color:var(--warn)">${esc(S.game_running_warn)}</span></div>` : ""}
      <div class="card"><h3>${esc(S.save_slot)}</h3><select id="slot" style="min-width:320px">${d.slots.map((s) =>
        `<option value="${esc(s.id)}" ${s.id === d.slot ? "selected" : ""}>${esc(s.label)}</option>`).join("")}</select></div>
      <div class="card"><h3>${esc(S.values)}</h3>${d.fields.map((f) => `<div class="row"><div><div class="label">${esc(f.label)}</div>
        <div class="help">${esc(S.now)}: ${fmt(f.value)}${f.help ? " · " + esc(f.help) : ""}</div></div>
        <div class="actions"><button class="btn small" data-max="${f.key}">${esc(S.max)}</button>
        <input type="number" id="c_${f.key}" min="${f.min}" max="${Math.max(f.max, f.value)}" step="${f.step}" value="${fmt(f.value)}"></div></div>`).join("")}</div>
      <div class="actions" style="margin-top:20px"><span class="dim small" style="flex:1">${esc(S.cheats_note)}</span>
        <button class="btn" id="maxall">${esc(S.max_all)}</button><button class="btn gold" id="apply">${esc(S.apply)}</button></div>`,
    after(p) {
      $("#slot", p).addEventListener("change", (e) => { CHEAT_SLOT = e.target.value; go("cheats", true); });
      const max = (key) => { const f = d.fields.find((x) => x.key === key); $(`#c_${key}`, p).value = f.max; };
      $$("[data-max]", p).forEach((b) => b.addEventListener("click", () => max(b.dataset.max)));
      $("#maxall", p).addEventListener("click", () => d.fields.forEach((f) => max(f.key)));
      $("#apply", p).addEventListener("click", async () => {
        const values = {};
        d.fields.forEach((f) => { values[f.key] = $(`#c_${f.key}`, p).value; });
        const r = await api().apply_cheats(d.slot, values);
        toast(r.message);
        if (r.ok) go("cheats", true);
      });
    },
  };
};

// ------------------------------------------------------------------ setup (game not found)
function renderSetup() {
  document.documentElement.lang = BOOT.lang;
  $("#root").innerHTML = `<div class="setup"><div class="card">${EMBLEM}
    <h1>${esc(S.find_game)}</h1><p>${esc(S.find_game_text)}</p>
    <div class="actions" style="justify-content:center"><button class="btn gold" id="pick" style="height:46px;padding:0 28px;font-size:15px">${esc(S.select_exe)}</button></div>
    <div style="margin-top:22px">${seg(BOOT.langs, BOOT.lang, 'id="lang"')}</div></div></div>`;
  $("#pick").addEventListener("click", async () => { const r = await api().choose_game(); if (r.message) toast(r.message); });
  bindSeg($("#lang"), async (code) => { BOOT = await api().set_lang(code); S = BOOT.strings; renderSetup(); });
}

// ------------------------------------------------------------------ start
async function start() {
  BOOT = await api().boot();
  S = BOOT.strings;
  if (!BOOT.found) return renderSetup();
  renderShell();
  go(BOOT.start_page || "home");
  poll();
}
if (window.pywebview && window.pywebview.api) start(); else window.addEventListener("pywebviewready", start);
