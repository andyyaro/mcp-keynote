"""PHASE 9 Task 6 — hex colours and font family/weight/style.

The field report: colours came back as 16-bit-per-channel comma strings
("33665,0,16829"), so every consumer had to divide by 257 and hex-encode; and
font_name was the bare PostScript name, so consistency auditing meant
string-munging `sub("-.*";"")`.

The values below are the exact ones the report cited from the real deck.
"""

from __future__ import annotations

import pytest

from keynote_mcp.utils.error_handler import parse_color, rgb65535_to_hex
from keynote_mcp.utils.fonts import split_font_name


class TestHexColor:
    @pytest.mark.parametrize(
        ("triple", "expected"),
        [
            ("33665,0,16829", "#830041"),  # cited in the field report
            ("65528,65535,65525", "#FFFFFF"),  # cited in the field report
            ("36493,7967,21845", "#8E1F55"),  # the deck's maroon
            ("61423,41890,41120", "#EFA3A0"),  # the deck's salmon
            ("0,0,0", "#000000"),
            ("65535,65535,65535", "#FFFFFF"),
        ],
    )
    def test_real_keynote_values_convert_exactly(self, triple: str, expected: str) -> None:
        assert rgb65535_to_hex(triple) == expected

    @pytest.mark.parametrize("bad", ["", "garbage", "1,2", "1,2,3,4", "a,b,c", "-5,0,0"])
    def test_unusable_input_returns_empty_not_a_wrong_colour(self, bad: str) -> None:
        """Empty is distinguishable; a plausible-but-wrong hex would not be."""
        assert rgb65535_to_hex(bad) == ""

    def test_round_trips_through_parse_color(self) -> None:
        """The hex we emit must be something build_deck accepts back, or the
        describe -> edit -> build round trip breaks."""
        for triple in ("33665,0,16829", "61423,41890,41120", "0,0,0"):
            hex_form = rgb65535_to_hex(triple)
            reparsed = parse_color(hex_form)
            assert reparsed is not None
            assert rgb65535_to_hex(",".join(str(c) for c in reparsed)) == hex_form


class TestFontSplit:
    @pytest.mark.parametrize(
        ("name", "family", "weight", "style"),
        [
            # The three PostScript names the field report cited.
            ("LibreCaslonCondensed-Medium", "LibreCaslonCondensed", "Medium", "Normal"),
            ("HoeflerText-Black", "HoeflerText", "Black", "Normal"),
            ("TimesNewRomanPSMT", "TimesNewRoman", "Regular", "Normal"),
            # Ordinary faces.
            ("Helvetica-Bold", "Helvetica", "Bold", "Normal"),
            ("HelveticaNeue", "HelveticaNeue", "Regular", "Normal"),
            ("Menlo-Regular", "Menlo", "Regular", "Normal"),
            # Combined weight + slant.
            ("HelveticaNeue-BoldItalic", "HelveticaNeue", "Bold", "Italic"),
            ("AvenirNext-DemiBoldItalic", "AvenirNext", "DemiBold", "Italic"),
            ("Baskerville-SemiBoldItalic", "Baskerville", "SemiBold", "Italic"),
            # A width word that is NOT a weight must stay with the family.
            ("Futura-CondensedExtraBold", "Futura-Condensed", "ExtraBold", "Normal"),
            ("GillSans-UltraBold", "GillSans", "UltraBold", "Normal"),
        ],
    )
    def test_decomposition(self, name: str, family: str, weight: str, style: str) -> None:
        got = split_font_name(name)
        assert got["font_family"] == family
        assert got["font_weight"] == weight
        assert got["font_style"] == style

    @pytest.mark.parametrize("name", ["Bookman", "Didot", "Monaco", "Papyrus"])
    def test_family_names_ending_in_a_weight_word_are_not_split(self, name: str) -> None:
        """ "Bookman" is a family, not the Book weight of a "man" family.
        Guessing here would silently corrupt a font audit."""
        got = split_font_name(name)
        assert got["font_family"] == name
        assert got["font_weight"] == "Regular"

    def test_postscript_name_is_always_preserved_verbatim(self) -> None:
        """It is what must be passed BACK: Keynote has no bold/italic
        attribute, so the face name carries weight and slant."""
        for name in (
            "LibreCaslonCondensed-Medium",
            "TimesNewRomanPSMT",
            "Futura-CondensedExtraBold",
        ):
            assert split_font_name(name)["font_name"] == name

    def test_empty_input_is_handled(self) -> None:
        got = split_font_name("")
        assert got == {"font_name": "", "font_family": "", "font_weight": "", "font_style": ""}
