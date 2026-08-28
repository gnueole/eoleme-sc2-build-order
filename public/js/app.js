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

function renderResult(res) {
  lastResult = res;
  markdown = res.markdown;
  $("out").textContent = markdown;
  const m = res.meta || {};
  const chips = [];
  if (m.map) chips.push([t("chip_map"), m.map]);
  if (m.matchup) chips.push([t("chip_matchup"), m.matchup]);
  if (m.duration) chips.push([t("chip_duration"), m.duration]);
  if (m.players) chips.push([t("chip_players"), m.players]);
  chips.push([t("chip_lines"), markdown.split("\n").length]);
  $("meta").innerHTML = chips
    .map((c) => '<span class="chip">' + c[0] + " <b>" + String(c[1]).replace(/</g, "&lt;") + "</b></span>")
    .join("");
  $("timing").textContent = t("read_in", { ms: res.ms });
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

  document.querySelectorAll("[data-theme-choice]").forEach((btn) =>
    btn.addEventListener("click", () => applyTheme(btn.dataset.themeChoice)));
  document.querySelectorAll("[data-locale-choice]").forEach((btn) =>
    btn.addEventListener("click", () => setLanguage(btn.dataset.localeChoice)));
}

applyTheme(storedTheme());
setLanguage(initialLocale());
cleanUrl();
wire();
