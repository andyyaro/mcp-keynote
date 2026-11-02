# mcp-keynote launch film: SPEC

```text
GOAL:    a developer who uses AI tools understands, in about a minute, what mcp-keynote is and why it holds:
         an MCP server that builds a whole Keynote deck from one spec in one call. It checks the spec before
         anything is made, passes text to AppleScript as data and never as code, draws native Keynote
         objects, and reads a deck back into the same spec. The proof is 757 unit tests and 289 live checks
         against a real Keynote. Upstream is credited honestly: ByAxe/keynote-mcp, a fork of easychen's original.
OUTPUT:  HyperFrames 0.8.173, 1920 x 1080, 30 fps, 66.6 s = 1998 frames (timed from the voice: sound/timing.json).
         renders/mcp-keynote-v1.mp4. Burned-in subtitles; the end card's two on-screen lines are left out of
         the captions, as in CERFODES.
SOUND:   (sound stage, 2026-11-01: sound/music.py, sound/mix.py, sound/grid.json, sound/timing.json)
         Music: "Angel Watching Me" (Arulo, Mixkit 432, Mixkit Stock Music Free License): relaxed pop/R&B,
         carefree, 100.7 s long.
         Grid (librosa on sound/track.mp3, checked on the kick onsets): 105.0 BPM, beat 0.571430 s, bar 2.285719 s.
           The kick onsets fit that grid to 3.3 ms over 90 hits. librosa's tempo guess (103.4) is a quantised bin
           and its beat tracker locks onto the off-beat, so the research stage's 103.4 BPM / 18.15 s were close
           but not exact. The groove's first kick is at track 18.247 s; track bar n starts at
           18.247 + (n - 8) x 2.285719 s (bar 0 at -0.04: the track opens on a bar line). The kick plays beats
           1, 2 and 3. The phrases are 2 bars long (odd bars about 2 dB fuller), so every join keeps the parity.
         Track map (RMS and band energy per bar):
           bars  0-7   0-18.25      the intro: keys only. Bar 7 swells into the drop
           bar   8     18.25        THE DROP: kick, hats and bass together
           bars  8-15  18.25-36.51  groove A
           bars 16-19  36.51-45.66  breakdown: kick and bass out, the hats carry on; bar 19 brings the bass back
           bars 20-39  45.66-91.37  full groove
           bars 40-43  91.37-99.5   the track's own fade-out (about -2 dB a beat)
         The edit (joins 20 ms before a downbeat's onset, 12 ms crossfades; all film times below):
           0-5.714        track 12.51-18.23   the end of the intro under the hook, from a beat, faded in 0.3 s
           5.714          THE DROP on "mcp-keynote" (v02's first word starts at 5.734, on the first kick)
           5.714-24.000   groove A, all 8 bars
           24.000-28.571  a lighter stretch of 2 bars: breakdown bar 16, then bar 19 (bars 17-18 cut), under v06
           28.571         the groove returns (bar 20) on v07's first word, "so a title full of quotes"
           60.571         the end card on bar 40, the track's own fade-out (bars 34-39 skipped), plus a 2.5 s fade
           66.600         the end
           Film bar lines: 5.714 + k x 2.2857 (8.0, 10.286, 12.571, ... 56.0, 58.286, 60.571).
         Voice: Kokoro af_heart, speed 1.0 for every line (narration/takes/<id>.1.wav; the 1.06 takes are there
           too). All 14 lines transcribe word for word (mlx-whisper large-v3-turbo, match 1.00). v06 is spoken
           from "Applescript" (one word): "Apple Script" came out as "Apple's script" at both speeds.
           lines-tts.json keeps "M.C.P. Keynote", "P.D.F.", "H.T.M.L.", "By Axe", "Easy Chen", "Describe deck".
           Whisper writes the words in window.VO as "MCP" "Keynote", "20", "81", "17", "757", "289",
           "AppleScript", "Describe" "deck", "Git", "Axe's", "Chen's": cue on those spellings.
         Slots (clip start-end, film s; the speech starts ~0.065 s into each clip):
           v01 0.75-5.00 · v02 5.67-9.43 · v03 10.25-14.59 · v04 15.04-17.89 · v05 18.62-22.95 ·
           v06 23.66-27.91 · v07 28.45-31.41 · v08 32.06-37.86 · v09 38.22-41.92 · v10 42.62-47.13 ·
           v11 47.83-50.29 · v12 50.80-54.84 · v13 55.54-60.14 · v14 61.02-65.06
           Breaths 0.36-0.82 s between clips; the commas inside a thought (v06 > v07, v08 > v09) get the shortest.
         Word anchors (film s): "81" 3.57 · "MCP" 5.73 · Claude 10.37 · Slides 11.73 · tables 12.35 · charts
           12.87 · notes 13.31 · transitions 13.77 · checks 15.50 · created 17.32 · typo 18.78 · invented 19.56 ·
           named 20.84 · AppleScript 24.54 · arguments 25.48 · never 26.22 · quotes 29.31 · break 29.93 ·
           native 33.00 · live 34.02 · "17" 35.26 · styled 36.76 · PDF 38.94 · PowerPoint 39.70 · movie 40.62 ·
           HTML 41.12 · Describe 42.69 · same 45.02 · diff 46.40 · "757" 47.91 · "289" 51.92 · None 53.92 ·
           rebuilds 55.70 · Axe's 56.32 · fork 58.48 · Easy 58.90 · "MCP" (v14) 61.09 · declarative 64.00.
           The scenes still find them through W() over window.VO, so a re-voiced line re-times itself.
         Levels (measured on the final mix): master -16.0 LUFS integrated, true peak -1.9 dBTP, LRA 1.5 LU.
           Speech -15.7 LUFS (the lines butted together, as they sit in the mix). The bed 9.2 dB under the voice
           before ducking, ducked 4.5 dB more while she speaks: 13.4 dB under her. Short-term loudness holds
           -15.6 to -17.6 LUFS through the film. mix.py measures the voice as stereo (secure-data-hub measured
           the mono file and also boosted by its speaking fraction, so its bed sat ~5 dB lower than its notes say).
         Effects: soft Mixkit UI sounds from sound/sfx-src (secure-data-hub's set), one vocabulary:
           pop         a card or the mark arrives (soft, never loud)
           tick        a key, chip or word lights on the voice (spec keys, export chips, thumbnails)
           whoosh_air  a camera glide, the thumbnails gathering, the argv chip travelling
           pop_hard    (low, -6 dB) ONLY the two rejected keys in the validation reply
           sweep       the pull-back to the whole board
           counters    the hook's 1->81 and the proof's 757: a few thinned ticks, never a rattle
           Placed (finish stage): 75 effects in sfx_events() in sound/mix.py, each cued through the scene's own
           word cue so its peak lands one frame after its picture. The drop is a riser + pop_hard on 5.714 with
           the gathering whoosh at 5.41. The low pop is pitch 0.8 (secure-data-hub's denial sound); pop_hard is
           used only on the drop. Each effect is levelled against the bed at that moment (K-weighted: its
           loudest 100 ms against the bed's 400 ms around it) at +3 to +4 dB, capped at 4 dB under the voice's
           level; mix.py prints the measured level of every one. Final: -16.0 LUFS, true peak -1.9 dBTP
           (mix.wav) and -1.8 dBTP (the mp4).
LOOK:    Reference: Andy's CERFODES architecture film (its 1080p English render), built in the
         HIG Native design system (Andy's unofficial web design system after Apple's HIG). Taken from it:
           ground     grouped background #f2f2f7; zones are fill-quaternary rgba(116,116,128,.08) at radius 26
           cards      white #ffffff, radius 20, no shadow; a 44 px coloured rounded tile (radius 11) holding a
                      white 24 px line glyph from the HIG icon set (copy CERFODES scripts/build-icons.mjs and
                      scripts/vendor/hig-icons.js); a bold title 22-23 px; a grey secondary line 18 px
                      label-secondary #68686d; status as a dot + word ("● verified live")
           skeletons  placeholder cards arrive early at 50% and fill in on the narrated word
           wires      thin grey arrows, 2.5 px system-gray #8e8e93 with small filled heads; dashed for "reads
                      back" and "checks"; small grey edge labels at 17 px
           camera     one big board (world 1920 x 1080) that the camera glides and zooms across (close shots at
                      zoom >= 1.55), then pulls back to the whole architecture at zoom 1.0 and holds about 4 s,
                      with the secondary lines folded away (titles and status words stay)
           titles     a section title at the top left (bold 30 px) + a small grey subtitle (19 px), outside
                      the camera, changing per beat
           captions   burned-in subtitles in a dark rounded pill at the bottom: rgba(0,0,0,.74), radius 18,
                      white 38/47 px weight 500, at most 2 lines of 42 characters, bottom 30 px. The band at
                      y >= 936 stays free: the board is masked to y < 930, as CERFODES' #a-fade does
           end card   the project's mark, the wordmark, and two short lines with icons
         Moved onto mcp-keynote's own brand (assets/brand, Andy's 2026-11-01 logo):
           mark       assets/brand/icons/icon-rounded.svg (three slide cards on the sky #8EC9FF square)
           wordmark   assets/brand/wordmark-navy.svg (Archivo Expanded ExtraBold as shapes, navy #0B1E3F),
                      cut from lockup/lockup-color.svg
           colour     brand blue #2F64B0 tiles = mcp-keynote's own code (server.py, Spec check, build_deck,
                      fragments.py, describe_deck); system-indigo #6155f5 = Keynote and what it draws;
                      system-gray = plumbing (client link, runner, styles); system-teal #00c3d0 = the MCP
                      client; system-green #34c759 = status dots only (verified, passing, 0 failed);
                      system-red #ff383c ONLY on the two rejected keys; navy #0B1E3F for the big numerals
                      (81, 757, 289) and the wordmark
           type       the system face loaded exactly as CERFODES does: @font-face "HostUI" src local("SF Pro"),
                      local("SF Pro Display"), local(".SF NS"), weight 100 900; --font-ui: "HostUI",
                      -apple-system, …, sans-serif. Code words (build_deck, describe_deck, on run argv, file
                      names) are in the SAME sans: semibold, in a fill-tertiary capsule when inline. The JSON
                      in the spec window is the sans at 20 px, keys in #2F64B0. NO MONOSPACE anywhere: never
                      the HIG --font-mono stack, never SFNSMono, never ui-monospace/Menlo/Courier/Consolas.
                      No Montserrat caps are needed: every label is sentence case in the system sans.
MOTION:  CERFODES' vocabulary, calm:
           pop         opacity 0, y +18, scale .96 -> 1, back.out(1.5), 0.6 s
           light       a skeleton card at 50% goes to 100%, its content rises 10 px, a 1.035 scale bump
                       0.2 s in, then back over 0.35 s, on the voice's own word (W() over window.VO)
           wire        the stroke draws (strokeDashoffset 1 -> 0, 0.45 s, power2.inOut); the head fades in
                       at the end. Dashed wires reveal through a mask, so the dashes stay put
           dot         a status dot + word slides in from x -8, 0.45 s after its card lights
           token       a small chip travels a wire, drawn UNDER the cards so it shows only in the gaps
           camera      glides power2.inOut 1.1-1.5 s, never during a key word
           fold        at the overview, secondary lines fade out (0.35 s), then display:none while the camera moves
           exits       fade 0.4 s; scene slots overlap 0.4 s, so they crossfade without an empty frame
           none of     blur entrances, screen shake, bouncing loops, typing floods
SHOTS:   (windows from sound/timing.json: scenes s1-s4 crossfade over 0.4 s; the board's beats b1-b7 are in
         window.TM too; each beat starts ~0.35 s before its first line, so the camera moves sit in the breaths)
         s1 hook      0-6.114  v01 (0.75-5.00, "81" at 3.57). Title "One element at a time" · "a 20-slide deck, built with primitive
                               tools". One white card: a 5 x 4 grid of 20 skeleton slide thumbnails filling one by
                               one. Beside it a counter card: a navy numeral counts 1 -> 81 and lands on "81" with
                               the voice. Under it ONE line shows the current call, changing calmly through
                               create_presentation, add_slide, add_title and add_bullet_list. Status "● 81 tool
                               calls". One line at a time: never a log flood.
         s2 name      5.714-10.286 v02 (5.67-9.43), ON THE DROP (5.714): the 20 thumbnails gather into one stack and the mark pops
                               (icon-rounded.svg, 220 px). The wordmark rises under it (about 900 px wide). A chip
                               follows: doc glyph + "build_deck · 1 call, not 81".
         s3 board     9.886-60.971 (settled on the bar line 10.286) one persistent composition (like CERFODES' arch-diagram.html) for b1-b7:
           b1 spec    9.886-18.27 v03, v04. The camera is on the left column. The MCP client card (teal tile,
                               person glyph) with chips "Claude Code", "Claude Desktop", "any MCP client". Under
                               it the spec window, whose keys light on the voice: slides, "table", "chart",
                               "notes", "transition". The wire "tools/call · stdio" draws to server.py ("MCP
                               stdio server · tool routing", ● 58 tools). The camera glides along row 1 to Spec
                               check ("the whole spec, before anything is created").
           b2 checked 18.27-23.3  v05. The real validation reply opens as a white window over row 2 (dim row
                               2 to 30% under it). Header "Spec validation failed (4 problem(s)); nothing was
                               created". Two lines light: "slides[0].layuot · Did you mean 'layout'?" and
                               "fill_color · not a capability of Keynote's AppleScript · use add_colored_panel".
                               Each has a red x mark (low pop_hard). Status "● 0 AppleScript calls".
           b3 argv    23.3-31.7  v06 (on the lighter stretch), v07 (the groove returns on "so", 28.571). The camera goes down the pipeline: Spec check ↓ build_deck ↓
                               fragments.py ↓ osascript runner → Keynote 14.5. The runner card shows the real
                               lines "on run argv" and "make new text item with properties {object text:(item 2
                               of argv)}". A capsule holding the title '"; do shell script "true"; "' travels the
                               wire labelled "argv" into Keynote. Keynote's mini slide shows it as plain title
                               text. Runner status "● 108 injection tests".
           b4 native  31.7-42.26  v08, v09. The camera moves to the right zone. Keynote 14.5 (● verified live)
                               draws into the slide strip above it, and the thumbnails light on the voice: the
                               native table with its Total row "=SUM(B2:B3)" turning to 35 on "live formulas";
                               the pie North/South/West 30/45/25 on "chart types", with the chip "17 types"; the
                               three styled lines (maroon solid, black dotted, salmon dashed with an arrow) on
                               "connectors". Then the export chips light one by one: PDF, PowerPoint, movie,
                               HTML (images and Keynote 09 already sit there, unlit).
           b5 round   42.26-47.47 v10. A dashed wire draws Keynote → describe_deck → back to the spec window
              trip                 ("same spec"). The tri-colour title thumbnail "Building A Secure Client Data
                               Hub" (black / #830041 / #F09490) appears. The spec window shows its "runs" lines
                               lighting in the same three colours, and a grey edge label "runs survive the
                               rebuild". Camera about zoom 1.2.
           b6 proof   47.47-54.9  v11, v12. The proof row. "757" counts up to "757 unit tests" (● passing,
                               "pytest · CI on macos-latest, Python 3.11, 3.12, 3.13"). Then "289 live checks"
                               (● 0 failed, "scripts/verify_tools.py · Keynote 14.5") on "none failed". A dashed
                               wire goes harness → Keynote. "ruff · mypy, strict mode" (● clean) lights quietly.
           b7 overview 54.9-60.971 v13 (55.54-60.14). Pull back to the whole board (zoom 1.0, sweep) and fold the secondary
                               lines. The header "mcp-keynote architecture" appears with a legend: ● verified
                               against Keynote 14.5 / ● tested in CI, no Keynote / ● rejected. The upstream card
                               lights on the voice: "easychen/keynote-mcp" › "ByAxe/keynote-mcp" › "this rebuild".
                               Holds about 5.5 s (the full board is up by the bar line at 56.0).
         s4 end       60.571-66.6 v14 (61.02-65.06), on the track's own fade-out. Mark (200 px), wordmark, then two lines with glyphs: doc "Keynote decks,
                               built from one declarative spec." and globe "github.com/andyyaro/mcp-keynote".
                               These two lines are not repeated in the captions. The card fades over the last
                               second with the music's outro.
ARCH:    the board, 16 parts, real names, world px (x, y, w, h); the overview frame is y 100-930:
           left    MCP client (40,150,320,130) · Claude Code, Claude Desktop, any MCP client
                   Deck spec window (40,300,320,460) · the live harness's own spec, trimmed (see OBJECTS)
           zone    "keynote-mcp server" · "Python · MCP stdio" (400,110,840,650), two columns x 430 / 850, w 360:
                   r1 y170  server.py · "MCP stdio server · tool routing" ● 58 tools
                            Spec check · "the whole spec, before anything is created"
                   r2 y320  Styles · ".keynote-mcp.toml · plain, boardroom, midnight, editorial, sdh"
                            build_deck · "the whole deck in one call · 5 slides per AppleScript session"
                   r3 y470  Rendered PNGs · "panels and styled_line strokes, exact colour"
                            fragments.py · "one source for every element's AppleScript"
                   r4 y620  describe_deck · "reads a deck back into the same spec"
                            osascript runner · "your text as argv, never in the script" ● 108 injection tests
           zone    "On the Mac" · "Keynote 14.5 · macOS 26.5.1" (1280,110,600,650):
                   Slides and exports (1310,170,540,400): 4 thumbnails + chips PDF · PPTX · movie · HTML ·
                   images · Keynote 09
                   Keynote 14.5 (1310,600,540,124) · "driven through its AppleScript dictionary" ● verified live
           proof   (y 800-900) 757 unit tests (40,800,420,100) · 289 live checks (490,800,440,100) ·
                   ruff and mypy (960,800,280,100) · Upstream (1280,800,600,100)
         wires:    client → server.py "tools/call · stdio" · server.py → Spec check "spec" ·
                   Spec check ↓ build_deck "valid" · Styles → build_deck "style" · build_deck ↓ fragments.py ·
                   fragments.py → Rendered PNGs "panels, strokes" · fragments.py ↓ osascript runner
                   "AppleScript" · osascript runner → Keynote 14.5 "argv" · Keynote 14.5 ↑ Slides and exports
                   "draws, exports" · Keynote 14.5 ⇢ describe_deck (dashed, routed under row 4)
                   "reads back" · describe_deck ⇢ Deck spec (dashed) "same spec" · 757 unit tests ⇢ server
                   zone (dashed) "CI" · 289 live checks ⇢ Keynote 14.5 (dashed) "live". Upstream has no wire.
         glyphs:   person.crop.circle (client), doc (spec, end line), list.bullet (server.py), checkmark.circle
                   (Spec check), square.3.layers.3d.top.filled (build_deck), square.grid.2x2 (Styles),
                   document.on.document (fragments.py), photo (Rendered PNGs), arrow.uturn.backward
                   (describe_deck), lock (runner), play.fill (Keynote; never the Keynote app icon),
                   square.and.arrow.up (exports), checkmark.circle.fill (tests), flag (live checks),
                   gearshape (ruff and mypy), arrow.uturn.forward (upstream), globe (URL).
OBJECTS: real artifacts only (sources and values in FACTS.md):
           the spec window (scripts/verify_tools.py:2240-2278, trimmed, sans): "style": "boardroom" · slide 1
             elements title "Verify Deck" + subtitle "harness build", "notes", "transition": {"effect":
             "dissolve", "duration": 0.7} · slide 2 "table" + "chart_type": "pie" · slide 3 "panel" + two
             "bullets" with "column": "left"/"right"
           the validation reply, verbatim from the code with osascript mocked: 4 problems, 0 osascript calls
           the adversarial title '"; do shell script "true"; "' (tests/unit/test_injection.py ADVERSARIAL) and
             the generated lines "on run argv" / "make new text item with properties {object text:(item 2 of argv)}"
           thumbnails, REDRAWN in HTML from repo specs (there are no slide screenshots in the repo, and Keynote is
             not driven): the title slide; the table Team/Now/Plan with "=SUM(B2:B3)" -> 35 (verify_tools.py:1806;
             show the formula or 35, never an invented total); the pie North/South/West 30/45/25 (:1857); the
             styled lines (:244-283); the tri-colour title (:1203-1233)
           numbers: 81 vs 1 call (README:108; no seconds on screen), 58 tools (tools/list), 17 chart types,
             43 transitions, 5 built-in styles, 108 injection tests, 757 unit tests (my run @0d42936),
             289 live checks with 0 failed (CHANGELOG 4.1.0), Keynote 14.5 on macOS 26.5.1
           credit: easychen/keynote-mcp (the original) › ByAxe/keynote-mcp (English, packaging, the skill, build
             animations) › this rebuild (49 commits on top)
BANNED:  monospace fonts of any kind (grep mono|Mono|monospace|Courier|Menlo|Consolas|ui-monospace|SFNSMono
         before every snapshot); em dashes; en dashes as separators or ranges (write "3.11, 3.12, 3.13", never a dashed
         range); the Huly look; drop shadows on content; a row of three feature cards; the logo docked in
         a corner; a busy, crammed frame (close shots carry the reading; the overview shows titles only);
         screen shake; floods of log lines or messages; "59 tools"; "95%"; "196 live checks"; seconds from the
         benchmark; the upstream assets/logo.png; the brand sheet (it says 59); Apple's Keynote icon or any
         Apple mark; invented slides, data, users or quotes; driving Keynote or any desktop app.
QA:      1.5, 4.6, 7.4, 12.5, 16.8, 21.2, 26.0, 30.6, 35.0, 39.8, 44.8, 50.0, 54.2, 58.6, 63.0, 66.3
         At each: no monospace, no dashes, nothing in the caption band but the pill, every number matches
         FACTS.md, cards readable at the shot's zoom (>= 22 px titles at zoom 1.0), the drop lands on the
         name, and no Kokoro mispronunciation (listen for "M.C.P.", "git", "By Axe", "Easy Chen", "describe deck").
```

## Notes for the build stage

- Copy the plumbing from `secure-data-hub/`: `build.py`, `index.html` (scene hosts, `W()`), `narration/pick.py`, `sound/music.py`, `sound/mix.py`, `sound/sfx-src/`, `assets/vendor/gsap.min.js`, `hyperframes.json` and `package.json`.
- From CERFODES, copy:
  - the `HostUI` @font-face, the light token block and the `#subtitles` / `.sub` styles from `source/index.html`;
  - the card, wire, camera (`C()`), `pop`, `ph`, `light` and `wire` helpers from `source/compositions/scenes/arch-diagram.html`;
  - `source/scripts/build-icons.mjs` with `source/scripts/vendor/hig-icons.js`, changing its `USED` list to the glyphs above.
- Captions: the CERFODES chunking (`max_chars` 42, `max_lines` 2, `lead` 0.05, `tail` 0.3, `min_dur` 1.0, `bridge` 0.7), driven by the word times in `window.VO`. The written text comes from `narration/lines.json`. v14 is on screen, so it is not captioned.
- Run the banned-font grep over `index.html`, `compositions/` and `assets/*.js|css`. The `.md` docs name the banned fonts on purpose and will always match.
- Kokoro takes: `--speeds 1.0,1.06`. The film uses the 1.0 takes and runs 66.6 s, so nothing was trimmed.
- Done in the sound stage: `narration/pick.py`, `sound/music.py`, `sound/mix.py`, `sound/sfx-src/` and `build.py` are copied and adapted.
  - `build.py` expects the scene hosts `s1-hook`, `s2-name`, `s3-board` and `s4-end` in `index.html`.
  - `window.TM` (assets/timing.js) carries `drop`, `groove_back`, `end_card`, `duration`, `film_bars`, the windows `s1`-`s4` and the beats `b1`-`b7`.
  - `window.VO` (assets/vo.js) carries every line's start/end and its word times in film seconds.
  - `narration/pick.py takes v06` re-picks a single line and keeps the others' word times.
  - To change a slot or a scene window, edit `SLOTS` / `SCENES` / `BEATS` in `sound/mix.py`, re-run it, then `python3 -I build.py`.
- The finish stage adds the remaining effects to `sfx_events()` in `sound/mix.py` (the drop and end card are there), re-runs it, and muxes `assets/audio/mix.wav` over the render as secure-data-hub does.
