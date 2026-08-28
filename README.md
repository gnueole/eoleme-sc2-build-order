# ⚔️ SC2 Build Order Forge

Drop a StarCraft II replay, get its build order as Markdown, ready to paste into
Claude for a coaching pass.

Live at **[sc2.eole.me](https://sc2.eole.me)**. The same engine runs from the
command line, without going through the site.

---

## What it pulls out

Beyond the supply / time / action sequence, three sections the replay lets us
compute rather than guess:

| Section | Where the numbers come from |
|---|---|
| **Economy** | The samples the game writes itself every ~160 frames: supply used *and* cap, active workers, banked resources, income. |
| **Supply blocked** | The stretches where used meets cap — production has stalled. The 200 cap is ignored: that is not a player mistake. |
| **Combat losses** | Units that died with an identified killer. Drones morphed into buildings are excluded: on one test game, 67 drone "losses" broke down into 36 real deaths and 31 morphs. |

The ⚡ symbol marks production sped up with Chrono Boost.

---

## From the command line

`cli.py` declares its dependencies in its own header: `uv` installs them on
first run, there is nothing to set up.

```bash
uv run cli.py --last                       # the most recent game
uv run cli.py --last 3 --cutoff 8:00 --clip
uv run cli.py --list 20                    # list recent replays
uv run cli.py "game.SC2Replay" --player Éole --format raw --output bo.md
```

The replay folder is found on its own, including through the OneDrive
redirection under WSL. `SC2_REPLAY_DIR` or `--replay-dir` override it.

| Option | Effect |
|---|---|
| `--cutoff MM:SS` | Keep only the opening — often the only part that matters. |
| `--player NAME` | A single side. Repeatable. Takes a partial name or a number. |
| `--all-players` | Include the AI and neutral forces (co-op). |
| `--workers` | `summary` (default), `all` to list every worker, `none`. |
| `--format` | `table` (default), `list`, or `raw` aligned in columns. |
| `--lang` | `fr` (default) or `en` — language of the generated Markdown. |
| `--no-prompt` | Without the coaching prompt on top. |

---

## Development

```bash
make venv     # Python environment
make test     # 58 tests
make up       # container on http://localhost:3050
make logs
make down
```

## Deployment

```bash
make deploy   # ghcr.io image + Doppler secrets + restart on the VPS
make checklogs
```

The image is built and pushed to `ghcr.io` by GitHub Actions on every push to
`main`, after the tests pass. `make deploy` only pulls the image and restarts
the container.

> [!IMPORTANT]
> `sc2.eole.me` needs an **A** record pointing at the VPS *before* the first
> deployment. Traefik gets its certificate through an HTTP challenge: with no
> DNS resolution, Let's Encrypt fails and the service stays unreachable over
> HTTPS. There is no wildcard on `eole.me`; every subdomain has its own record.

---

## Architecture

```text
sc2bo/extract.py      Engine: read the replay, compute, render
cli.py                Command line (standalone uv script)
server.py             FastAPI service
public/index.html     Web interface, no build step, no JS dependency
public/css/styles.css eole.me brand guidelines
public/js/            translations.js (FR/EN) and app.js (theme, language, upload)
docker/               Dockerfile plus local and production compose
```

The command line and the site share the very same engine: a fix in `sc2bo/`
serves both.

### One report, two renderings

`build_report()` returns the intermediate structure both the Markdown and the
HTML derive from. Without it the server would render Markdown while the page
built its own HTML, and the two would drift on the first change. The response
also carries the labels the server used, so the page renders in exactly the
Markdown's words rather than holding a second copy.

### The service contract

| Route | Role |
|---|---|
| `POST /api/extract` | Multipart: `replay`, plus `cutoff`, `players`, `format`, `workers`, `prompt`, `lang`. Returns `{markdown, report, labels, meta, ms}`. |
| `GET /api/health` | Status, version, size cap, usage for the day. |
| `GET /` | The interface. |

The replay is written to a temporary file for the duration of the parse then
removed in a `finally`: **nothing is kept**. Telemetry carries neither player
names nor replay content — map, matchup, durations and sizes are enough.

### Settings

| Variable | Default | Role |
|---|---|---|
| `SC2BO_MAX_UPLOAD_BYTES` | 12 MB | Size cap. A replay rarely goes past 3 MB. Traefik cuts at the same threshold already. |
| `SC2BO_PARSE_TIMEOUT_S` | 45 | Past this the request gives up rather than holding the server. |
| `SC2BO_FEEDBACK_THRESHOLD` | 50 | Extractions per day past which a `usage_threshold_crossed` event is emitted. The site is not throttled: the threshold exists to decide whether it should be. |
| `TELEMETRY_WEBHOOK_URL` | `http://vector:8080` | Vector, which relays to Axiom. Empty means events stay on stdout. |

The usage counter lives in memory: a restart resets it. That is deliberate — we
want an order of magnitude, not accounting.

---

## Brand guidelines

The interface follows the guidelines documented in `www/DESIGN_SYSTEM.md` of the
`eoleme-www` repository: *business* persona, `#080b11` ground, `#38bdf8` cyan
accent, Outfit / Inter / Fira Code typography. Like `trail-mapper`, this is a
local stylesheet reusing the guidelines' **token names** rather than a remote
import — standalone sub-pages do not share the main site's generated bundle. The
traps in `www/CSS_TOPOLOGY.md` are respected: no `100vw`, `100dvh` alongside
`100vh`, `767.98px` / `768px` breakpoints.

---

## A spawningtool quirk worth knowing

`spawningtool` loses **12 replays out of 495** on this corpus, all to the same
`KeyError`. In co-op and on maps with neutral camps, a replay carries upgrades
belonging to players absent from its table (Amon's forces, civilians). Every one
of its event handlers checks membership before indexing — except
`add_upgrade_event`, which only tests for player 0.

`patch_spawningtool()` adds the same guard at import time, which brings the
corpus back to **495/495**. The patch is idempotent and checks it only applies
once. Drop it the day the library fixes this upstream.

A second trap on the same ground: some co-op units arrive **with no name**.
`pretty()` renders them as "unknown unit" rather than bringing the render down.

---

## Tests

No replay is versioned: these are private games, and a `.SC2Replay` holds both
players' handles. The suite therefore covers the pure functions (name splitting,
block detection, economy-table consistency, player selection), the Markdown
rendered from a synthetic report, and the HTTP contract (validation, size cap,
unreadable file, usage counter, language negotiation). Checks against real files
are done by hand with `cli.py`.

---

*Julien (Éole) Avarre — MIT*
