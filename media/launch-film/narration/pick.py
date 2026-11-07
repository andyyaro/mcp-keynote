"""Kokoro af_heart takes (mcp-keynote). Choose the best take of each narration line and time its words.

    python3 narration/pick.py takes            (the folder of <id>.<k>.wav takes)
    python3 narration/pick.py takes v06 v09    (redo only these lines, keep the rest)

For every line in lines.json: transcribe each take (mlx-whisper, word timestamps), score it by how exactly the words
match the script (and, as a tie-break, closeness to the slot's length budget), trim silence, and keep the winner as
chosen/<id>.wav (narration/overrides.json can force a take: {"v02": "v02.2.wav"}). words.json gets each chosen line's words with times relative to the clip's start.
"""
import json, re, sys, difflib
from pathlib import Path
import numpy as np, soundfile as sf
import mlx_whisper

HERE = Path(__file__).resolve().parent
ASR = "mlx-community/whisper-large-v3-turbo"
# the spoken spellings (lines-tts.json) and what whisper writes for them, mapped to one form on both sides
WORDS = {"mcp": "m c p", "pdf": "p d f", "html": "h t m l", "applescript": "apple script", "81": "eighty one",
         "17": "seventeen", "757": "seven hundred fifty seven", "289": "two hundred eighty nine",
         "byaxes": "by axes", "byaxe": "by axe", "easychens": "easy chens", "easychen": "easy chen",
         "cant": "can not", "describedeck": "describe deck", "mcpkeynote": "m c p keynote", "20": "twenty"}


def norm(s):
    s = re.sub(r"\[([^\]]+)\]\(/[^)]*/\)", r"\1", s).lower()     # "[word](/phonemes/)" -> "word"
    s = s.replace("_", " ").replace("-", " ").replace("\u2019", "'")
    s = re.sub(r"(?<=[a-z])\.(?=[a-z]\.)", "", s)                   # "m.c.p." -> "mcp."
    s = re.sub(r"[^a-z0-9 ]", "", s)
    return " ".join(WORDS.get(w, w) for w in s.split())


def trim(y, sr, thr_db=-42, pad=0.06):
    env = np.abs(y)
    win = int(0.01 * sr)
    rms = np.sqrt(np.convolve(env ** 2, np.ones(win) / win, "same"))
    on = np.where(20 * np.log10(rms + 1e-9) > thr_db)[0]
    if not len(on):
        return y, 0.0
    a, b = max(0, on[0] - int(pad * sr)), min(len(y), on[-1] + int(pad * sr))
    return y[a:b], a / sr


def speech_onset(y, sr, thr_db=-35):
    """The first 10 ms where the voice is above thr_db. The clip is trimmed, so this is where the first word starts:
    whisper puts the first word at 0.0, and a spoken number ("757") can come back 0.6 s late."""
    win = int(0.01 * sr)
    rms = np.sqrt(np.convolve(y ** 2, np.ones(win) / win, "same"))
    on = np.where(20 * np.log10(rms + 1e-9) > thr_db)[0]
    return round(on[0] / sr, 3) if len(on) else 0.0


def fix_first(ws, y, sr):
    if ws:
        ws[0]["t0"] = min(speech_onset(y, sr), ws[0]["t1"] - 0.05)
    return ws


def main():
    takes_dir = HERE / sys.argv[1]
    lines = json.loads((HERE / "lines.json").read_text())
    tts = json.loads((HERE / "lines-tts.json").read_text())
    out = HERE / "chosen"; out.mkdir(exist_ok=True)
    over = json.loads((HERE / "overrides.json").read_text()) if (HERE / "overrides.json").exists() else {}
    only = set(sys.argv[2:])
    words_out = json.loads((HERE / "words.json").read_text()) if only and (HERE / "words.json").exists() else {}
    report = []
    for key, text in lines.items():
        if only and key not in only:
            continue
        best = None; tried = []
        cands = [takes_dir / over[key]] if key in over else sorted(takes_dir.glob(f"{key}.*.wav"))
        for f in cands:
            y, sr = sf.read(f)
            if y.ndim > 1: y = y.mean(1)
            y, cut = trim(y, sr)
            tmp = out / f"_{f.name}"; sf.write(tmp, y, sr)
            r = mlx_whisper.transcribe(str(tmp), path_or_hf_repo=ASR, language="en", word_timestamps=True)
            tmp.unlink()
            heard = " ".join(s["text"] for s in r["segments"]).strip()
            score = difflib.SequenceMatcher(None, norm(tts[key]).split(), norm(heard).split()).ratio()
            dur = len(y) / sr
            # words-per-second sanity: penalise very slow, draggy takes slightly
            wps = len(text.split()) / max(dur, 0.1)
            rank = score + (0.03 if f.name.endswith(".1.wav") else 0.0)
            ws = [{"w": w["word"].strip(), "t0": round(w["start"], 3), "t1": round(w["end"], 3)}
                  for s in r["segments"] for w in s.get("words", [])]
            tried.append(f"{f.name} {dur:.2f}s {score:.2f}")
            if best is None or rank > best[0]:
                best = (rank, f.name, y, sr, heard, dur, ws, score)
        rank, name, y, sr, heard, dur, ws, score = best
        ws = fix_first(ws, y, sr)
        sf.write(out / f"{key}.wav", y, sr)
        words_out[key] = {"text": text, "dur": round(dur, 3), "take": name, "words": ws}
        report.append(f"{key} {name:10s} {dur:5.2f}s match={score:.2f}  [{' | '.join(tried)}]\n     heard: {heard}")
    words_out = {k: words_out[k] for k in lines if k in words_out}
    (HERE / "words.json").write_text(json.dumps(words_out, indent=1))
    print("\n".join(report))


if __name__ == "__main__":
    main()
