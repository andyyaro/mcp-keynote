# Third-party sounds and type in the film

These are in the film but not in this repository. Their licences cover using them inside a film,
not handing the files on by themselves, so they are listed here instead. Download each one again
to the path shown to rebuild. Each download link below was checked on 2026-11-02: it serves the
same bytes the film was mixed from.

## Music

| Used as | Track | Licence | Put it at |
|---|---|---|---|
| The bed under the whole film, cut on its bar lines by `sound/music.py`: the end of the intro under the hook, the drop on the name, a lighter stretch under the AppleScript line, and the track's own fade-out under the end card | "Angel Watching Me" by Arulo, Mixkit 432 ([MP3](https://assets.mixkit.co/music/432/432.mp3)) | [Mixkit Stock Music Free License](https://mixkit.co/license/#musicFree): free in any project, no credit required, not for use in a music-only track | `sound/track.mp3` |

## Sound effects

All from Mixkit, under the [Mixkit Sound Effects Free License](https://mixkit.co/license/#sfxFree).
The names are the ones `sound/mix.py` uses (`SFX`); each file goes in `sound/sfx-src/` as
`mixkit-<id>.mp3`, and is served at
`https://assets.mixkit.co/active_storage/sfx/<id>/<id>-preview.mp3`.

| Name in `mix.py` | Mixkit id | What it marks |
|---|---|---|
| `pop` | 2357 | A part arriving: a card lights, a window opens, a slide appears; pitched down to 0.8, the two rejected keys in the validation reply |
| `tick` | 1120 | A step or a counter: a spec key, a tool call, a chip or a status word, a few thinned ticks while 81, 757 and 289 count up |
| `whoosh_air` | 1492 | Travel: a camera glide, the slides gathering into the mark, the argv capsule |
| `sweep` | 3115 | The pull-back to the whole board |
| `riser` | 2408 | The swell into the drop |
| `pop_hard` | 3005 | The soft hit on the drop, as the mark lands |

`mix.py` also names `whoosh_wind` (1465) and `typing` (2538). This film does not play them, and
`mix.py` loads a sound only when it is played, so they are not needed.

## Voice

Kokoro-82M ([Apache-2.0](https://huggingface.co/hexgrad/Kokoro-82M)), voice af_heart, run
locally. The lines are `narration/lines-tts.json`; the audio is generated, so it is not kept.

## Type

- **SF Pro**, Apple's system font, for all text. `index.html` loads it from the Mac with
  `local("SF Pro")` as "HostUI"; no font file is used or kept, so the film renders only on a Mac
  with SF Pro installed.
- **Archivo Expanded ExtraBold** ([SIL Open Font License 1.1](https://openfontlicense.org/)) for
  the wordmark. It is already converted to outlines in `assets/brand/wordmark-navy.svg`, so no
  font file is needed.

## Pictures

There are no third-party pictures, models or screen recordings in the film. The slide thumbnails
are drawn in HTML from specs in this repository (`scripts/verify_tools.py`); [FACTS.md](../../FACTS.md)
lists the source line of each one.
