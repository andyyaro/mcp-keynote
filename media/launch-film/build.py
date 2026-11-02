"""Write the scene windows and the burned-in captions into index.html.

    python3 -I build.py

- Scene windows: each scene host's data-start/data-duration and the root duration come from sound/timing.json (made by
  sound/mix.py), the same numbers the scenes read at runtime (window.TM in assets/timing.js), so they never drift apart.
- Captions: the script's own words (narration/lines.json), timed from the voice's word times (assets/vo.js, window.VO),
  chunked as the CERFODES film does (<= 2 lines of <= 42 characters, lead 0.05, tail 0.3, min 1.0 s, bridge 0.7).
  v14 is on the end card as the wordmark and line 1, so it is not captioned (CERFODES' "onscreen" rule).
- Sidecar subtitles: renders/mcp-keynote-v1.en.vtt, the same cues plus v14 (spoken over the end card).
- Icons: run `node scripts/build-icons.mjs` once after changing its USED list (it writes the HF:ICONS sprite).
"""
import html, json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TM = json.loads((ROOT / "sound/timing.json").read_text())
LINES = json.loads((ROOT / "narration/lines.json").read_text())
vo_js = (ROOT / "assets/vo.js").read_text()
VO = json.loads(vo_js[vo_js.index("{"): vo_js.rindex("}") + 1])

# scene host id in index.html -> its window in sound/timing.json (the board s3 draws beats b1-b7 itself, from window.TM)
HOSTS = {"s1-hook": "s1", "s2-name": "s2", "s3-board": "s3", "s4-end": "s4"}
ONSCREEN = {"v14"}  # spoken lines that are already large on screen: not captioned
SUB = dict(max_chars=42, max_lines=2, lead=0.05, tail=0.3, min_dur=1.0, bridge=0.7)
r = lambda x: f"{x:.3f}".rstrip("0").rstrip(".")
norm = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())

# how a written word is heard: whisper's spelling, split into the tokens it writes (checked against every line below)
SPOKEN = {"twenty": ["20"], "byaxes": ["by", "axes"], "easychens": ["easy", "chens"]}


def spoken(word):
    n = norm(word)
    if n in SPOKEN:
        return SPOKEN[n]
    return [norm(p) for p in re.split(r"[-_]", word) if norm(p)]


def timed_words(key):
    """The written words of a line, each with the voice's t0/t1 (film seconds)."""
    heard = VO[key]["words"]
    out, k = [], 0
    for w in LINES[key].split():
        toks = spoken(w)
        got = [norm(x["w"]) for x in heard[k:k + len(toks)]]
        assert got == toks, f"{key}: '{w}' is heard as {got}, expected {toks}"
        out.append({"w": w, "t0": heard[k]["t0"], "t1": heard[k + len(toks) - 1]["t1"]})
        k += len(toks)
    assert k == len(heard), f"{key}: {len(heard) - k} heard words left over"
    return out


def wrap(words):
    text = " ".join(words)
    if len(text) <= SUB["max_chars"]:
        return [text]
    best = None
    for k in range(1, len(words)):
        a, b = " ".join(words[:k]), " ".join(words[k:])
        if len(a) > SUB["max_chars"] or len(b) > SUB["max_chars"]:
            continue
        score = max(len(a), len(b)) - (6 if re.search(r"[,:;.]$", words[k - 1]) else 0)
        if best is None or score < best[0]:
            best = (score, [a, b])
    return best[1] if best and SUB["max_lines"] >= 2 else None


def chunk(words):
    """Dynamic programming over cue boundaries: prefer sentence ends, then commas/colons; avoid tiny cues."""
    n = len(words)
    dp, frm = [0.0] + [float("inf")] * n, [-1] * (n + 1)
    end_cost = lambda w, last: 0 if last or re.search(r"[.?!]$", w) else (1 if re.search(r"[,:;]$", w) else 6)
    for i in range(1, n + 1):
        for j in range(max(0, i - 24), i):
            seg = [x["w"] for x in words[j:i]]
            if not wrap(seg):
                continue
            ln = len(" ".join(seg))
            inner = sum(1 for w in seg[:-1] if re.search(r"[.?!]$", w))
            c = dp[j] + end_cost(seg[-1], i == n) + (4 if ln < 22 else 0) + inner * (1.5 if ln <= 52 else 8) + 1
            if c < dp[i]:
                dp[i], frm[i] = c, j
    out, i = [], n
    while i > 0:
        out.insert(0, words[frm[i]:i])
        i = frm[i]
    return out


def make_cues(keys):
    cues = []
    for key in keys:
        for ws in chunk(timed_words(key)):
            cues.append({"lines": wrap([x["w"] for x in ws]), "start": ws[0]["t0"] - SUB["lead"], "end": ws[-1]["t1"] + SUB["tail"]})
    for i, c in enumerate(cues):
        nx = cues[i + 1] if i + 1 < len(cues) else None
        if c["end"] - c["start"] < SUB["min_dur"]:
            c["end"] = c["start"] + SUB["min_dur"]
        if nx and nx["start"] - c["end"] < SUB["bridge"]:
            c["end"] = nx["start"] - 0.04
        if nx and c["end"] > nx["start"] - 0.04:
            c["end"] = nx["start"] - 0.04
    for c in cues:
        assert "—" not in " ".join(c["lines"]), "em dash in a caption"
    return cues


cues = make_cues([k for k in sorted(LINES) if k not in ONSCREEN])

# the sidecar subtitles: the same cues, plus the end card's spoken line (it is on screen, so not burned in)
ts = lambda x: f"{int(x // 3600):02d}:{int(x % 3600 // 60):02d}:{x % 60:06.3f}"
vtt = "WEBVTT\n\n" + "\n".join(f"{i + 1}\n{ts(c['start'])} --> {ts(min(c['end'], TM['duration']))}\n" + "\n".join(c["lines"]) + "\n"
                              for i, c in enumerate(make_cues(sorted(LINES))))
(ROOT / "renders").mkdir(exist_ok=True)
(ROOT / "renders/mcp-keynote-v1.en.vtt").write_text(vtt)

subs = "\n".join(
    f'        <div id="sub-{i + 1}" class="clip sub subtitle-cue" data-layout-allow-overlap data-start="{r(c["start"])}" data-duration="{r(c["end"] - c["start"])}" '
    f'data-track-index="5">{html.escape(chr(10).join(c["lines"]), quote=False)}</div>'
    for i, c in enumerate(cues))

s = (ROOT / "index.html").read_text()
for host, key in HOSTS.items():
    a, b = TM[key]
    s, n = re.subn(rf'(<div id="{host}"[^>]*?data-start=")[^"]*(" data-duration=")[^"]*(")', rf"\g<1>{r(a)}\g<2>{r(b - a)}\g<3>", s)
    assert n == 1, host
s, n = re.subn(r'(<div id="main"[^>]*?data-duration=")[^"]*(")', rf"\g<1>{r(TM['duration'])}\g<2>", s); assert n == 1
s, n = re.subn(r'(<audio id="soundtrack"[^>]*?data-duration=")[^"]*(")', rf"\g<1>{r(TM['duration'])}\g<2>", s); assert n == 1
s, n = re.subn(r"<!-- HF:SUBS[^>]*-->[\s\S]*?<!-- /HF:SUBS -->",
               lambda m: f"<!-- HF:SUBS (written by build.py from narration/lines.json + assets/vo.js) -->\n{subs}\n        <!-- /HF:SUBS -->", s)
assert n == 1, "HF:SUBS markers"
(ROOT / "index.html").write_text(s)
print("index.html:", ", ".join(f"{k} {TM[k][0]}-{TM[k][1]}" for k in HOSTS.values()), f"| {TM['duration']} s | {len(cues)} captions")
for c in cues:
    print(f"  {c['start']:6.2f}-{c['end']:6.2f}  " + " / ".join(c["lines"]))
