# Changelog

Every notable change to SC2 Build Order Forge.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
versioning follows [SemVer](https://semver.org/).

## [1.4.0] — 2026-08-28

### Added
- **The game's own unit icons** next to every build-order step. 1,269 icons
  extracted from the installed game's CASC storage, converted from 76px DX10
  `.dds` to 64px WebP — 3.3 MB in total, and a page only fetches the twenty or so
  it needs.
- Race-scoped ability icons are shipped too, which is where the game files the
  Protoss researches: without them Blink and Charge were the only gaps left on a
  real 1v1. Widening further to every extracted icon was measured and reverted —
  940 more files and 2.1 MB for no change in coverage, because the co-op names
  still missing have no button icon in the game at all.
- `sc2bo/icons.py` maps a step name to its icon. Plain normalisation only reaches
  units and buildings, so three rules close the gap on upgrades: the race prefix
  is stripped ("Terran Infantry Weapons Level 1" is filed without it), a trailing
  plural is retried singular ("Combat Shields" is filed as combatshield), and
  "weapons" is retried as "attacks" (Zerg upgrades use the second word). Add-ons
  fall back to the generic tech lab and reactor icons. Measured against production on a real 1v1: 94 steps out of 94 carry an icon.
- Two tests assert that every indexed icon and every alias has a file behind it —
  an index entry with nothing on disk is a broken image on the page.
- Blizzard attribution in the footer, in both languages, as the assets require.

### Notes
- The community pack `MatthewMarinets/ap_sc2_icons` was measured first and turned
  down: built for the Archipelago co-op randomizer, it covers 61 % of the melee
  vocabulary and misses SCV, Drone, Overlord, Pylon, Gateway, Nexus, Supply Depot,
  Barracks and Hatchery — the backbone of every build order.

## [1.3.0] — 2026-08-28

### Added
- **The build order renders as HTML** rather than raw Markdown: real tables,
  supply in colour, a bolt on chrono-boosted production, supply at its cap
  flagged red in the economy table, verdicts and blocks as pills. The **Copy the
  Markdown** button stays, and a *Preview / Markdown* toggle shows what is being
  copied.

### Changed
- The engine now exposes `build_report()`, the intermediate structure both the
  Markdown **and** the HTML derive from. Without it the server would render
  Markdown while the client built its own HTML, and the two would drift on the
  first change. `render_replay()` remains as a shortcut: the Markdown output is
  unchanged, verified by comparing 24 renders (8 replays × 3 option
  combinations) before and after the split — no difference.
- `/api/extract` returns the report **and the labels used**. The page therefore
  renders its HTML in exactly the Markdown's words rather than holding a second
  copy. A test ties the label keys `app.js` reads to the Python dictionary:
  dropping one would break the view silently.

## [1.2.0] — 2026-08-28

### Added
- **Light / dark / system theming**, three states like `trail-mapper`: the
  `preferred-theme` key defaults to `system`, the guidelines' `theme-light` /
  `theme-dark` classes are stamped, and a system change is picked up live. An
  inline script sets the theme *before* first paint; without it a light
  preference flashed dark.
- **Bilingual interface, FR / EN.** The `preferred-locale` key like
  `trail-mapper`, and the blog's `?hl=fr` / `?hl=en` parameter, which is cleaned
  out of the address bar once read. Browser language decides on a first visit.
- The translation covers **the generated Markdown and the server's error
  messages** too: an English interface returning French tables and French errors
  would be a half-translation. `cli.py` gains `--lang`.
- English follows its own typography: `**Map:**` with no space before the colon,
  where French writes `**Carte :**`.

### Changed
- The page script moved into `public/js/`, split into `translations.js` and
  `app.js`, following `trail-mapper`.

## [1.1.0] — 2026-08-28

### Changed
- The interface follows the eole.me brand guidelines (`www/DESIGN_SYSTEM.md`).
  *Business* persona: `#080b11` ground, `#38bdf8` cyan accent, ambient glow.
  Typography **Outfit / Inter / Fira Code**, the three families the guidelines
  name. Both documented themes are supported, where `trail-mapper` ships dark
  only.
- The style moved into `public/css/styles.css`, like `trail-mapper`, reusing the
  guidelines' *token names* rather than isolated values.
- Breakpoints aligned on the `767.98px` / `768px` pair `www/CSS_TOPOLOGY.md`
  requires, and `100dvh` alongside `100vh`.

## [1.0.0] — 2026-08-28

### Added
- Extract a StarCraft II replay's build order as Markdown, ready to paste into
  Claude: a web service on `sc2.eole.me` and a `cli.py` command line, sharing
  the engine in `sc2bo/`.
- Economy figures taken from the game's own `PlayerStatsEvent` samples (supply
  used and cap, active workers, resources, income), which makes supply-block
  detection exact rather than estimated.
- Combat losses separated from drones morphed into buildings.
- A guard on spawningtool's `add_upgrade_event`, its only event handler that
  indexes the player table without checking the key: it takes a 495-replay
  corpus from 483 to 495 read.
