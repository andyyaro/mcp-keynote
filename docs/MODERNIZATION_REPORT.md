# Modernization report — keynote-mcp 2.x

Branch `modernize`, 2026-07-25/26. Environment ground truth in
[ENVIRONMENT.md](ENVIRONMENT.md); per-tool verification in
[TOOL_MATRIX.md](TOOL_MATRIX.md). Every claim below was verified by running
something — the sdef dump, the unit suite (295 tests at 2.1.0), a live
driver (`scripts/verify_tools.py`, 57 checks at 2.0.0, 91 at 2.1.0), or the
end-to-end `claude mcp add` cycle. §"Field test findings" at the end records
what the 2.0.0 verification missed and why.

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

## Field test findings (Phase 8, 2026-07-26)

A live 4-slide deck build — the first use of the server on work it did not
generate for itself — surfaced five defects that Phase 3's 57-check
verification had marked "verified". This section documents the gap rather
than quietly patching it.

### The root failure: verification that only ate its own cooking

`scripts/verify_tools.py` exercised documents **it created itself, with an
explicit `save_path`**. That single choice hid three classes of failure:

1. **`open_presentation` "verified" but wedging in the field.** The harness
   opened `.scratch/phase3-test.key` — a file Keynote itself had saved
   moments earlier, which leaves a per-file sandbox extension behind. So the
   AppleScript `open` verb worked in the harness and wedged the AppleEvent
   queue on any genuinely foreign file (zero windows, every subsequent event
   timing out, -1712 even at 90 s; only force-quitting Keynote recovers).
2. **`save_presentation` "verified" but trapping in the field.** The harness
   only ever saved documents that already had a file. On an untitled
   document, plain `save` opens a modal sheet that blocks the queue until
   timeout — after which Keynote completes a default save to iCloud as
   `Untitled.key`, so the "failed" call half-succeeded in the wrong place
   under the wrong name.
3. **Indices and counts taken on faith.** The harness confirmed elements
   existed but never fed a returned index back into a sibling tool.
   `add_title` reported "index 6" for the element `get_slide_content` and
   `move_element` addressed as 4 — any caller trusting the response moved
   the wrong element.

### What the field defects actually were (and the mechanism found)

- **Phantom text items, not a leak.** The observed "every add_* call leaves
  a 0x0 empty text item" was a misdiagnosis of mechanism, with a real
  observable: Keynote counts the slide's `default title item`/`default body
  item` objects among "text items" even when hidden (surfacing as 0x0
  empties at 0,0) and **twice** when showing (once in z-order, once
  trailing). Established by live experiment: an empty Blank slide reports
  `count of text items` = 2 with `count of iWork items` = 0, and on a themed
  slide `text item 2 is default title item` and `text item 5 is default
  title item` are both true. Fix: identity-filtered enumeration everywhere
  (`get_slide_content`, `get_slide_info`, `clear_slide`) and
  identity-located return indices in `_add_text_element`.
- **The index mismatch falls out of the same mechanism**: `count of text
  items` over-reports and the new item is not last (phantoms trail it).
- **Screenshot dishonesty.** Keynote's slide-image export omits unfilled
  placeholder boxes, so a clean-looking PNG "verified" a slide the editor
  showed full of placeholder boxes. `screenshot_slide` now counts what the
  export omitted and says the image is not a faithful editor view.
- **Unfilled default placeholders on slide 1.** New documents opened on a
  themed title layout whose placeholders the add_* tools overlap rather than
  fill. Policy decision: slide 1 now defaults to the Blank layout (matching
  `add_slide`); `set_slide_content` is the documented opt-in to theme
  placeholders and works on Blank slides.
- **x=0 titles.** `add_title`/`add_subtitle` gained `centered` — the
  read-width-then-move dance is now server-side, consistent with the Phase 3
  font-clipping absorption.

### Why Phase 3 missed it — and the process change

Phase 3's standard was "ran against a real document and read the effect
back". The gap: every input was one the server had just produced, so the
sandbox, save-sheet, and index-space failure modes were structurally
unreachable. The harness (now 91 checks, 0 failed) additionally exercises:
the untitled-document save path and its refusal guard, opens from
~/Downloads **and** ~/Desktop with a queue-liveness probe after, a
create→move-by-returned-index→read-back round-trip for all seven add_*
text tools, the phantom regression (five adds → exactly five items),
screenshot honesty in both directions, and centering math against slide
width. [TOOL_MATRIX.md](TOOL_MATRIX.md) now records per tool what its
verification actually exercises, so "verified" can be audited instead of
trusted. Defense in depth for the wedge that slipped through: the runner
probes on any timeout and fails fast with the `killall Keynote` recovery
once the queue is wedged (unit-pinned; deliberately not wedged live).
