"""Cut "Angel Watching Me" (Arulo, Mixkit 432, Mixkit Stock Music Free License) to the mcp-keynote film.

    python3 -I sound/music.py     # -> assets/audio/music.wav, sound/grid.json

The grid (measured on sound/track.mp3 with librosa, 2026-11-01):
- 105.0 BPM: beat 0.571430 s, bar 2.285719 s (4 beats). The kick onsets fit that grid to 3.3 ms over 90 hits.
  librosa's own tempo guess (103.4) is a quantised bin, and its beat tracker locks onto the off-beat; the kick
  onsets are the truth.
- The groove's downbeat (kick) is at 18.247 s, and track bar n starts at 18.247 + (n - 8) * 2.285719 s.
  Bar 0 is at -0.039, so the track opens on a bar line. The kick plays beats 1, 2 and 3 of every groove bar.
- The phrases are 2 bars long (the odd bars are about 2 dB fuller), so every join keeps the bar's parity.
Structure (RMS and band energy per bar):
  bars  0-7   (0-18.25)      the intro: keys only, no kick or hats. Bar 7 swells into the drop
  bar   8     (18.25)        THE DROP: kick, hats and bass enter together
  bars  8-15  (18.25-36.51)  groove A
  bars 16-19  (36.51-45.66)  breakdown: kick and bass out, the hats carry on. Bar 19 brings the bass back in
  bars 20-39  (45.66-91.37)  full groove
  bars 40-43  (91.37-99.5)   the track's own fade-out (about -2 dB a beat), silence by 100.5

The edit (joins on bar lines, 20 ms before each downbeat's onset, 12 ms crossfades):
  film  0.000- 5.714  track 12.513-18.227  the end of the intro under the hook, from a beat, faded in over 0.3 s
  film  5.714-24.000  track 18.227-36.513  THE DROP on "mcp-keynote"; groove A, all 8 bars
  film 24.000-26.286  track 36.513-38.799  breakdown bar 16 (the track's own way out of the groove)
  film 26.286-60.571  track 43.370-77.656  breakdown bar 19 (bars 17-18 cut), then the groove returns on bar 20
                                           (film 28.571), on "so a title full of quotes"
  film 60.571-66.600  track 91.370-...     the end card on bar 40, the track's own fade-out, plus 2.5 s of fade
"""
import json, subprocess
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
TRACK = ROOT / "sound/track.mp3"
SR = 48000
BEAT = 0.571430
BAR = 4 * BEAT
ONSET8 = 18.247                      # the drop's first kick (onset peak)
PRE = 0.020                          # cut this far ahead of each downbeat's onset, so the attack stays whole
tb = lambda n: ONSET8 + (n - 8) * BAR - PRE       # cut point of track bar n
DROP = 5.714                         # film time of the drop (10 beats of intro under the hook)
A0 = tb(8) - DROP                    # the film opens on a beat of intro bar 5
f_bar = lambda k: DROP + k * BAR     # film bar lines, counted from the drop
SEGMENTS = [                         # (film start, track start)
    (0.0, A0),
    (DROP, tb(8)),                   # groove A, bars 8-15
    (f_bar(8), tb(16)),              # breakdown bar 16
    (f_bar(9), tb(19)),              # breakdown bar 19, then the groove from bar 20
    (f_bar(24), tb(40)),             # the end card on the fade-out
]
GROOVE_BACK = f_bar(10)              # bar 20 under film 28.571
END_CARD = f_bar(24)
FILM_END = 66.6                      # 1998 frames at 30 fps
XF = 0.012


def main():
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(TRACK), "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"],
                         capture_output=True, check=True).stdout
    track = np.frombuffer(raw, np.float32).reshape(-1, 2).T.astype(np.float64)
    n = int(round(FILM_END * SR))
    out = np.zeros((2, n))
    x = int(XF * SR); ramp = np.linspace(0, 1, x)
    for k, (f0s, t0s) in enumerate(SEGMENTS):
        f0 = int(round(f0s * SR)); f1 = int(round(SEGMENTS[k + 1][0] * SR)) if k + 1 < len(SEGMENTS) else n
        t0 = int(round(t0s * SR))
        seg = track[:, t0: t0 + (f1 - f0)]
        seg = np.pad(seg, ((0, 0), (0, (f1 - f0) - seg.shape[1])))
        if k > 0:
            out[:, f0 - x: f0] = out[:, f0 - x: f0] * (1 - ramp) + track[:, t0 - x: t0] * ramp
        out[:, f0:f1] = seg
    fi = int(0.3 * SR); out[:, :fi] *= np.linspace(0, 1, fi)
    fo = int(2.5 * SR); out[:, -fo:] *= np.linspace(1, 0, fo) ** 1.5
    import soundfile as sf
    (ROOT / "assets/audio").mkdir(parents=True, exist_ok=True)
    sf.write(ROOT / "assets/audio/music.wav", out.T.astype(np.float32), SR)
    r3 = lambda v: round(v, 3)
    grid = {"track": "Angel Watching Me (Arulo, Mixkit 432)", "bpm": 105.0, "beat": BEAT, "bar": r3(BAR),
            "track_bar0": r3(ONSET8 - 8 * BAR), "drop": r3(DROP), "groove_back": r3(GROOVE_BACK),
            "end_card": r3(END_CARD), "track_ending": r3(END_CARD), "duration": FILM_END,
            "film_bars": [r3(f_bar(k)) for k in range(-2, 27) if 0 <= f_bar(k) <= FILM_END],
            "segments": [[r3(f), r3(t)] for f, t in SEGMENTS],
            "segments_note": "[film start, track start]; track bars: intro 5.5-7, groove 8-15, breakdown 16 and 19, "
                             "groove 20-33, fade-out 40-"}
    (ROOT / "sound/grid.json").write_text(json.dumps(grid, indent=1))
    print(f"music.wav {FILM_END} s; drop {DROP:.3f}, groove back {GROOVE_BACK:.3f}, end card {END_CARD:.3f}")
    print("segments (film, track):", ", ".join(f"{f:.3f}<-{t:.3f}" for f, t in SEGMENTS))


if __name__ == "__main__":
    main()
