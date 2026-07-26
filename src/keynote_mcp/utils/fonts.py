"""PostScript font-name decomposition.

Keynote reports a font as its PostScript name — ``LibreCaslonCondensed-Medium``,
``HoeflerText-Black``, ``TimesNewRomanPSMT``. That round-trips perfectly (and
is exactly what you must pass back, since Keynote has no bold/italic attribute
— weight and slant ARE the face name), but it makes consistency auditing a
string-munging exercise: the field report resorted to ``sub("-.*";"")``.

So the family, weight and style are reported ALONGSIDE the PostScript name,
never instead of it.
"""

from __future__ import annotations

# Weight tokens in PostScript face names, longest first so "UltraLight" wins
# over "Light" and "Semibold" over "Bold".
_WEIGHT_TOKENS = (
    "UltraLight",
    "ExtraLight",
    "SemiBold",
    "Semibold",
    "DemiBold",
    "ExtraBold",
    "UltraBold",
    "Thin",
    "Light",
    "Regular",
    "Normal",
    "Book",
    "Roman",
    "Medium",
    "Bold",
    "Heavy",
    "Black",
)

# Longest first, so "ExtraBold" wins over "Bold" and "UltraLight" over "Light"
# regardless of how the tuple above is ordered.
_WEIGHTS = tuple(sorted(_WEIGHT_TOKENS, key=len, reverse=True))

# Weights that are safe to detect INSIDE a name with no hyphen. "Roman" is
# excluded: TimesNewRomanPSMT is the Times New Roman family, not a "Roman"
# weight of a "TimesNew" family. Same for "Book" (Bookman) and "Black"
# (Blackadder) - all real font families whose names end in a weight word.
_AMBIGUOUS_EMBEDDED = frozenset({"Roman", "Book", "Black", "Normal", "Medium"})
_EMBEDDED_WEIGHTS = tuple(w for w in _WEIGHTS if w not in _AMBIGUOUS_EMBEDDED)

_STYLES = ("Italic", "Oblique")

# Trailing PostScript-name noise that carries no design meaning.
# TimesNewRomanPSMT -> TimesNewRoman (MT = Monotype, PS = PostScript).
_NAME_SUFFIXES = ("PSMT", "PS-MT", "MT", "PS")


def split_font_name(postscript_name: str) -> dict[str, str]:
    """Decompose a PostScript font name into family / weight / style.

    Returns a dict with ``font_name`` (always the original, unmodified),
    ``font_family``, ``font_weight`` and ``font_style``. Weight defaults to
    "Regular" and style to "Normal" when the face name says nothing, which is
    what those faces actually are.

    Deliberately conservative: an unrecognized suffix stays part of the family
    rather than being guessed at, so an audit sees the real string instead of a
    plausible invention.
    """
    name = (postscript_name or "").strip()
    if not name:
        return {"font_name": "", "font_family": "", "font_weight": "", "font_style": ""}

    family, _, face = name.partition("-")
    weight = ""
    style = ""

    if face:
        remainder = face
        for token in _STYLES:
            if remainder.endswith(token):
                style = token
                remainder = remainder[: -len(token)]
                break
        # Match at the END, not the start: "CondensedExtraBold" is the
        # ExtraBold weight of a Condensed family, and a startswith test finds
        # nothing at all in it.
        for token in _WEIGHTS:
            if remainder.endswith(token):
                weight = token
                remainder = remainder[: -len(token)]
                break
        # Anything left over was not a weight/style - keep it on the family so
        # nothing is silently dropped (e.g. "Condensed", "Display").
        if remainder:
            family = f"{family}-{remainder}" if family else remainder
    else:
        # No hyphen: strip PostScript foundry noise, then look for an
        # embedded weight/style word (HelveticaNeueBold). Ambiguous words are
        # deliberately NOT matched here - see _AMBIGUOUS_EMBEDDED.
        for suffix in _NAME_SUFFIXES:
            if family.endswith(suffix) and len(family) > len(suffix):
                family = family[: -len(suffix)]
                break
        for token in _STYLES:
            if family.endswith(token) and len(family) > len(token):
                style = token
                family = family[: -len(token)]
                break
        for token in _EMBEDDED_WEIGHTS:
            if family.endswith(token) and len(family) > len(token):
                weight = token
                family = family[: -len(token)]
                break

    return {
        "font_name": name,
        "font_family": family,
        "font_weight": weight or "Regular",
        "font_style": style or "Normal",
    }
