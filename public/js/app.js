/* Interface de sc2.eole.me.
   Thème et langue suivent les conventions de trail-mapper : clés localStorage
   `preferred-theme` (light | dark | system, défaut system) et `preferred-locale`.
   Les classes appliquées sont celles de la charte (`theme-light` / `theme-dark`,
   www/DESIGN_SYSTEM.md §4), et la langue accepte aussi `?hl=` comme le blog,
   paramètre qui se nettoie de la barre d'adresse après lecture. */

import { TRANSLATIONS, LOCALES } from "./translations.js";

const $ = (id) => document.getElementById(id);

/* ---------- thème ---------- */

const THEMES = ["light", "dark", "system"];

function resolveTheme(theme) {
  if (theme === "light" || theme === "dark") return theme;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function applyTheme(theme) {
  if (!THEMES.includes(theme)) theme = "system";
  const resolved = resolveTheme(theme);
  for (const node of [document.documentElement, document.body]) {
    node.classList.toggle("theme-light", resolved === "light");
    node.classList.toggle("theme-dark", resolved === "dark");
  }
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", resolved === "dark" ? "#080b11" : "#f8fafc");

  try { localStorage.setItem("preferred-theme", theme); } catch (e) { /* mode privé */ }

  document.querySelectorAll("[data-view-choice]").forEach((btn) =>
    btn.addEventListener("click", () => { view = btn.dataset.viewChoice; applyView(); }));

  document.querySelectorAll("[data-theme-choice]").forEach((btn) => {
    btn.setAttribute("aria-pressed", String(btn.dataset.themeChoice === theme));
  });
}

function storedTheme() {
  try { return localStorage.getItem("preferred-theme") || "system"; } catch (e) { return "system"; }
}

/* Un système qui bascule ne doit déplacer la page que si l'on suit le système. */
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
  if (storedTheme() === "system") applyTheme("system");
});

/* ---------- langue ---------- */

let locale = "fr";

function t(key, fields) {
  let text = (TRANSLATIONS[locale] || TRANSLATIONS.fr)[key] || key;
  if (fields) {
    for (const [k, v] of Object.entries(fields)) text = text.replace("{" + k + "}", v);
  }
  return text;
}

function setLanguage(lang) {
  locale = LOCALES.includes(lang) ? lang : "fr";
  try { localStorage.setItem("preferred-locale", locale); } catch (e) { /* mode privé */ }
  document.documentElement.lang = locale;

  document.querySelectorAll("[data-i18n]").forEach((el) => {
    el.textContent = t(el.dataset.i18n);
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    el.placeholder = t(el.dataset.i18nPlaceholder);
  });
  document.querySelectorAll("[data-i18n-aria]").forEach((el) => {
    el.setAttribute("aria-label", t(el.dataset.i18nAria));
  });
  document.querySelectorAll("[data-i18n-title]").forEach((el) => {
    el.title = t(el.dataset.i18nTitle);
  });

  document.querySelectorAll("[data-locale-choice]").forEach((btn) => {
    btn.setAttribute("aria-pressed", String(btn.dataset.localeChoice === locale));
  });

  if (lastResult) renderResult(lastResult);
}

function initialLocale() {
  /* Priorité : ?hl= (convention du blog) > choix mémorisé > langue du navigateur. */
  try {
    const hl = new URLSearchParams(window.location.search).get("hl");
    if (hl && LOCALES.includes(hl)) return hl;
  } catch (e) { /* URL exotique */ }
  try {
    const saved = localStorage.getItem("preferred-locale");
    if (saved && LOCALES.includes(saved)) return saved;
  } catch (e) { /* mode privé */ }
  return (navigator.language || "fr").toLowerCase().startsWith("en") ? "en" : "fr";
}

function cleanUrl() {
  /* Le paramètre a été lu : on le retire de la barre d'adresse sans recharger. */
  try {
    const url = new URL(window.location.href);
    if (url.searchParams.has("hl")) {
      url.searchParams.delete("hl");
      history.replaceState(null, "", url.pathname + url.search + url.hash);
    }
  } catch (e) { /* history indisponible */ }
}

/* ---------- extraction ---------- */

let picked = null;
let markdown = "";
let basename = "build-order";
let lastResult = null;
let view = "pretty";

function setFile(f) {
  picked = f;
  $("chosen").textContent = f ? f.name + "  (" + Math.round(f.size / 1024) + " Ko)" : "";
  $("go").disabled = !f;
  if (f) basename = f.name.replace(/\.SC2Replay$/i, "") || "build-order";
}

function show(el, on) { el.classList.toggle("hidden", !on); }

function fail(message) {
  show($("result"), false);
  show($("failure"), true);
  $("errmsg").textContent = message;
}

function esc(value) {
  return String(value).replace(/[&<>"']/g, (ch) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
}

/* Le HTML dérive du rapport renvoyé par le serveur, avec les libellés que le
   serveur a lui-même employés pour le Markdown : les deux vues disent donc
   exactement la même chose, dans les mêmes mots. */
function renderReport(report, L) {
  const h = [];

  h.push('<div class="rep-head">');
  h.push("<h3>" + esc(report.map) +
    (report.matchup ? ' <span class="mu">' + esc(report.matchup) + "</span>" : "") + "</h3>");
  const facts = [
    [L.duration, report.duration],
    [L.played, report.played + " UTC"],
    [L.patch, "build " + report.build],
    [L.kind, (report.category + " " + report.game_type).trim()],
  ];
  h.push('<p class="facts">' + facts
    .map((f) => "<span>" + esc(f[0]) + esc(L.colon) + " <b>" + esc(f[1]) + "</b></span>")
    .join("") + "</p>");
  h.push('<ul class="roster">' + report.roster.map((p) =>
    "<li>" + esc(p.name) +
    (p.is_human ? "" : ' <span class="tag">' + esc(L.ai) + "</span>") +
    ' <span class="race">' + esc(p.race) + "</span>" +
    ' <span class="verdict ' + (p.won ? "win" : "loss") + '">' + esc(p.result) + "</span></li>"
  ).join("") + "</ul>");
  if (report.cutoff) {
    h.push('<p class="cut">' +
      esc(L.truncated.replace("{cut}", report.cutoff).replace("{full}", report.duration)) + "</p>");
  }
  h.push("</div>");

  for (const s of report.sections) {
    h.push('<section class="sect">');
    h.push("<h4>" + esc(s.name) + ' <span class="race">' + esc(s.race) + "</span>" +
      ' <span class="verdict ' + (s.won ? "win" : "loss") + '">' + esc(s.result) + "</span></h4>");

    if (!s.build.length) {
      h.push('<p class="muted">' + esc(L.no_build) + "</p></section>");
      continue;
    }

    h.push('<div class="scroll"><table class="bo"><thead><tr><th class="num">' +
      esc(L.col_supply) + '</th><th class="num">' + esc(L.col_time) + "</th><th>" +
      esc(L.col_action) + "</th></tr></thead><tbody>");
    for (const e of s.build) {
      h.push("<tr" + (e.worker ? ' class="wk"' : "") + '><td class="num sup">' + esc(e.supply) +
        '</td><td class="num t">' + esc(e.time) + "</td><td>" + esc(e.action) +
        (e.chrono ? ' <span class="chrono" title="' + esc(L.chrono) + '">⚡</span>' : "") +
        "</td></tr>");
    }
    h.push("</tbody></table></div>");

    if (s.workers_folded) {
      h.push('<p class="muted">' + esc(L.workers_folded.replace("{n}", s.workers_folded)) + "</p>");
    }

    if (s.economy.length) {
      h.push("<h5>" + esc(L.economy) + '</h5><div class="scroll"><table class="eco"><thead><tr>' +
        ["col_time", "col_supply", "col_workers", "col_minerals", "col_gas", "col_income"]
          .map((k) => '<th class="num">' + esc(L[k]) + "</th>").join("") +
        "</tr></thead><tbody>");
      for (const r of s.economy) {
        /* Le ravitaillement qui touche sa capacité est signalé : c'est le moment
           où la production s'arrête, et c'est ce qu'on vient chercher ici. */
        const blocked = r.food_used >= r.food_made && r.food_made < 200;
        h.push('<tr><td class="num t">' + esc(r.at) +
          '</td><td class="num' + (blocked ? " bad" : "") + '">' +
          esc(r.food_used) + "/" + esc(r.food_made) +
          '</td><td class="num">' + esc(r.workers) +
          '</td><td class="num">' + esc(r.minerals) +
          '</td><td class="num">' + esc(r.vespene) +
          '</td><td class="num">' + esc(r.mineral_rate) + "/" + esc(r.vespene_rate) +
          "</td></tr>");
      }
      h.push("</tbody></table></div>");
    }

    if (s.supply_blocks.length) {
      h.push('<p class="line"><span class="lbl">' + esc(L.supply_blocked) + "</span>" +
        s.supply_blocks.map((b) => '<span class="chip warn">' + esc(b) + "</span>").join("") + "</p>");
    }
    if (s.macro.length) {
      h.push('<p class="line"><span class="lbl">' + esc(L.macro) + "</span>" +
        s.macro.map((m) => '<span class="chip">' + esc(m.name) + " <b>×" + esc(m.count) +
          "</b></span>").join("") + "</p>");
    }
    if (s.losses.total) {
      h.push('<p class="line"><span class="lbl">' + esc(L.losses) + " (" + esc(s.losses.total) +
        ")</span>" + s.losses.items.map((i) => '<span class="chip">' + esc(i.name) +
          (i.count > 1 ? " <b>×" + esc(i.count) + "</b>" : "") + "</span>").join("") + "</p>");
    }
    h.push("</section>");
  }

  return h.join("");
}

function applyView() {
  show($("view"), view === "pretty");
  show($("out"), view === "markdown");
  document.querySelectorAll("[data-view-choice]").forEach((btn) => {
    btn.setAttribute("aria-pressed", String(btn.dataset.viewChoice === view));
  });
}

function renderResult(res) {
  lastResult = res;
  markdown = res.markdown;
  $("out").textContent = markdown;
  $("view").innerHTML = renderReport(res.report, res.labels);

  const m = res.meta || {};
  const chips = [];
  if (m.map) chips.push([t("chip_map"), m.map]);
  if (m.matchup) chips.push([t("chip_matchup"), m.matchup]);
  if (m.duration) chips.push([t("chip_duration"), m.duration]);
  if (m.players) chips.push([t("chip_players"), m.players]);
  chips.push([t("chip_lines"), markdown.split("\n").length]);
  $("meta").innerHTML = chips
    .map((c) => '<span class="chip">' + esc(c[0]) + " <b>" + esc(c[1]) + "</b></span>")
    .join("");
  $("timing").textContent = t("read_in", { ms: res.ms });
  applyView();
  show($("result"), true);
}

function extract() {
  if (!picked) return;
  const body = new FormData();
  body.append("replay", picked);
  body.append("cutoff", $("cutoff").value);
  body.append("players", $("players").value);
  body.append("format", $("format").value);
  body.append("workers", $("workers").value);
  body.append("prompt", $("prompt").checked ? "true" : "false");
  body.append("lang", locale);

  $("go").disabled = true;
  $("hint").innerHTML = '<span class="spinner"></span>' + t("reading");
  show($("failure"), false);

  fetch("/api/extract", { method: "POST", body })
    .then((r) => r.json().then((data) => ({ ok: r.ok, status: r.status, data })))
    .then((res) => {
      $("go").disabled = false;
      $("hint").textContent = "";
      if (!res.ok) {
        fail(res.data && res.data.detail ? res.data.detail : t("error_status", { status: res.status }));
        return;
      }
      renderResult(res.data);
      $("result").scrollIntoView({ behavior: "smooth", block: "start" });
    })
    .catch(() => {
      $("go").disabled = false;
      $("hint").textContent = "";
      fail(t("no_response"));
    });
}

/* ---------- câblage ---------- */

function wire() {
  const drop = $("drop");
  const fileInput = $("file");

  drop.addEventListener("click", () => fileInput.click());
  drop.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileInput.click(); }
  });
  fileInput.addEventListener("change", () => setFile(fileInput.files[0] || null));

  ["dragenter", "dragover"].forEach((name) =>
    drop.addEventListener(name, (e) => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach((name) =>
    drop.addEventListener(name, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
  drop.addEventListener("drop", (e) => {
    const f = e.dataTransfer && e.dataTransfer.files[0];
    if (f) setFile(f);
  });

  $("go").addEventListener("click", extract);

  $("copy").addEventListener("click", () => {
    const done = () => {
      $("copied").textContent = t("copied");
      setTimeout(() => { $("copied").textContent = ""; }, 2600);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(markdown).then(done, () => {
        $("copied").textContent = t("copy_blocked");
      });
    } else {
      $("copied").textContent = t("copy_blocked");
    }
  });

  $("download").addEventListener("click", () => {
    const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = basename + ".md";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });

  document.querySelectorAll("[data-view-choice]").forEach((btn) =>
    btn.addEventListener("click", () => { view = btn.dataset.viewChoice; applyView(); }));

  document.querySelectorAll("[data-theme-choice]").forEach((btn) =>
    btn.addEventListener("click", () => applyTheme(btn.dataset.themeChoice)));
  document.querySelectorAll("[data-locale-choice]").forEach((btn) =>
    btn.addEventListener("click", () => setLanguage(btn.dataset.localeChoice)));
}

applyTheme(storedTheme());
setLanguage(initialLocale());
cleanUrl();
wire();
