# Modernization report — keynote-mcp 2.0.0

Branch `modernize`, 2026-07-25/26. Environment ground truth in
[ENVIRONMENT.md](ENVIRONMENT.md); per-tool verification in
[TOOL_MATRIX.md](TOOL_MATRIX.md). Every claim below was verified by running
something — the sdef dump, 277 tests, a 57-check live driver
(`.scratch/verify_tools.py`), or the end-to-end `claude mcp add` cycle.

## What was broken, and how I know

**AppleScript injection everywhere.** Every tool f-string-interpolated user
text into AppleScript source with only `"` → `\"` escaping. A title ending in
a backslash broke the script; embedded `" … tell application …` payloads
could rewrite it. Proven by reading `utils/applescript_runner.py:_format_args`
and every tool method; the replacement (osascript argv) is proven safe by 70+
injection unit tests plus a live adversarial round-trip against Keynote.

**stdout pollution.** `server.py:37` printed a warning to stdout when
UNSPLASH_KEY was absent — that is inside the JSON-RPC channel, and it fired
on every startup without the key. `start_server.py` printed banners. Found by
grep; absence now enforced by tests (a subprocess handshake test asserts the
first stdout bytes parse as JSON-RPC, and a static test forbids `print(` in
`src/`).

**Silent lies from Keynote.** `delete slide 999` and `delete text item 99`
succeed silently on Keynote 14.5 (verified with count-before/count-after
probes), so the old tools reported deletions that never happened. The tools
now check `exists …` first and raise error -1719.

**Wrong error taxonomy.** Keynote 14.5 reports bad indices as **-1719
"Invalid index"**, not -1728 (verified live); the first version of my own
error mapper misclassified -1719 as an Accessibility failure — caught because
the live driver exercised the failure path, not just the happy path.

**UI-scripting fragility.** Build tools addressed `window "<doc name>"`,
but window titles don't reliably match document names — the integration suite
failed with "Can't get window \"integration-test.key\"" while a solo run
passed. Now targets `window 1` of the Keynote process; integration suite is
deterministic across repeated full runs.

**Destructive screenshot side effect.** `screenshot_slide` ended with
`set skipped of every slide to false`, erasing the user's intentional
skip states. Now saves and restores per-slide state.

**Font clipping (the skill's "CRITICAL" bug).** Fonts > 48pt truncate to 1-2
characters in the auto-sized box. The server now sizes the box from the text
before applying the font and re-sets the text afterwards — verified live at
96pt, and the skill's 4-step manual workaround is obsolete
(TOOL_MATRIX.md § absorbed).

**Packaging drift.** Three competing dependency declarations (setup.py,
requirements*.txt, pyproject) with unused deps: Pillow and typing-extensions
were never imported (grep), python-dotenv only behind guarded imports whose
`.env`-crawl walked up from site-packages. `.gitignore` ignored `test_*.py` —
any test suite would silently never be committed.

**Dead code.** The entire `applescript/*.applescript` library (1,456 lines)
and the `.scpt` loader were unreachable — every tool used inline scripts, and
`.scpt` files were both never compiled and gitignored.

## What was fixed (by phase)

- **Phase 1** — PEP 621 pyproject (uv_build), `uv.lock`, `mcp>=1.28,<2`
  (1.28.1 resolved; PyPI-verified), requires-python ≥3.11, dead deps removed,
  [MCP_V2_MIGRATION.md](MCP_V2_MIGRATION.md) inventories every v2-affected
  SDK touchpoint.
- **Phase 2** — argv-based runner; stderr logging (`KEYNOTE_MCP_LOG_LEVEL`);
  bounded timeouts (30 s default, `KEYNOTE_MCP_TIMEOUT`, 60 s UI, 120 s
  export); -1743/-1728/-1719/assistive/-600/-1712 mapped to messages naming
  the exact System Settings pane; handlers never kill the process.
- **Phase 3** — all 45 tools validated against the sdef and executed live
  ([TOOL_MATRIX.md](TOOL_MATRIX.md)); skill workarounds absorbed; new
  `set_slide_content` (theme placeholders — idea cherry-picked from the
  betancur fork); removed `get_presentation_resolution` (duplicate),
  `create_presentation`'s implicit Desktop save + dead `template` arg,
  `add_image`'s movie/clipboard fallbacks.
- **Phase 4** — 270 unit tests / 95% line coverage (gate ≥85% in CI), 7
  integration tests (`-m keynote`, deselected by default, scratch-only,
  quits Keynote only if it started it).
- **Phase 5** — CI on macos-latest: ruff lint+format, mypy --strict, unit
  tests on 3.11/3.12/3.13; `make test-integration` documented as local-only;
  pre-commit with ruff + whitespace hooks.
- **Phase 6** — `claude mcp add keynote-mcp -- uv --directory … run
  keynote-mcp` verified: registers (health: Connected), initialize →
  tools/list → live tool calls. README/CLAUDE.md/CONTRIBUTING/CHANGELOG
  rewritten; ByAxe + easychen attribution and MIT license intact.

## Deliberately not fixed, and why

1. **MCP SDK v2** — pre-release only (2.0.0a3/b2 on PyPI, checked). Pinned
   to 1.x; the migration is inventoried to be a mechanical afternoon.
2. **Unsplash live verification** — no `UNSPLASH_KEY` on this machine. The
   HTTP layer is unit-tested against a faked aiohttp session; the AppleScript
   insertion path is shared with the verified `add_image`. Marked in
   TOOL_MATRIX.md.
3. **The giant if/elif dispatch** in `server.py` — ugly but total, typed,
   95%-covered, and exactly the surface v2 will reshape. Restructuring now
   would be churn ahead of a known breaking change.
4. **UI-scripting build tools remain timing-based** (fixed `delay` calls).
   Making them event-driven would be a rewrite of marginal value; they are
   integration-tested and the README documents flakiness expectations.
   Locale-dependence (English menu/button names) also remains.
5. **`clear_slide` leaves images** — preserved upstream behavior: it can't
   distinguish user images from decorative theme images, so deleting them
   risks damaging themed slides. Documented in the tool description.
6. **PyPI release workflow** untouched — publishing under a name owned by
   upstream's maintainer is not this fork's call to make. The workflow still
   works if a rename/ownership decision is made.
7. **Keynote error -10000 on `move slide <bad index>`** is passed through
   with the generic message — rare, and the text still includes Keynote's
   own description.

## Remaining risks, ranked

1. **UI-scripting brittleness (highest).** Build tools depend on Keynote's
   inspector layout, English UI labels, fixed delays, window focus, and an
   unlocked screen. A Keynote redesign breaks them silently. Mitigation:
   integration tier catches it locally; errors are actionable.
2. **Keynote version drift.** All verification is against Keynote 14.5 /
   macOS 26.5.1. Apple has changed AppleScript behavior between releases
   (e.g. the -1719 vs -1728 split). Mitigation: `docs/ENVIRONMENT.md`
   records the verified baseline; `make test-integration` re-verifies in
   minutes.
3. **MCP v2 cutover.** When 2.0 goes stable, new installs pinning `<2` are
   fine, but the ecosystem will move. The migration doc de-risks this to a
   scheduled task.
4. **Silent no-op surface may be larger than the two fixed cases.** I probed
   delete/move/set-position out-of-range, but other verbs may clamp instead
   of erroring. Pattern to apply: `exists …` guard before mutating verbs.
5. **TCC permission attribution confusion.** Users granting permissions from
   a different terminal than the one running Claude Code will see -1743
   despite "having granted" — the README, preflight script, and error text
   all address this, but it will remain the top support issue.
6. **Unsplash API drift** (lowest) — opt-in, isolated, unit-tested against
   today's response shape only.
