# MCP Keynote launch film

The 67-second film at the top of the [repository README](../../README.md), published at
https://andyyaro.github.io/mcp-keynote/film.html. It starts with the problem: a 20-slide deck built
one element at a time takes 81 tool calls. Then the name lands on the music's drop, and the camera
glides across one architecture board: the spec, checked before anything is created; the real
validation reply; text passed to AppleScript as arguments; the native tables, charts and styled
connectors Keynote draws, and the exports; `describe_deck` reading a deck back into the same spec;
and the proof, 757 unit tests and 289 live checks. It ends by crediting the project this one
rebuilds: ByAxe's keynote-mcp, a fork of easychen's original.

The project has no interface of its own, so the film is an architecture board, not a screen
recording. The validation reply and the AppleScript lines on it are real outputs, captured from the
code with `osascript` mocked. The slide thumbnails are redrawn in HTML from specs in the repository,
because the repository holds no slide screenshots and Keynote was not driven for the film.

[STORYBOARD.md](STORYBOARD.md) has the scenes, the look, the sound and every build step.
[FACTS.md](FACTS.md) has every claim in the film and where it comes from, and
[SPEC.md](SPEC.md) is the brief the film was built from: every shot, number and timing.

## What is here

| Path | What it is |
|---|---|
| `index.html`, `compositions/` | The composition (HyperFrames 0.8.173, GSAP): four scenes (the hook, the name, the architecture board, the end card), plus the burned-in subtitles and the icon sprite in `index.html` |
| `assets/board.js` | The board's parts, wires and motion helpers; its timeline is `compositions/s3-board.html` |
| `assets/vo.js`, `assets/timing.js` | The narration's word times (`window.VO`) and the scene windows, beats and drop (`window.TM`), written by `sound/mix.py`; the scenes find their cues in them |
| `build.py` | Writes the scene windows and subtitles into the composition, and the captions file |
| `sound/` | The music edit (`music.py`), the mix (`mix.py`: narration, music and 75 effects, each cued to its picture), the bar grid (`grid.json`) and the timing (`timing.json`) |
| `narration/` | The script (`lines.json`), the script as voiced (`lines-tts.json`), `pick.py`, which chooses the best take of each line and times its words, and the word times (`words.json`) |
| `SPEC.md` | The brief: goal, sound, look, motion, every shot and the board's parts |
| `FACTS.md` | Every line of narration and every on-screen claim, with its source |
| `scripts/` | The HIG Native line icons and the script that writes them into `index.html` |
| `tools/fetch_vendor.sh` | Fetches GSAP at the pinned version and checks the file's SHA-256 |
| `deploy/film.html`, `deploy/index.html` | The watch page, and a redirect to it from the site's root |
| `assets/brand/wordmark-navy.svg` | The navy wordmark, cut from the repository's `docs/assets/brand/lockup/lockup-color.svg`; the mark is drawn inline from `docs/assets/brand/icons/icon-rounded.svg` |
| `assets/audio/SOURCE.md` | Every third-party sound and typeface in the film, with its licence and where it goes |
| `hyperframes.json`, `package.json` | The HyperFrames project settings and the render scripts |

## What is not here, and why

The working folder for the film is about 65 MB. This folder keeps the source and leaves out
everything that is generated or that its licence does not let us hand on by itself:

- **Generated:** the narration takes and the chosen lines, the music edit, the mix, the voice on
  its own, the render and its captions file. The build steps make them again.
- **Screen recordings:** there are none. Nothing in the film was recorded from a screen; the board
  and the slide thumbnails are drawn in HTML.
- **Third-party media:** the music ("Angel Watching Me" by Arulo, Mixkit) and six Mixkit sound
  effects. [assets/audio/SOURCE.md](assets/audio/SOURCE.md) lists each one with its licence and the
  path it goes to.
- **Libraries and fonts:** GSAP 3.14.2 is fetched by `tools/fetch_vendor.sh`. All text is SF Pro,
  the Mac's system font, loaded with `local()`, so no font file is used or shipped and the film
  renders only on a Mac. The wordmark's typeface is already converted to outlines in the SVG.

## Publishing

The MP4, its captions and its poster are assets of the
[`film-v1` release](https://github.com/andyyaro/mcp-keynote/releases/tag/film-v1), so the 18.9 MB
film is not in the repository's history. The
[film page workflow](../../.github/workflows/film.yml) puts them on GitHub Pages with
`deploy/film.html`, `deploy/index.html`, the white lockup and the favicon from
`docs/assets/brand/`. It runs when anything in `deploy/` changes on `master`. After replacing a release asset, run it by hand:

```sh
gh release upload film-v1 mcp-keynote-launch.mp4 --clobber
gh workflow run film.yml
```

## Credits

The project: MCP Keynote began as [keynote-mcp](https://github.com/easychen/keynote-mcp) by
easychen (2025), which [ByAxe](https://github.com/ByAxe/keynote-mcp) translated into English,
packaged for PyPI and extended with the keynote-presentation skill and the build-animation tools.
This repository is Andy Yaro's rebuild on top of ByAxe's fork: 49 commits, 116 files. The film
says so in its last line before the end card.

Narration: Kokoro-82M (Apache-2.0), voice af_heart. Music: "Angel Watching Me" by Arulo (Mixkit).
Sound effects: Mixkit. Type: SF Pro (Apple's system font); the wordmark is Archivo Expanded
ExtraBold (SIL OFL 1.1), as outlines. Icons: HIG Native line glyphs. The mark and wordmark are the
project's own (`docs/assets/brand/`).
