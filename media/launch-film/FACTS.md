# mcp-keynote launch film: FACTS

Every claim that is spoken or shown, with where it comes from and the value checked on 2026-11-01.

- **Repo:** `andyyaro/mcp-keynote`, branch `master` @ `0d42936` ("Add project logo", 2026-11-01).
  The clone is at `<scratch>/films/mcp-keynote/clone/mcp-keynote`, where `<scratch>` is a scratch folder outside the repository; the probe scripts named below were kept there and are not part of this folder.
- **Version:** 4.1.0 (`pyproject.toml`, `CHANGELOG.md` [4.1.0] 2026-07-26).
- **Keynote was never driven for this film.** Andy is using this computer.
  - The unit suite ran with `subprocess.Popen` guarded (`<scratch>/films/mcp-keynote/guard/sitecustomize.py`), so `/usr/bin/osascript` and `/usr/bin/open` could not run.
  - Every probe mocked `subprocess.run`, as the repo's own unit tests do.
  - Live-Keynote figures are therefore quoted from the repo's own records and labelled as such below.

## Counts I measured myself

| Claim (on screen / spoken) | Verified value | How |
|---|---|---|
| "757 unit tests pass" (v11, proof card) | **757 passed, 8 deselected** (the 8 are the `-m keynote` integration tests), 17.6 s | `PYTHONPATH=<guard> .venv/bin/python -m pytest tests/ -q --cov=keynote_mcp` in the clone, Python 3.12.6, `uv sync --dev --frozen`. |
| Line coverage (not used on screen) | **90%** (3371 statements, 329 missed) | Same run. The README badge says 95%, which was the 2.x figure. **Do not show 95%.** |
| Lint and types clean (CI card: "ruff · mypy --strict") | `ruff check`: All checks passed. `ruff format --check`: 54 files already formatted. `mypy` (strict): no issues in 23 source files | Run in the clone. |
| CI green on master | GitHub Actions "CI" on `master` @ `0d42936`: **success** (2026-11-01T15:58Z) | `gh run list -R andyyaro/mcp-keynote`. The CI matrix is `macos-latest` × Python 3.11, 3.12, 3.13 plus ruff, ruff format and mypy (`.github/workflows/ci.yml`). Older unmerged branches (feat/theme-file, feat/edit-table, perf/batched-reads, fix/keynote-15-builds, 2026-09-24) failed CI. They are not on master and are not mentioned. |
| "58 tools" (server card) | `tools/list` returns **58 tools** without `UNSPLASH_KEY`, and **61** with it (+ `search_unsplash_images`, `add_unsplash_image_to_slide`, `get_random_unsplash_image`) | `<scratch>/films/mcp-keynote/probe/list_tools.py` speaks MCP stdio to `python -m keynote_mcp`. No tool was called. |
| "each run against a real Keynote" (58 tools) | `docs/TOOL_MATRIX.md`: all 58 non-Unsplash tools are "verified" against Keynote 14.5. The 3 Unsplash tools are "not verified live (no API key)". | Read the matrix row by row. |
| 108 injection tests (argv card status) | `tests/unit/test_injection.py`: **108 tests collected** | `pytest --collect-only`. |
| "17 chart types" (v08) | `CHART_TYPES` has **17** keys: area, area_3d, bar, bar_3d, horizontal_bar(_3d), line(_3d), pie(_3d), scatter, stacked_area(_3d), stacked_bar(_3d), stacked_horizontal_bar(_3d) | `src/keynote_mcp/tools/fragments.py:183`, imported and counted. README line 135 also says "17 native types". |
| "all 43 transitions" (native card chip) | `TRANSITION_EFFECTS` has **43** keys | `fragments.py:203`, counted. README line 133. |
| Built-in styles | **5**: plain, boardroom, midnight, editorial, sdh | `BUILTIN_STYLES` in `src/keynote_mcp/utils/styles.py:176` (+ `styles/sdh.keynote-mcp.toml`). README line 144. |
| Export formats | `export_pdf` (PDF: slides / with notes / handouts) + `export_presentation`: **pptx, movie (.m4v), html, images, key09** | `src/keynote_mcp/tools/export.py:55-60, 214`. README line 136. |
| Server name | `serverInfo.name` = `keynote-mcp` | The initialize response in `list_tools.py`. |

## Real outputs captured from the code (Keynote not involved)

1. **The validation reply (beat "checked first", v05).** I called `DeckTools().build_deck(spec=…)` with osascript mocked (`<scratch>/films/mcp-keynote/probe/real_replies.py`).
   - The spec held a slide key typo `layuot` and an invented element key `fill_color`.
   - The verbatim reply:
     ```
     Spec validation failed (4 problem(s)); nothing was created:
     - slides[0].layuot: unknown key for a slide. Did you mean 'layout'?
     - slides[0]: a slide accepts: body, elements, layout, notes, skipped, title, transition. Nothing was created.
     - slides[0].elements[0].fill_color: unknown key for an element of type 'title'. Not a capability of Keynote's AppleScript (shape/text fill color is not writable by AppleScript). Use add_colored_panel (rendered PNG, exact color) or set_element_opacity.
     - slides[0].elements[0]: an element of type 'title' accepts: centered, color, column, font_name, font_size, height, index, module, role, runs, text, type, width, x, y, zone. Nothing was created.
     ```
   - **osascript calls made: 0.** That backs "before anything is created" and the status "● 0 AppleScript calls".
   - The hint table is `src/keynote_mcp/utils/unsupported.py`.
2. **Text travels as argv (beat "text as data", v06-v07).**
   - Call: `ContentTools().add_title(1, '"; do shell script "true"; "')`. The payload is one of the `ADVERSARIAL` strings in `tests/unit/test_injection.py`.
   - The command was `['/usr/bin/osascript', '-']` with argv `['success', '"; do shell script "true"; "']`. (`success` is the mocked document name returned by the lookup call.)
   - The script begins `on run argv` / `set docName to item 1 of argv` / … / `make new text item with properties {object text:(item 2 of argv)}`.
   - "payload in source? False."
   - Runner: `src/keynote_mcp/utils/applescript_runner.py` (`subprocess.run(["/usr/bin/osascript", "-", *args], input=script)`).

## Claims quoted from the repo's own records (not re-run: they need a live Keynote)

| Claim | Value | Source |
|---|---|---|
| "Twenty Keynote slides, built one element at a time: 81 tool calls." (v01), "in one call" (v02), "1 call, not 81" chip | 20-slide deck: **81 primitive calls (21.8 s) versus 1 call (11.9 s)**, 6 osascript sessions | `README.md:108`; `CHANGELOG.md` [3.0.0] "Benchmark (20-slide deck, live)". The README asks to read it as a call count, not as speed, so **the film shows call counts only and no seconds.** |
| "289 live checks ran: none failed." (v12) | **289 live checks, 0 failed** at 4.1.0 | `CHANGELOG.md:12` ([4.1.0]). The README (line 21) and TOOL_MATRIX (line 9) still say "196 live checks, 0 failed": that was the 3.0.0 run. The newer figure is used, sourced to the CHANGELOG. |
| Verified against Keynote 14.5 on macOS 26.5.1 | Keynote **14.5**, macOS **26.5.1** (build 25F80), Apple Silicon | `docs/ENVIRONMENT.md` (Host table); `docs/keynote-14.5.sdef` is tracked. |
| "Your text reaches AppleScript as arguments, never pasted into the script, so a title full of quotes can't break it, or take it over." (v06-v07) | "User input reaches AppleScript via `osascript` argv, never string interpolation, so titles containing quotes, backslashes, emoji, or CJK can't break (or hijack) the script." | `README.md:28-30`. `docs/MODERNIZATION_REPORT.md` §"AppleScript injection everywhere" adds "proven safe by 70+ injection unit tests plus a live adversarial round-trip against Keynote" (108 tests today, counted above). Before the rebuild every tool f-string-interpolated user text (same section). |
| "The server checks all of it before anything is created." (v04) | "whole-spec validation before anything is created" / "Nothing is created when validation fails" | `README.md` Available Tools, build_deck row; `build_deck` tool description (tools/list); proven by output 1 above. |
| "A typo or an invented key comes back named, with what to use instead." (v05) | Unknown keys are rejected at every level (deck, slide, element, run) with the accepted set named; invented capability names get the alternative | `CHANGELOG.md` [4.1.0] Fixed, first bullet; output 1 above. |
| "Claude writes one spec: slides, tables, charts, notes and transitions." (v03) | The spec shape `{title?, theme?, style?, …, slides: [{layout?, title?/body?, notes?, skipped?, transition?, elements?: [...]}]}`, with element types incl. table, chart | The `build_deck` description from tools/list (also `tools/deck.py:81` `_ELEMENT_TYPES`). "Claude" stands for the MCP client: README registers it with `claude mcp add keynote-mcp -- uv --directory … run keynote-mcp` (line 43), and also documents Claude Desktop and "Other MCP clients … transport stdio" (lines 49-64). |
| "native tables with live formulas" (v08) | "tables (data, live `=SUM(…)` formulas, styled headers, column widths)" | `README.md:135`. |
| "styled connectors" (v08) | `styled_line`: "connectors whose colour, width, dash and arrowheads carry meaning", rendered to a transparent PNG because Keynote has no stroke API | `CHANGELOG.md` [4.0.0] Added; `docs/CEILING.md`; README "Known Keynote limits". |
| "exports to PDF, PowerPoint, a movie or HTML" (v09) | "export to PDF, PPTX, movie, or HTML" | `README.md:9-13`, line 136; export.py (above). |
| "describe_deck reads an open deck back into the same spec, ready to diff in git." (v10) | "`describe_deck` reads any open deck back as JSON for diffing or round-tripping"; "decks round-trip and become diffable in git" | `README.md:106`; `CHANGELOG.md:245` [3.0.0]. Documented limit: charts come back geometry-only. |
| Runs survive the round trip (round-trip card caption) | "a described deck keeps its runs when rebuilt"; verified in pixels after rebuilding from the unedited description | `CHANGELOG.md` [4.1.0] Added; `scripts/verify_tools.py` PHASE 10 (lines 1188-1290). |
| Zone colours within 8/255 (optional overview line, not narrated) | "The rendered panels reproduce the deck's real zone colours to within 8/255" against a real 35-slide architecture deck | `docs/FIDELITY_REPORT.md:93`. |
| Slides batched per AppleScript session (build_deck card secondary line) | "slides batched 5 per osascript session" | `CHANGELOG.md:232` [3.0.0]. |
| Every reply names its document (session card, optional) | "every reply echoes its target, and an ambiguous target is an error that NAMES the open documents" | `CHANGELOG.md` [4.0.0] Fixed, first bullet; `src/keynote_mcp/utils/session.py`. |
| Error mapping (runner card secondary line, optional) | -1743 / -1728 / -1719 / assistive / -600 / -1712 mapped to messages naming the exact System Settings pane | `docs/MODERNIZATION_REPORT.md` Phase 2; README Troubleshooting table. |

## Credit (v13 and the upstream card)

| Claim | Verified value | Source |
|---|---|---|
| "It rebuilds ByAxe's keynote-mcp, a fork of easychen's original." | GitHub: `andyyaro/mcp-keynote` parent = **ByAxe/keynote-mcp**, source = **easychen/keynote-mcp** | `gh api repos/andyyaro/mcp-keynote` (`.parent`, `.source`); `gh api repos/ByAxe/keynote-mcp` parent = easychen/keynote-mcp. |
| What upstream contributed (upstream card secondary lines) | easychen: the original server (2 commits, 2025-07-05/06). ByAxe (commits by `alekseilitvinau`, 15 commits, 2026-03-09..13): English translation, PyPI packaging, the keynote-presentation Claude skill, build-in animation tools (`add_build_in`, `remove_build_in`, `add_builds_to_slide`), `clear_slide`, `add_shape`, `set_element_opacity` | `git log` of master; `gh api repos/ByAxe/keynote-mcp/commits`; README Acknowledgments (lines 232-235). |
| This rebuild's share | **49 commits** on top of ByAxe's master (`compare ByAxe:master...andyyaro:master` → ahead_by 49, behind_by 0); 66 commits on master in all (andyyaro 49, alekseilitvinau 15, easychen 2) | `gh api …/compare/…`, `git shortlog -sn master`. **The brief's "48 of the repo's 50 commits" does not match today's repo.** At Jul 26 Andy had 48 commits (before the 2026-11-01 logo commit), but the total was 65, not 50. If a commit figure goes on screen, use "49 commits on top of ByAxe's fork". The current plan shows none. |
| Tool growth (not narrated) | 45 tools verified at 2.0 → 59 at 3.0.0 → 61 at 4.0.0 (incl. the 3 opt-in Unsplash tools) | `CHANGELOG.md:192` (45 → 59), `:86` (59 → 61); `docs/MODERNIZATION_REPORT.md` Phase 3 ("all 45 tools"). |

## Numbers in the brief or the repo that are NOT used (and why)

- **"59 tools"** appears in the repo description, the README heading ("Available Tools (59)"), the brand README, the brand sheet (`logo-sheet.png`) and Andy's portfolio entry. The code serves 58 (61 with an Unsplash key). 59 was the 3.0.0 count, and it included the 3 Unsplash tools that were never verified live. The film says **58 tools** and keeps the brand sheet off screen. Andy may want to update the README, the repo description and the portfolio entry.
- **"Coverage 95%"** (README badge): the measured figure is 90%. Not shown.
- **"196 live checks"** (README, TOOL_MATRIX): superseded by 289 at 4.1.0 (CHANGELOG). Not shown.
- **SECURITY.md** is upstream's file: it lists 1.0.x as supported and points reporters at ByAxe's advisories. Not used.
- **21.8 s / 11.9 s:** the README says the gain is the call count, not the clock. Not shown.

## Brand

- **The mark, wordmark and lockup are Andy's**, added 2026-11-01 in `docs/assets/brand/` (commit `0d42936`). They are copied unchanged to `assets/brand/`.
  - `assets/brand/wordmark-navy.svg` was cut out of `lockup/lockup-color.svg`. It is the same glyph shapes, without the sky background or the mark.
- **Colours** (brand README): `#8EC9FF` sky, `#0B1E3F` navy, `#2F64B0` blue, `#FFFFFF`.
- **Wordmark typeface:** Archivo Expanded ExtraBold (OFL). It is already converted to shapes in every SVG, so no font file is needed. Supporting text on the sheet is Geist.
- **Tagline:** "Keynote decks, built from one declarative spec" (`logo-sheet.png`), used in v14 and on the end card.
- **`assets/logo.png` in the repo root is upstream's logo** (added by ByAxe in `4602a4d`). Not used.

## Redrawn, not captured

The repo holds **no slide screenshots or exported decks**: its `.scratch/` exports are gitignored, and Keynote may not be driven here. Every slide thumbnail in the film is redrawn in HTML from a spec in the repo, and says so in SPEC.md:

| Thumbnail | Spec it is drawn from |
|---|---|
| Title slide "Verify Deck" / "harness build", notes, dissolve 0.7 s | `scripts/verify_tools.py:2240-2278` (the 3.0.0 `build_deck` live check, style `boardroom`) |
| Native table Team / Now / Plan; Eng 24 30; Sales 11 14; Total `=SUM(B2:B3)` `=SUM(C2:C3)` | `scripts/verify_tools.py:1806-1809`. The live check asserts the formula stayed live and that Keynote computed **35** (24 + 11). The second total, 44, is plain arithmetic: show the formula or 35 only. |
| Pie chart North / South / West 30 / 45 / 25 | `scripts/verify_tools.py:1857-1864` (the rendered check found 3 slices) |
| Three styled lines: maroon `#8E1F55` solid, black dotted, salmon `#EFA3A0` dashed with an end arrow, over a salmon panel (radius 16) | `scripts/verify_tools.py:244-283` (phase9 strokes) |
| Tri-colour title "Building A Secure Client Data Hub": runs 1-10 `#000000`, 12-17 `#830041`, 19-33 `#F09490` | `scripts/verify_tools.py:1203-1233` (PHASE 10 runs). The source deck is the Secure Data Hub architecture deck (`docs/FIDELITY_REPORT.md`). |

The validation reply and the argv/script lines are real outputs (captured above), shown as text in the system sans, never monospace.
