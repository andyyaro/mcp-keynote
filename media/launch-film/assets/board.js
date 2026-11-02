// The board's parts for compositions/s3-board.html, kept here so the composition stays small enough to read.
// window.BOARD.build() fills the board's DOM (cards, wires, the spec's JSON, the redrawn slides, the two windows)
// and returns the card and wire tables the timeline uses. World coordinates are 1920 x 1080 px (the overview).
// Sources (FACTS.md): the spec is scripts/verify_tools.py's build_deck spec (2240-2278, trimmed with …) and its
// PHASE 10 runs spec (1203-1233); the validation reply and the osascript lines are real outputs captured from the code
// with osascript mocked; the slides are REDRAWN from the repo's own specs (no screenshots exist, Keynote is not driven).
// No monospace anywhere: code words and JSON are set in the system sans.
(function () {
  // the redrawn Keynote slides on the canvas (one shows at a time)
  const CANVAS = `
<!-- the unit test's adversarial title (tests/unit/test_injection.py ADVERSARIAL), as plain title text -->
<div id="cv-adv" class="cv" style="display:flex; align-items:center; justify-content:center">
  <div style="font-size:31px; line-height:38px; font-weight:600; white-space:pre">"; do shell script "true"; "</div>
</div>
<!-- native table with a live formula: verify_tools.py:1806-1809 (Keynote computed 35) -->
<div id="cv-tab" class="cv">
  <div class="tb">
    <div class="tr th"><span>Team</span><span>Now</span><span>Plan</span></div>
    <div class="tr"><span>Eng</span><span>24</span><span>30</span></div>
    <div class="tr alt"><span>Sales</span><span>11</span><span>14</span></div>
    <div class="tr tt"><span>Total</span><span class="f"><i id="cv-hl"></i><b id="cv-f">=SUM(B2:B3)</b><b id="cv-35">35</b></span><span class="fx">=SUM(C2:C3)</span></div>
  </div>
</div>
<!-- native pie: verify_tools.py:1857-1864, North/South/West 30/45/25 -->
<div id="cv-pie" class="cv">
  <svg width="498" height="280" viewBox="0 0 498 280">
    <g transform="translate(170 140)">
      <path d="M0 0 L0 -100 A100 100 0 0 1 95.1 30.9 Z" fill="#2F64B0" />
      <path d="M0 0 L95.1 30.9 A100 100 0 0 1 -95.1 30.9 Z" fill="#8EC9FF" />
      <path d="M0 0 L-95.1 30.9 A100 100 0 0 1 0 -100 Z" fill="#0B1E3F" />
    </g>
    <g font-family="HostUI, -apple-system, sans-serif" font-size="21" fill="#000">
      <rect x="312" y="84" width="16" height="16" rx="4" fill="#2F64B0" /><text x="338" y="99">North</text><text x="440" y="99" text-anchor="end" font-weight="600">30</text>
      <rect x="312" y="128" width="16" height="16" rx="4" fill="#8EC9FF" /><text x="338" y="143">South</text><text x="440" y="143" text-anchor="end" font-weight="600">45</text>
      <rect x="312" y="172" width="16" height="16" rx="4" fill="#0B1E3F" /><text x="338" y="187">West</text><text x="440" y="187" text-anchor="end" font-weight="600">25</text>
    </g>
  </svg>
</div>
<!-- styled connectors: verify_tools.py:244-283 (phase9), drawn at the slide's own proportions -->
<div id="cv-lin" class="cv">
  <svg width="498" height="280" viewBox="0 0 1920 1080">
    <rect x="100" y="100" width="500" height="300" rx="16" fill="#EFA3A0" />
    <path d="M100 600H900" stroke="#8E1F55" stroke-width="12" stroke-linecap="round" />
    <path d="M100 750H900" stroke="#000000" stroke-width="12" stroke-linecap="round" stroke-dasharray="0 26" />
    <path d="M100 900H866" stroke="#EFA3A0" stroke-width="12" stroke-dasharray="40 26" />
    <path d="M906 900L862 876L862 924Z" fill="#EFA3A0" />
  </svg>
</div>
<!-- runs: verify_tools.py:1203-1233 (PHASE 10), the tri-colour title -->
<div id="cv-run" class="cv" style="display:flex; align-items:center; padding-left:44px">
  <div style="font-size:26px; line-height:32px; font-weight:700; white-space:nowrap">
    <span style="color:#000000">Building A</span> <span style="color:#830041">Secure</span> <span style="color:#F09490">Client Data Hub</span>
  </div>
</div>`;

  const VAL = `
<!-- the real validation reply, captured from build_deck with osascript mocked (FACTS.md, output 1) -->
<div id="b-val" class="win" data-layout-allow-overlap>
  <div class="win-h">
    <div class="tile" style="background:var(--brand-blue)"><svg class="ic"><use href="#ic-checkmark-circle" /></svg></div>
    <div class="tx"><div class="t">build_deck replies</div><div class="s">the real reply, captured from the code with osascript mocked</div></div>
  </div>
  <div class="vh" style="margin-top:14px">Spec validation failed (4 problem(s)); nothing was created:</div>
  <div class="vr" id="vr1"><span class="vi"><svg class="ic"><use href="#ic-xmark-circle-fill" /></svg></span>
    <span><span class="bad">slides[0].layuot</span>: unknown key for a slide. <span class="fix" id="fx1">Did you mean 'layout'?</span></span></div>
  <div class="vr dim"><span class="vi"><i></i></span>
    <span>slides[0]: a slide accepts: body, elements, layout, notes, skipped, title, transition. Nothing was created.</span></div>
  <div class="vr" id="vr3"><span class="vi"><svg class="ic"><use href="#ic-xmark-circle-fill" /></svg></span>
    <span><span class="bad">slides[0].elements[0].fill_color</span>: unknown key for an element of type 'title'. Not a capability of Keynote's AppleScript (shape/text fill color is not writable by AppleScript). <span class="fix" id="fx3">Use add_colored_panel (rendered PNG, exact color) or set_element_opacity.</span></span></div>
  <div class="vr dim"><span class="vi"><i></i></span>
    <span>slides[0].elements[0]: an element of type 'title' accepts: centered, color, column, font_name, font_size, height, index, module, role, runs, text, type, width, x, y, zone. Nothing was created.</span></div>
  <div class="st" id="b-val-st"><i class="dot ci"></i><span>0 AppleScript calls</span></div>
</div>`;

  const OSA = `
<!-- what osascript receives for add_title with the unit test's adversarial title (FACTS.md, output 2) -->
<div id="b-osa" class="win" data-layout-allow-overlap>
  <div class="win-h">
    <div class="tile" style="background:var(--system-gray)"><svg class="ic"><use href="#ic-lock" /></svg></div>
    <div class="tx"><div class="t">What osascript receives</div><div class="s">add_title with a test title, captured from the code</div></div>
  </div>
  <div class="ol">the script</div>
  <div class="oc">on run argv</div>
  <div class="oc"><span class="in">set docName to item 1 of argv</span></div>
  <div class="oc"><span class="in">…</span></div>
  <div class="oc"><span class="in">make new text item with properties {object text:<span class="ref" id="b-ref">(item 2 of argv)</span>}</span></div>
  <div class="ol">argv, item 2</div>
  <div id="b-pay">"; do shell script "true"; "</div>
  <div class="st" id="b-osa-st"><i class="dot ci"></i><span>the title is never in the script</span></div>
</div>`;

  window.BOARD = {
    build() {
      document.getElementById("b-canvas").innerHTML = CANVAS;
      const val = document.getElementById("b-val"), osa = document.getElementById("b-osa");
      val.outerHTML = VAL;
      osa.outerHTML = OSA;
      const wires = document.getElementById("b-wires");

        // ---- cards (world px). Tiles: brand blue = mcp-keynote's own code, indigo = Keynote and what it draws,
        // gray = plumbing, teal = the MCP client. Status is always dot + word: green verified live, blue tested in CI.
        const CARDS = [
          { id: "client", x: 40, y: 150, w: 370, h: 124, hue: "var(--system-teal)", ic: "person-crop-circle", t: "MCP client",
            chips: ["Claude Code", "Claude Desktop", "any MCP client"] },
          { id: "server", x: 496, y: 162, w: 370, h: 124, hue: "var(--brand-blue)", ic: "list-bullet", t: "server.py",
            s: "MCP stdio server · tool routing", st: "live", sw: "58 tools" },
          { id: "check", x: 898, y: 162, w: 370, h: 124, hue: "var(--brand-blue)", ic: "checkmark-circle", t: "Spec check",
            s: "the whole spec, before anything is created" },
          { id: "styles", x: 496, y: 302, w: 370, h: 124, hue: "var(--system-gray)", ic: "square-grid-2x2", t: "Styles",
            s: "plain, boardroom, midnight, editorial, sdh" },
          { id: "build", x: 898, y: 302, w: 370, h: 124, hue: "var(--brand-blue)", ic: "square-3-layers-3d-top-filled", t: "build_deck",
            s: "the whole deck in one call, 5\u00a0slides per AppleScript session" },
          { id: "png", x: 496, y: 442, w: 370, h: 124, hue: "var(--system-gray)", ic: "photo", t: "Rendered PNGs",
            s: "panels and styled_line strokes, exact colour" },
          { id: "frag", x: 898, y: 442, w: 370, h: 124, hue: "var(--brand-blue)", ic: "document-on-document", t: "fragments.py",
            s: "one source for every element's AppleScript" },
          { id: "desc", x: 496, y: 582, w: 370, h: 124, hue: "var(--brand-blue)", ic: "arrow-uturn-backward", t: "describe_deck",
            s: "reads a deck back into its spec", st: "live", sw: "runs survive the rebuild" },
          { id: "runner", x: 898, y: 582, w: 370, h: 124, hue: "var(--system-gray)", ic: "lock", t: "osascript runner",
            s: "your text as argv, never in the script", st: "ci", sw: "108 injection tests" },
          { id: "keynote", x: 1330, y: 582, w: 530, h: 124, hue: "var(--system-indigo)", ic: "play-fill", t: "Keynote 14.5",
            s: "driven through its AppleScript dictionary", st: "live", sw: "verified live" },
          { id: "t757", x: 474, y: 772, w: 300, h: 124, hue: "var(--system-gray)", ic: "checkmark-circle-fill", num: "757", t: "unit tests",
            s: "pytest, in CI on macOS", st: "ci", sw: "passing" },
          { id: "t289", x: 794, y: 772, w: 360, h: 124, hue: "var(--system-indigo)", ic: "flag", num: "289", t: "live checks",
            s: "verify_tools.py · Keynote 14.5", st: "live", sw: "0 failed" },
        ];
        const anchor = document.getElementById("b-wires");
        for (const c of CARDS) {
          const el = document.createElement("div");
          el.className = "card";
          el.id = "c-" + c.id;
          el.style.cssText = `left:${c.x}px; top:${c.y}px; width:${c.w}px; height:${c.h}px`;
          const title = c.num ? `<div class="t"><span class="num" id="n-${c.id}">${c.num}</span> ${c.t}</div>` : `<div class="t">${c.t}</div>`;
          const chips = c.chips ? `<div class="b-chips" id="c-${c.id}-chips">${c.chips.map((x) => `<span class="chip">${x}</span>`).join("")}</div>` : "";
          const st = c.st ? `<div class="st" id="c-${c.id}-st"><i class="dot ${c.st}"></i><span>${c.sw}</span></div>` : "";
          el.innerHTML = `<div class="tile" style="background:${c.hue}; --knock:${c.hue}"><svg class="ic"><use href="#ic-${c.ic}"/></svg></div>` +
            `<div class="tx">${title}${c.s ? `<div class="s">${c.s}</div>` : ""}${chips}${st}</div>`;
          anchor.parentNode.insertBefore(el, anchor.nextSibling);
        }

        // ---- the spec window's JSON (sans). b-j1: the harness's build spec; b-j2: PHASE 10's title with runs.
        const k = (s) => `<span class="k">"${s}"</span>`, p = (s) => `<span class="p">${s}</span>`;
        const J1 = [
          [0, `${p("{")}${k("style")}${p(":")} "boardroom"${p(",")}`],
          [1, `${k("slides")}${p(": [")}`, "slides"],
          [2, `${p("{")}${k("elements")}${p(": [ … ],")}`],
          [3, `${k("notes")}${p(":")} "deck notes ünïcode"${p(",")}`, "notes"],
          [3, `${k("transition")}${p(": {")}`, "transition"],
          [4, `${k("effect")}${p(":")} "dissolve"${p(",")}`],
          [4, `${k("duration")}${p(":")} 0.7${p("}},")}`],
          [2, `${p("{")}${k("elements")}${p(": [")}`],
          [3, `${p("{")}${k("type")}${p(":")} "table"${p(", … },")}`, "table"],
          [3, `${p("{")}${k("type")}${p(":")} "chart"${p(",")}`, "chart"],
          [4, `${k("chart_type")}${p(":")} "pie"${p(", … }]},")}`],
          [2, `${p("{")}${k("elements")}${p(": [")}`],
          [3, `${p("{")}${k("type")}${p(":")} "panel"${p(", … },")}`],
          [3, `${p("{")}${k("type")}${p(":")} "bullets"${p(", … }, … ],")}`],
          [3, `${k("skipped")}${p(":")} true${p("}]}")}`],
        ];
        const J2 = [
          [0, `${p("{")}${k("slides")}${p(": [")}`],
          [1, `${p("{")}${k("layout")}${p(":")} "Blank"${p(",")}`],
          [2, `${k("elements")}${p(": [")}`],
          [3, `${p("{")}${k("type")}${p(":")} "title"${p(",")}`],
          [4, `${k("text")}${p(":")} "Building A Secure`],
          [5, `Client Data Hub"${p(",")}`],
          [4, `${k("runs")}${p(": [")}`],
          [5, `${p("{")}${k("start")}${p(":")} 1${p(",")} ${k("end")}${p(":")} 10${p(",")}`, "r1"],
          [5, `<span class="sw" style="background:#000000"></span>${k("color")}${p(":")} "#000000"${p("},")}`, "r1c"],
          [5, `${p("{")}${k("start")}${p(":")} 12${p(",")} ${k("end")}${p(":")} 17${p(",")}`, "r2"],
          [5, `<span class="sw" style="background:#830041"></span>${k("color")}${p(":")} "#830041"${p("},")}`, "r2c"],
          [5, `${p("{")}${k("start")}${p(":")} 19${p(",")} ${k("end")}${p(":")} 33${p(",")}`, "r3"],
          [5, `<span class="sw" style="background:#F09490"></span>${k("color")}${p(":")} "#F09490"${p("}]}]}]}")}`, "r3c"],
        ];
        const fill = (host, lines, pre) => {
          document.getElementById(host).innerHTML = lines.map(([ind, h, id]) =>
            `<div class="j"${id ? ` id="${pre}-${id}"` : ""} style="padding-left:${6 + ind * 14}px">${h}</div>`).join("");
        };
        fill("b-j1", J1, "j1");
        fill("b-j2", J2, "j2");

        // ---- wires: line + arrowhead; dashed wires are revealed through a mask so the dashes stay put
        const WIRES = [
          { id: "w-call", d: "M410 212 H487", dir: "r" },
          { id: "w-spec", d: "M866 224 H889", dir: "r" },
          { id: "w-valid", d: "M1083 286 V293", dir: "d" },
          { id: "w-style", d: "M866 364 H889", dir: "r" },
          { id: "w-frag", d: "M1083 426 V433", dir: "d" },
          { id: "w-png", d: "M898 504 H875", dir: "l" },
          { id: "w-osa", d: "M1083 566 V573", dir: "d" },
          { id: "w-argv", d: "M1268 644 H1321", dir: "r" },
          { id: "w-draw", d: "M1595 582 V566", dir: "u" },
          { id: "w-read", d: "M1460 706 V728 H681 V715", dir: "u", dash: 1 },
          { id: "w-same", d: "M496 644 H429", dir: "l", dash: 1 },
          { id: "w-ci", d: "M624 772 V759", dir: "u", dash: 1 },
          { id: "w-live", d: "M974 772 V760 H1780 V715", dir: "u", dash: 1 },
        ];
        const end = (d) => { const n = d.match(/-?\d+(\.\d+)?/g).map(Number); const cmds = d.match(/[MHV]/g);
          let x = 0, y = 0, i = 0; for (const c of cmds) { if (c === "M") { x = n[i++]; y = n[i++]; } else if (c === "H") x = n[i++]; else y = n[i++]; } return [x, y]; };
        const head = ([x, y], dir) => {
          const a = 9, b = 6;
          if (dir === "r") return `M${x} ${y} L${x - a} ${y - b} L${x - a} ${y + b} Z`;
          if (dir === "l") return `M${x} ${y} L${x + a} ${y - b} L${x + a} ${y + b} Z`;
          if (dir === "d") return `M${x} ${y} L${x - b} ${y - a} L${x + b} ${y - a} Z`;
          return `M${x} ${y} L${x - b} ${y + a} L${x + b} ${y + a} Z`;
        };
        const tipOf = (d, dir) => { const [x, y] = end(d); const off = { r: [9, 0], l: [-9, 0], d: [0, 9], u: [0, -9] }[dir]; return [x + off[0] * 0.6, y + off[1] * 0.6]; };
        let defs = "", g = "";
        for (const w of WIRES) {
          const tip = tipOf(w.d, w.dir);
          if (w.dash) {
            defs += `<mask id="${w.id}-m" maskUnits="userSpaceOnUse" x="0" y="0" width="1920" height="1080"><path id="${w.id}-mk" class="mk" d="${w.d}" pathLength="1"/></mask>`;
            g += `<g id="${w.id}"><path class="w dash" d="${w.d}" mask="url(#${w.id}-m)"/><path id="${w.id}-h" class="h" d="${head(tip, w.dir)}"/></g>`;
          } else {
            g += `<g id="${w.id}"><path id="${w.id}-ln" class="w" d="${w.d}" pathLength="1"/><path id="${w.id}-h" class="h" d="${head(tip, w.dir)}"/></g>`;
          }
        }
        wires.innerHTML = `<defs>${defs}</defs>${g}`;
      this.labels();
      return { CARDS, WIRES };
    },
    // the edge labels on the wires (world px)
    labels() {
      document.getElementById("b-wls").outerHTML = `
        <div id="wl-call" class="wl" style="left:414px; top:184px">tools/call</div>
        <div id="wl-valid" class="wl" style="left:1092px; top:284px">valid</div>
        <div id="wl-osa" class="wl" style="left:1092px; top:564px">AppleScript</div>
        <div id="wl-argv" class="wl" style="left:1272px; top:616px">argv</div>
        <div id="wl-draw" class="wl" style="left:1606px; top:558px">draws, exports</div>
        <div id="wl-read" class="wl" style="left:1150px; top:733px">reads back</div>
        <div id="wl-same" class="wl" style="left:422px; top:618px">same spec</div>
        <div id="wl-ci" class="wl" style="left:640px; top:750px">CI</div>
        <div id="wl-live" class="wl" style="left:1430px; top:736px">live</div>`;
    },
    // W(): a word's time in the voice (window.VO), in seconds from the scene's start S0; "a|b" tries each spelling
    W(S0) {
      const VO = window.VO, norm = (s) => s.toLowerCase().replace(/[^a-z0-9]/g, "");
      return (k, w, nth = 0) => {
        const alts = w.split("|");
        for (const exact of [true, false]) {
          let c = 0;
          for (const x of VO[k].words) {
            const t = norm(x.w);
            if (alts.some((a) => (exact ? t === a : t.startsWith(a)))) { if (c === nth) return x.t0 - S0; c++; }
          }
        }
        return VO[k].start - S0;
      };
    },
    // the motion vocabulary (CERFODES): pop, fade, out, dot, placeholder, light, wire, highlight, count
    helpers(tl, WIRES) {
        const pop = (sel, at, dy = 18) => tl.fromTo(sel, { opacity: 0, y: dy, scale: 0.96 }, { opacity: 1, y: 0, scale: 1, duration: 0.6, ease: "back.out(1.5)" }, at);
        const fade = (sel, at, d = 0.5) => tl.fromTo(sel, { opacity: 0 }, { opacity: 1, duration: d, ease: "power1.out" }, at);
        const out = (sel, at, d = 0.35) => tl.to(sel, { opacity: 0, duration: d, ease: "power1.in" }, at);
        const dot = (sel, at) => tl.fromTo(sel, { opacity: 0, x: -8 }, { opacity: 1, x: 0, duration: 0.45, ease: "power2.out" }, at);
        // placeholder: the empty card shape arrives early (faint), its content lights up on the narrated word
        const ph = (sel, at) => tl.fromTo(sel, { opacity: 0, scale: 0.97 }, { opacity: 0.5, scale: 1, duration: 0.45, ease: "power2.out" }, at);
        const light = (sel, at) => {
          tl.to(sel, { opacity: 1, duration: 0.3, ease: "power1.out" }, at);
          tl.fromTo(`${sel} > *`, { opacity: 0, y: 10 }, { opacity: 1, y: 0, duration: 0.45, ease: "power2.out" }, at);
          tl.to(sel, { scale: 1.035, duration: 0.2, ease: "power2.out" }, at);
          tl.to(sel, { scale: 1, duration: 0.35, ease: "power2.inOut" }, at + 0.2);
        };
        // quiet: a card the voice does not name fills in without the scale pulse
        const quiet = (sel, at) => {
          tl.to(sel, { opacity: 1, duration: 0.4, ease: "power1.out" }, at);
          tl.fromTo(`${sel} > *`, { opacity: 0 }, { opacity: 1, duration: 0.5, ease: "power1.out" }, at);
        };
        const wire = (id, at, d = 0.45) => {
          const w = WIRES.find((x) => x.id === id);
          tl.fromTo(`#${id}-${w.dash ? "mk" : "ln"}`, { strokeDasharray: 1, strokeDashoffset: 1 }, { strokeDashoffset: 0, duration: d, ease: "power2.inOut" }, at);
          tl.fromTo(`#${id}-h`, { opacity: 0 }, { opacity: 1, duration: 0.15 }, at + d - 0.1);
        };
        // a line of JSON or text lights: a soft brand-blue capsule fades in behind it
        const hl = (sel, at, c = "rgba(47,100,176,0.12)") =>
          tl.fromTo(sel, { backgroundColor: "rgba(47,100,176,0)" }, { backgroundColor: c, duration: 0.3, ease: "power1.out" }, at);
        const unhl = (sel, at) => tl.to(sel, { backgroundColor: "rgba(47,100,176,0)", duration: 0.5, ease: "power1.inOut" }, at);
        const count = (sel, at, to, d) => {
          const n = { v: 0 };
          tl.fromTo(n, { v: 0 }, { v: to, duration: d, ease: "power1.out",
            onUpdate: () => { document.querySelector(sel).textContent = String(Math.round(n.v)); } }, at);
        };
      return { pop, fade, out, dot, ph, light, quiet, wire, hl, unhl, count };
    },
  };
})();
