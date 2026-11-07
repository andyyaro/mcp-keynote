"""The mcp-keynote soundtrack: Kokoro af_heart, "Angel Watching Me" (Arulo, Mixkit 432) as a quiet bed, soft effects.

    python3 -I sound/mix.py

Inputs: assets/audio/music.wav (sound/music.py), narration/chosen/<id>.wav + narration/words.json (narration/pick.py),
sound/sfx-src/mixkit-<id>.mp3 (Mixkit free sound effects, same licence as the music).
Outputs:
- assets/audio/mix.wav: the soundtrack, about -16 LUFS, true peak under -1.5 dBTP.
- assets/audio/vo.wav: the voice alone.
- assets/vo.js: window.VO, each line's start/end and word times in film seconds.
- assets/timing.js and sound/timing.json: window.TM, the scene windows (s1-s4) and the board's beats (b1-b7). Every
  scene reads its start from it, and build.py writes the scene windows into index.html.

Levels (Andy: "the sound should not be too loud, just present, the voice should be clear"):
- Speech at -16 LUFS, measured on the spoken stretches only (the lines butted together, no silences).
- The bed 9 dB under the speech (-25 LUFS) and ducked 4.5 dB more while she speaks, so about 13.5 dB under her voice.
- Each effect hits 3-4 dB over the bed as it sits at that moment (K-weighted: the effect's loudest 100 ms against the
  bed's 400 ms around it), stays at least 4 dB under the voice's own level, and its peak lands one frame after its
  picture. mix.py prints every effect's measured level.
- The master is levelled to -16 LUFS integrated and limited to a true peak under -1.5 dBTP.
The effects (sfx_events) mirror the scenes' own tweens, found through the same word cues.
"""
import json, subprocess, sys, tempfile
from pathlib import Path
import numpy as np, soundfile as sf, librosa

ROOT = Path(__file__).resolve().parent.parent
SR = 48000
G = json.loads((ROOT / "sound/grid.json").read_text())
DROP, END_CARD, DUR = G["drop"], G["end_card"], G["duration"]
SPEECH, BED_UNDER, DUCK_DB = -16.0, 9.0, 4.5     # LUFS of the speech; dB the bed sits under it; dB more while she speaks

# each line's clip start in film seconds (the clips carry 0.06 s of room at each end; the speech starts ~0.065 in).
# - v02 "mcp-keynote" lands on the drop: its first word's onset is on the drop's first kick (film 5.734).
# - v06 rides the lighter stretch (breakdown bars 16 and 19); the groove comes back on v07's first word (28.571).
# - The breaths are 0.36-0.82 s between clips (0.48-0.94 s of audible room); the commas inside a thought
#   (v06 > v07, v08 > v09) get the shortest.
# - v13 sits on the overview, and the end card (and v14) on the track's own fade-out from 60.571.
SLOTS = {"v01": 0.75, "v02": DROP + 0.02 - 0.062, "v03": 10.25, "v04": 15.04, "v05": 18.62, "v06": 23.66,
         "v07": 28.45, "v08": 32.06, "v09": 38.22, "v10": 42.62, "v11": 47.83, "v12": 50.8, "v13": 55.54,
         "v14": END_CARD + 0.45}
# scene windows (film seconds). A scene starts where it is fully in and the scene before runs 0.4 s on under it,
# so they crossfade; s2 starts on the drop and s4 on the end-card bar line. The board (s3) is settled on the bar
# line at 10.286, just before "Claude".
SCENES = {"s1": [0, round(DROP + 0.4, 3)], "s2": [DROP, 10.286], "s3": [9.886, round(END_CARD + 0.4, 3)],
          "s4": [END_CARD, DUR]}
# the board's beats inside s3: each starts about 0.35 s before its first line (camera moves sit in the breaths)
BEATS = {"b1": [9.886, 18.27], "b2": [18.27, 23.3], "b3": [23.3, 31.7], "b4": [31.7, 42.26], "b5": [42.26, 47.47],
         "b6": [47.47, 54.9], "b7": [54.9, round(END_CARD + 0.4, 3)]}


def lufs(path):
    out = subprocess.run(["ffmpeg", "-nostats", "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    summ = out[out.rfind("Summary:"):]
    i = float(summ.split("I:")[1].split("LUFS")[0])
    tp = float(summ.split("Peak:")[1].split("dBFS")[0]) if "Peak:" in summ else 0.0
    return i, tp


def to_stereo(y):
    return np.vstack([y, y]) if y.ndim == 1 else y


def load(path, sr=SR):
    y, s = sf.read(path, always_2d=True)
    y = y.T.astype(np.float64)
    if s != sr:
        y = np.vstack([librosa.resample(ch, orig_sr=s, target_sr=sr) for ch in y])
    return y


def main():
    words = json.loads((ROOT / "narration/words.json").read_text())
    music = load(ROOT / "assets/audio/music.wav")
    n = music.shape[1]

    # ---------------------------------------------------------------- the voice
    vo = np.zeros(n)
    meta, prev_end = {}, 0.0
    for key, t0 in SLOTS.items():
        y = load(ROOT / f"narration/chosen/{key}.wav").mean(0)
        if t0 < prev_end + 0.25:
            print(f"warning: {key} starts {prev_end + 0.25 - t0:.2f} s too early", file=sys.stderr)
        a = int(round(t0 * SR)); b = min(n, a + len(y))
        vo[a:b] += y[: b - a]
        end = t0 + len(y) / SR
        meta[key] = {"start": round(t0, 3), "end": round(end, 3), "text": words[key]["text"],
                     "words": [{"w": w["w"], "t0": round(t0 + w["t0"], 3), "t1": round(t0 + w["t1"], 3)} for w in words[key]["words"]]}
        prev_end = end
    tmp = Path(tempfile.mkdtemp())
    sf.write(tmp / "vo_raw.wav", vo.astype(np.float32), SR)
    # Kokoro is clean and bright already: a high-pass, a touch of presence, light de-essing and compression
    chain = ("highpass=f=80,equalizer=f=3000:t=q:w=1.2:g=1.5,equalizer=f=250:t=q:w=1.0:g=-1,"
             "deesser=i=0.2:f=0.5,acompressor=threshold=0.1:ratio=2.5:attack=10:release=150:makeup=1.3")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(tmp / "vo_raw.wav"), "-af", chain, "-ar", str(SR),
                    str(ROOT / "assets/audio/vo.wav")], check=True)
    vo = load(ROOT / "assets/audio/vo.wav").mean(0)[:n]
    vo = np.pad(vo, (0, n - len(vo)))

    # ---------------------------------------------------------------- the bed: quieter, less boom, ducked by the voice
    sf.write(tmp / "m.wav", music.T.astype(np.float32), SR)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(tmp / "m.wav"), "-af",
                    "bass=g=-4:f=110:w=0.7,equalizer=f=2500:t=q:w=1.5:g=-2", str(tmp / "m2.wav")], check=True)
    bed = load(tmp / "m2.wav")
    spoken = lambda x: np.concatenate([x[..., int(m["start"] * SR): int(m["end"] * SR)] for m in meta.values()], -1)
    # measured as it sits in the mix: the mono voice goes to both channels, which BS.1770 counts as +3 dB over the
    # mono file. (secure-data-hub measured the mono file and also boosted by its speaking fraction, so its voice
    # sat ~5 dB further over its bed than its notes say.)
    sf.write(tmp / "v.wav", spoken(np.vstack([vo, vo])).T.astype(np.float32), SR)
    vi_speech, _ = lufs(tmp / "v.wav")           # the lines butted together: speech loudness with no silence in it
    bi, _ = lufs(tmp / "m2.wav")
    vo *= 10 ** ((SPEECH - vi_speech) / 20)
    bed *= 10 ** ((SPEECH - BED_UNDER - bi) / 20)   # the bed 9 dB under the speech before ducking
    # duck: -4.5 dB under the voice, 40 ms attack, 450 ms release (followed at 1 kHz, then interpolated)
    hop = SR // 1000
    env = np.sqrt(np.convolve(vo ** 2, np.ones(int(0.05 * SR)) / int(0.05 * SR), "same"))[::hop]
    on = (env > 10 ** (-45 / 20)).astype(float)
    g = np.empty(len(on)); state = 0.0
    att, rel = 1 - np.exp(-1 / (0.04 * 1000)), 1 - np.exp(-1 / (0.45 * 1000))
    for i, target in enumerate(on):
        state += (att if target > state else rel) * (target - state)
        g[i] = state
    g = np.interp(np.arange(n), np.arange(len(g)) * hop, g)
    duck = 10 ** (-DUCK_DB * g / 20)
    bed *= duck

    # ---------------------------------------------------------------- effects
    # Each effect is levelled against the bed as it sits at that moment (after ducking): its loudest 100 ms
    # (K-weighted) lands `over` dB above the bed's K-weighted level in the 400 ms around its peak, and at least 4 dB
    # under the voice's own level (K-weighted, over the spoken stretches). Its peak lands one frame after its picture.
    sfx = np.zeros((2, n))
    TMd = {"drop": DROP, "end_card": END_CARD, **SCENES, **BEATS}
    W = word_finder(meta)
    events = sfx_events(W, TMd, meta)
    bed_p, vo_p = kpower(bed), kpower(np.vstack([vo, vo]))
    speech_db = 10 * np.log10(np.mean(np.concatenate([vo_p[int(m["start"] * SR): int(m["end"] * SR)] for m in meta.values()])))
    report = []
    for t, name, over, pitch in sorted(events):
        report.append((t, name, pitch, over, place(sfx, name, t, over, pitch, bed_p, speech_db)))
    sfx_p = kpower(sfx)

    # ---------------------------------------------------------------- sum, level, limit
    mix = bed + sfx + np.vstack([vo, vo])
    sf.write(tmp / "mix.wav", mix.T.astype(np.float32), SR)
    mi, _ = lufs(tmp / "mix.wav")
    mix *= 10 ** ((-16 - mi) / 20)
    sf.write(tmp / "mix2.wav", mix.T.astype(np.float32), SR)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(tmp / "mix2.wav"), "-af", "alimiter=limit=0.79:attack=3:release=60:level=disabled",
                    "-ar", str(SR), str(ROOT / "assets/audio/mix.wav")], check=True)
    fi, tp = lufs(ROOT / "assets/audio/mix.wav")

    # ---------------------------------------------------------------- the levels as heard in the final mix
    k = 10 ** ((-16 - mi) / 20)                   # the master gain (the limiter only touches peaks)
    cut = lambda x, spans: np.concatenate([x[..., int(a * SR): int(b * SR)] for a, b in spans], -1)
    stats = {}
    for name, x, spans in [("speech", np.vstack([vo, vo]) * k, [(m["start"], m["end"]) for m in meta.values()]),
                           ("bed_under_speech", bed * k, [(m["start"], m["end"]) for m in meta.values()]),
                           ("bed_undocked_ref", bed / duck * k, [(m["start"], m["end"]) for m in meta.values()]),
                           ("bed_whole_film_undocked", bed / duck * k, [(0.0, DUR)])]:
        sf.write(tmp / "s.wav", cut(x, spans).T.astype(np.float32), SR)
        stats[name] = round(lufs(tmp / "s.wav")[0], 1)

    (ROOT / "assets/vo.js").write_text("window.VO = " + json.dumps(meta) + ";\n")
    tm = {"drop": DROP, "groove_back": G["groove_back"], "end_card": END_CARD, "track_ending": G["track_ending"],
          "duration": DUR, "bpm": G["bpm"], "bar": G["bar"], "film_bars": G["film_bars"], **SCENES, **BEATS,
          "levels": {"master_lufs": round(fi, 1), "true_peak_dbtp": round(tp, 1), **stats}}
    (ROOT / "assets/timing.js").write_text("window.TM = " + json.dumps(tm) + ";\n")
    (ROOT / "sound/timing.json").write_text(json.dumps(tm, indent=1))
    # the effects as placed, measured on the summed effects track (so overlapping effects count together)
    # (alone: the effect by itself; sum: every effect sounding in that 100 ms, under the voice's level)
    print("effects (film s of the picture, sound, pitch: dB over the bed alone [target]; all effects there, dB under the voice):")
    worst_over, worst_vo = [], []
    for t, name, pitch, over, alone in report:
        fx = win_db(sfx_p, t + 1 / 30, 0.1, peak=True)
        worst_over.append(alone); worst_vo.append(speech_db - fx)
        print(f"  {t:6.2f} {name:11s} {pitch:4.2f}: {alone:+5.1f} [+{over}], {speech_db - fx:4.1f} under the voice")
    print(f"effects over the bed: {min(worst_over):+.1f} to {max(worst_over):+.1f} dB alone; "
          f"the closest the effects come to the voice: {min(worst_vo):.1f} dB under it")
    print(f"mix.wav {DUR} s, {fi:.1f} LUFS, true peak {tp:.1f} dBTP; voice, bed and {len(events)} effects")
    print("lines: " + ", ".join(f"{k} {m['start']:.2f}-{m['end']:.2f}" for k, m in meta.items()))
    print("levels (LUFS, final scale):", stats, f"| bed under speech {stats['speech'] - stats['bed_under_speech']:.1f} dB below the voice,"
          f" {stats['speech'] - stats['bed_undocked_ref']:.1f} dB before ducking")


def word_finder(meta):
    norm = lambda s: "".join(c for c in s.lower() if c.isalnum())
    def W(k, w, nth=0):
        alts = w.split("|")
        ws = meta[k]["words"]
        for exact in (True, False):
            c = 0
            for x in ws:
                t = norm(x["w"])
                if any((t == a) if exact else t.startswith(a) for a in alts):
                    if c == nth: return x["t0"]
                    c += 1
        print(f"warning: no word {w!r} in {k}", file=sys.stderr)
        return meta[k]["start"]
    return W


SFX = {  # secure-data-hub's soft Mixkit set (sound/sfx-src): one vocabulary for the whole series
    "whoosh_wind": "mixkit-1465.mp3", "whoosh_air": "mixkit-1492.mp3", "sweep": "mixkit-3115.mp3",
    "tick": "mixkit-1120.mp3", "pop": "mixkit-2357.mp3", "pop_hard": "mixkit-3005.mp3",
    "typing": "mixkit-2538.mp3", "riser": "mixkit-2408.mp3",
}
_cache = {}

# BS.1770 K-weighting at 48 kHz (the pre-filter shelf, then the RLB high-pass): loudness-like levels, so a bright
# pop and the bass-heavy bed are compared the way they are heard
_K = [([1.53512485958697, -2.69169618940638, 1.19839281085285], [1.0, -1.69065929318241, 0.73248077421585]),
      ([1.0, -2.0, 1.0], [1.0, -1.99004745483398, 0.99007225036621])]


def kpower(x):
    """K-weighted power, summed over the channels (BS.1770), one value per sample."""
    from scipy.signal import lfilter
    x = np.atleast_2d(x)
    p = np.zeros(x.shape[1])
    for ch in x:
        for b, a in _K:
            ch = lfilter(b, a, ch)
        p += ch ** 2
    return p


def win_db(p, center, w, peak=False):
    """Level in dB of a K-weighted power track: the mean over w seconds around `center`, or with peak=True the
    loudest 100 ms window starting within 0.15 s of it."""
    if not peak:
        a, b = max(0, int((center - w / 2) * SR)), min(len(p), int((center + w / 2) * SR))
        return 10 * np.log10(np.mean(p[a:b]) + 1e-15)
    a, b = max(0, int((center - 0.15) * SR)), min(len(p), int((center + 0.15) * SR))
    m = int(0.1 * SR)
    c = np.concatenate([[0.0], np.cumsum(p[max(0, a - m // 2): b + m])])
    return 10 * np.log10(np.max(c[m:] - c[:-m]) / m + 1e-15)


def clip(name, pitch):
    """The sound at unit gain: (samples, its peak time in s, the K-weighted level of its loudest 100 ms)."""
    if (name, pitch) not in _cache:
        y = load(ROOT / "sound/sfx-src" / SFX[name])
        if name == "typing":   # a short burst of keys from the middle of the take
            y = y[:, int(1.0 * SR): int(1.75 * SR)]
            f = int(0.03 * SR); y[:, :f] *= np.linspace(0, 1, f); y[:, -f:] *= np.linspace(1, 0, f)
        if name == "riser":    # let it swell in from nothing
            f = int(1.2 * SR); y[:, :f] *= np.linspace(0, 1, f) ** 2
        if pitch != 1.0:       # small pitch steps rotate repeated sounds (resampling also shortens or lengthens them)
            y = np.vstack([librosa.resample(ch, orig_sr=SR, target_sr=int(SR / pitch)) for ch in y])
        peak = np.argmax(np.convolve(np.abs(y).mean(0), np.ones(240) / 240, "same")) / SR
        _cache[(name, pitch)] = (y, peak, win_db(kpower(y), peak, 0.1, peak=True))
    return _cache[(name, pitch)]


def place(out, name, t, over, pitch, bed_p, speech_db):
    """Adds one effect so its peak lands one frame after the picture at film time t, `over` dB above the bed there
    (and never closer than 4 dB to the voice's level). Returns its own peak over the bed, measured as placed."""
    y, peak, lvl = clip(name, pitch)
    pk = t + 1 / 30
    bed_db = win_db(bed_p, pk, 0.4)
    want = min(bed_db + over, speech_db - 4)
    y = y * 10 ** ((want - lvl) / 20)
    a = int(round((pk - peak) * SR))
    s0 = max(0, -a); a = max(0, a)
    b = min(out.shape[1], a + y.shape[1] - s0)
    out[:, a:b] += y[:, s0: s0 + (b - a)]
    alone = np.zeros(out.shape[1]); alone[a:b] = kpower(y[:, s0: s0 + (b - a)])   # this effect by itself, as placed
    return win_db(alone, pk, 0.1, peak=True) - bed_db


def sfx_events(W, TM, meta):
    """(film time of the picture, sound, dB over the bed, pitch). Each time mirrors the scene's own tween
    (compositions/*.html, assets/board.js), found through the same word cues, so a re-timed voice re-times both.
    One vocabulary (secure-data-hub's), quiet and sparse:
      pop         a part arriving: a card lights, a window opens, a slide appears
      tick        a step or a counter: a spec key, a call, a chip or status on the voice, a few thinned count ticks
      whoosh_air  travel: a camera glide (peak about mid-glide), the slides gathering, the argv capsule
      sweep       the pull-back to the whole board
      pop (0.8)   the low pop: a denial or error, only the two rejected keys
      riser + pop_hard  the drop (the mark lands on "mcp-keynote")"""
    e = []
    E = lambda t, name, over=4, pitch=1.0: e.append((round(t, 3), name, over, pitch))
    cam = lambda t0, d: t0 + 0.45 * d            # a glide's whoosh peaks a little before its midpoint (fastest)
    end = lambda k: meta[k]["end"]

    # ---- s1 hook: the cards arrive; one call at a time (4 steps); the count lands on "81"
    E(0.2, "pop", 3, 1.0)
    t20, t81 = W("v01", "20"), W("v01", "81")
    for i, dt in enumerate([-0.05, 0.6, 1.25, 1.9]):
        E(t20 + dt, "tick", 3, (1.0, 1.04, 1.08, 1.12)[i])
    E(t81, "tick", 4, 1.18)
    # the drop: the slides gather (air) into the mark, which lands on the drop's first kick
    E(TM["drop"] - 0.3, "whoosh_air", 3, 1.0)
    E(TM["drop"], "riser", 3, 1.0)
    E(TM["drop"], "pop_hard", 3, 1.0)

    # ---- s2 name: the chip "build_deck · 1 call, not 81"; "1 call" lights
    E(W("v02", "builds") - 0.05, "pop", 3, 1.06)
    E(W("v02", "one", 1) - 0.05, "tick", 3, 1.1)

    # ---- b1: the client and the spec arrive; its keys light on the voice; the server and the spec check light
    E(W("v03", "claude") - 0.1, "pop", 4, 1.0)
    E(W("v03", "writes") + 0.05, "pop", 3, 1.06)
    for i, w in enumerate(["slides", "tables", "charts", "notes", "transitions"]):
        E(W("v03", w), "tick", 3, 1.0 + 0.04 * i)
    E(cam(end("v03") - 0.35, 1.2), "whoosh_air", 4, 1.06)
    E(W("v04", "server"), "pop", 4, 1.0)
    E(W("v04", "checks"), "pop", 4, 1.06)

    # ---- b2: the reply opens; the two rejected keys (low pops); the two fixes light
    E(cam(end("v04") - 0.1, 1.1), "whoosh_air", 4, 1.12)
    E(W("v05", "a") - 0.25, "pop", 4, 1.0)
    E(W("v05", "typo"), "pop", 4, 0.8)
    E(W("v05", "invented"), "pop", 4, 0.78)
    E(W("v05", "named"), "tick", 3, 1.06)
    E(W("v05", "use"), "tick", 3, 1.1)

    # ---- b3: down the pipeline (build_deck, fragments.py, the runner), the runner's window, "never" lights
    t3 = end("v05") + 0.05
    E(cam(t3, 1.2), "whoosh_air", 4, 1.0)
    E(W("v06", "your") - 0.05, "pop", 3, 1.0)
    E(W("v06", "applescript") - 0.1, "pop", 3, 1.06)
    E(W("v06", "arguments"), "pop", 3, 1.12)
    E(W("v06", "arguments") + 0.45, "pop", 4, 1.0)
    E(W("v06", "never"), "tick", 3, 1.06)
    # v07: across to the Mac; the capsule travels the argv wire; Keynote lights; the title shows as plain text
    E(cam(end("v06") - 0.15, 1.1), "whoosh_air", 4, 1.06)
    E(W("v07", "title") + 0.45, "whoosh_air", 4, 1.25)
    E(W("v07", "quotes"), "pop", 4, 1.0)
    E(W("v07", "break") - 0.05, "tick", 3, 1.06)
    E(W("v07", "take"), "tick", 3, 1.12)

    # ---- b4: to the slide strip; the table, its total (35), the pie, the styled lines; the four exports
    E(cam(end("v07") + 0.05, 1.2), "whoosh_air", 4, 1.0)
    E(W("v08", "tables") - 0.3, "pop", 3, 1.0)
    E(W("v08", "formulas") + 0.32, "tick", 3, 1.1)
    E(W("v08", "17") - 0.15, "pop", 3, 1.06)
    E(W("v08", "styled") - 0.1, "pop", 3, 1.12)
    for i, w in enumerate(["pdf", "powerpoint", "movie", "html"]):
        E(W("v09", w) - 0.05, "tick", 3, 1.0 + 0.04 * i)

    # ---- b5: describe_deck lights; the tri-colour title; back to the spec; its three runs light; the Git chip
    E(cam(W("v09", "html") + 0.55, 1.2), "whoosh_air", 4, 1.12)
    E(W("v10", "describe"), "pop", 4, 1.0)
    E(W("v10", "reads") - 0.1, "pop", 3, 1.06)
    E(cam(W("v10", "deck", 1), 1.0), "whoosh_air", 4, 1.06)
    for i in range(3):
        E(W("v10", "spec") + 0.2 + i * 0.25, "tick", 3, 1.0 + 0.05 * i)
    E(W("v10", "diff") - 0.05, "tick", 3, 1.18)

    # ---- b6: 757 lights and counts (three thinned ticks, the last on its landing); then 289 and "none failed"
    E(cam(end("v10") + 0.02, 1.0), "whoosh_air", 4, 1.0)
    E(W("v11", "757") - 0.1, "pop", 4, 1.0)
    for i, dt in enumerate([0.3, 0.65, 1.15]):
        E(W("v11", "757") + dt, "tick", 3, 1.0 + 0.06 * i)
    E(cam(end("v11") - 0.15, 1.1), "whoosh_air", 4, 1.06)
    E(W("v12", "real"), "pop", 4, 1.06)
    for i, dt in enumerate([0.3, 0.8]):
        E(W("v12", "289") + dt, "tick", 3, 1.0 + 0.06 * i)
    E(W("v12", "none"), "tick", 4, 1.18)

    # ---- b7: the pull-back to the whole board; the upstream card; its three names light on the voice
    E(end("v12") - 0.1 + 0.25, "sweep", 4, 1.0)   # the glide starts slowly: the sweep meets it as it gathers speed
    E(W("v13", "rebuilds") - 0.3, "pop", 3, 1.0)
    for i, w in enumerate(["rebuilds", "by", "easy"]):
        E(W("v13", w), "tick", 3, 1.0 + 0.05 * i)

    # ---- s4 end card, on the track's fade-out: the board clears (air), the mark, the wordmark, the two lines
    E(TM["end_card"] - 0.35, "whoosh_air", 4, 1.06)
    E(TM["end_card"] + 0.12, "pop", 4, 0.94)
    E(W("v14", "mcp") - 0.05, "pop", 3, 1.06)
    E(W("v14", "keynote", 1) - 0.1, "tick", 3, 1.0)
    E(W("v14", "built") + 0.1, "tick", 3, 1.06)
    return e


if __name__ == "__main__":
    main()
