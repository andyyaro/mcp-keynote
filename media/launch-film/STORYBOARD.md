# MCP Keynote launch film: storyboard and build

66.6 s, 1920 × 1080, 30 fps (1,998 frames). H.264 with AAC at 256 kb/s; measured on the MP4:
-16.0 LUFS integrated, true peak -1.8 dBTP, loudness range 1.5 LU. Made against `master` at
`0d42936` (version 4.1.0). Every claim in it and its source is in [FACTS.md](FACTS.md); the brief,
with every shot and timing, is [SPEC.md](SPEC.md).

## What is real and what is rebuilt

- **Real outputs, captured from the code** with `osascript` mocked, so Keynote was never driven:
  the validation reply ("Spec validation failed (4 problem(s)); nothing was created", with 0
  AppleScript calls made), and the `on run argv` lines the server writes for the adversarial title
  `"; do shell script "true"; "` from `tests/unit/test_injection.py`.
- **Measured in a clone of the repository:** 757 unit tests pass, `tools/list` serves 58 tools,
  108 injection tests, 17 chart types.
- **Quoted from the repository's records,** because they need a live Keynote: 81 calls against 1
  for a 20-slide deck (the README; call counts only, no seconds), and 289 live checks with none
  failed against Keynote 14.5 on macOS 26.5.1 (CHANGELOG 4.1.0, `docs/ENVIRONMENT.md`).
- **Redrawn in HTML:** the slide thumbnails (the title slide, the table with `=SUM(B2:B3)` and its
  total of 35, the pie at 30/45/25, the three styled lines and the tri-colour title), each from a
  spec in `scripts/verify_tools.py`, because the repository holds no slide screenshots. The deck
  spec on the board is the same file's own spec, trimmed.
- **Left out on purpose:** "59 tools" (the code serves 58), the 95% coverage badge (the measured
  figure is 90%), "196 live checks" (superseded by 289) and the benchmark's seconds.
  [FACTS.md](FACTS.md) says why for each.

## The film

| Time (s) | Scene | Narration | What you see |
|---|---|---|---|
| 0–6.1 | Hook | "Twenty Keynote slides, built one element at a time: 81 tool calls." | "One element at a time". A grid of 20 slide thumbnails fills one by one; a navy counter counts to 81 with the voice; one line shows the current call: `create_presentation`, `add_slide`, `add_title`, `add_bullet_list`. |
| 5.7–10.3 | Name, on the drop | "mcp-keynote builds the whole deck from one spec, in one call." | The 20 slides gather into the mark, which lands on the drop at 5.714 s. The wordmark rises; a chip: "build_deck · 1 call, not 81". |
| 9.9–18.3 | Board: one spec, one call | "Claude writes one spec: slides, tables, charts, notes and transitions. The server checks all of it before anything is created." | The MCP client (Claude Code, Claude Desktop, any MCP client) and the deck spec, whose keys light on the voice. The wire "tools/call · stdio" draws to `server.py` (58 tools); the camera glides to Spec check. |
| 18.3–23.3 | Checked first | "A typo or an invented key comes back named, with what to use instead." | The real validation reply opens over the board: the typo `layuot` ("Did you mean 'layout'?") and the invented `fill_color` each get a red mark. "0 AppleScript calls". |
| 23.3–31.7 | Text as data | "Your text reaches AppleScript as arguments, never pasted into the script, so a title full of quotes can't break it, or take it over." | Down the pipeline: Spec check, `build_deck`, `fragments.py`, the `osascript` runner, Keynote 14.5. The runner shows what `osascript` receives; the title travels the "argv" wire in a capsule, and Keynote's slide shows it as plain title text. "108 injection tests". |
| 31.7–42.3 | Native Keynote objects | "Then Keynote builds native tables with live formulas, 17 chart types and styled connectors, and exports to PDF, PowerPoint, a movie or HTML." | Keynote draws into the slide strip: the table with its `=SUM` row, the pie with "17 chart types", the three styled lines. The export chips light one by one: PDF, PowerPoint, movie, HTML. |
| 42.3–47.5 | Round trip | "describe_deck reads an open deck back into the same spec, ready to diff in git." | A dashed wire from Keynote through `describe_deck` back to the spec ("same spec"). The tri-colour title "Building A Secure Client Data Hub" and its runs in the spec, in the same three colours; "runs survive the rebuild", "diffable in git". |
| 47.5–54.9 | Proof | "757 unit tests pass. On a real Keynote, 289 live checks ran: none failed." | 757 counts up (passing, pytest in CI on macOS); 289 live checks (0 failed, `verify_tools.py` against Keynote 14.5). |
| 54.9–61.0 | The whole board | "It rebuilds ByAxe's keynote-mcp, a fork of easychen's original." | The camera pulls back to the whole architecture with a legend (verified against Keynote 14.5, tested in CI). The Upstream card lights: easychen/keynote-mcp › ByAxe/keynote-mcp › this rebuild. |
| 60.6–66.6 | End card | "mcp-keynote. Keynote decks, built from one declarative spec." | The mark, the wordmark, "Keynote decks, built from one declarative spec." and github.com/andyyaro/mcp-keynote, on the music's own fade-out. This line is not burned in, since it is on screen; it is in the captions file. |

## Look

- **Style:** the project has no interface, so the film is built like Andy's CERFODES architecture
  film: one big board that the camera glides and zooms across beat by beat, then pulls back from to
  show the whole architecture. The design system is HIG Native, Andy's unofficial web design system
  after Apple's HIG: the grouped background #f2f2f7, white cards (radius 20, no shadow) with a line
  glyph in a coloured tile, status as a dot and a word, skeleton cards that fill in on the narrated
  word, thin grey wires with small labels, a section title at the top left and a dark caption pill.
- **Brand:** MCP Keynote's own, from `docs/assets/brand/`, unchanged: sky #8EC9FF, navy #0B1E3F,
  blue #2F64B0. Brand blue marks the server's own code, system indigo is Keynote and what it draws,
  grey is plumbing, teal the MCP client, green only status dots, red only the two rejected keys, and
  navy the big numerals and the wordmark. The upstream logo (`assets/logo.png`) and Apple's Keynote
  icon are not used.
- **Type:** SF Pro, the system face, throughout; code words, the JSON and the AppleScript lines are
  set in the same sans. No monospace and no em dashes on screen. Icons: the HIG Native line glyphs
  (`scripts/vendor/hig-icons.js`, written into `index.html` by `scripts/build-icons.mjs`).
- **Motion:** calm: cards pop in (0.6 s, `back.out`), skeletons light on their word, wires draw,
  the camera glides 1.1 to 1.5 s and never during a key word, scenes crossfade over 0.4 s.

## Sound

- **Voice:** Kokoro-82M, voice af_heart, speed 1.0, 14 lines, each take matching the script word
  for word (mlx-whisper). `narration/lines-tts.json` holds the spellings the voice needs:
  "M.C.P. Keynote", "P.D.F.", "H.T.M.L.", "By Axe", "Easy Chen", "Describe deck" and the numbers in
  words; "AppleScript" is written "Applescript", because "Apple Script" came out as "Apple's script".
- **Music:** "Angel Watching Me" by Arulo (Mixkit 432), relaxed pop and R&B at 105.0 BPM, cut by
  `sound/music.py` on its bar lines (`sound/grid.json`):
  - 0–5.714 s: the end of the track's intro under the hook;
  - 5.714 s: the drop (kick, hats and bass together) on "mcp-keynote";
  - 24.0–28.571 s: two lighter bars from the breakdown under the AppleScript line;
  - 28.571 s: the groove returns on "so a title full of quotes";
  - 60.571 s: the track's own fade-out under the end card.
- **Effects:** 75 cues from six soft Mixkit interface sounds, one vocabulary: a pop when a part
  arrives, a tick for a step or a counter, a whoosh for travel, a sweep for the pull-back, a low pop
  on the two rejected keys, and a riser with a soft hit on the drop. `sfx_events()` in
  `sound/mix.py` places each from the same word cues the scenes use, so its peak lands one frame
  after its picture. The list is in [assets/audio/SOURCE.md](assets/audio/SOURCE.md).
- **Levels:** speech -15.7 LUFS; the music 9.2 dB under it, ducked 4.5 dB more while she speaks;
  each effect 3 to 4 dB over the music around it and at least 4 dB under the voice. Master -16.0
  LUFS, true peak -1.9 dBTP in the mix and -1.8 dBTP in the MP4 after AAC encoding.

## Build

Get the inputs first: `tools/fetch_vendor.sh` for GSAP, then the music and effects listed in
[assets/audio/SOURCE.md](assets/audio/SOURCE.md). The Python steps need numpy, soundfile, scipy,
librosa and mlx-whisper (`<voice-venv>`). The render needs a Mac with SF Pro.

```sh
tools/fetch_vendor.sh
# Voice each line of narration/lines-tts.json with Kokoro-82M (af_heart) at speeds 1.0 and 1.06,
# as narration/takes/<id>.<k>.wav
<voice-venv>/bin/python narration/pick.py takes                   # best take per line, words.json
<voice-venv>/bin/python -I sound/music.py                         # assets/audio/music.wav, sound/grid.json
<voice-venv>/bin/python -I sound/mix.py                           # mix.wav, vo.wav, vo.js, timing.js, sound/timing.json
python3 -I build.py                                               # scene windows, subtitles, the .vtt
npx --yes hyperframes@0.8.173 lint && npx --yes hyperframes@0.8.173 check
npx --yes hyperframes@0.8.173 render -o renders/raw.mp4 --fps 30
ffmpeg -y -i renders/raw.mp4 -i assets/audio/mix.wav -map 0:v -map 1:a -c:v copy -c:a aac -b:a 256k \
  -shortest -movflags +faststart renders/mcp-keynote-v1.mp4
```

The last step puts the exact mix back on the picture, because the renderer's own audio comes out
quieter. The scenes find their cue words by text in `window.VO`, so a re-voiced line re-times the
picture, the captions and the effects together. To move a line, change `SLOTS` in `sound/mix.py`,
then run `mix.py` and `build.py` again.

## The README preview

`docs/assets/readme/mcp-keynote-in-action.webp` is 31.0–47.0 s of the film: the injection title
shown as plain text on Keynote's slide, then the native table, pie and styled lines, the export
chips, and `describe_deck` reading the deck back. 1200 × 676, 15 fps, lossy WebP at quality 90,
looping, 6.3 MB. The board's small grey text stays sharp at this quality, so it was not lowered.

```sh
mkdir -p preview
ffmpeg -v error -ss 31.0 -t 16 -i renders/mcp-keynote-v1.mp4 \
  -vf fps=15,scale=1200:676:flags=lanczos preview/f%03d.png
img2webp -loop 0 -lossy -q 90 -m 6 -d 67 preview/f*.png \
  -o ../../docs/assets/readme/mcp-keynote-in-action.webp
```
