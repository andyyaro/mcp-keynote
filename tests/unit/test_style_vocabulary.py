"""PHASE 9 Task 9 — the style system against a REAL design system.

`.keynote-mcp.toml` had only ever been tested with invented input. Handed
tokens.json from a real 35-slide technical architecture deck, the flat
27-scalar schema could carry 3 of its ~60 concepts: slide size, theme, and a
couple of fonts. Everything that made the deck a SYSTEM — 22 named type roles,
a palette where colour is a referent rather than decoration, 8 semantic
connector strokes, named canvas zones, and an n-up grid with real gutters —
had no representation at all.

These tests pin the five named vocabularies that closed that gap, and the
shipped `sdh` style built from the real tokens.
"""

from __future__ import annotations

import pytest

from keynote_mcp.utils.error_handler import ParameterError
from keynote_mcp.utils.styles import BUILTIN_STYLES, DeckStyle, _style_from_mapping, resolve_style


class TestShippedSdhStyle:
    """The real design system, shipped as a built-in."""

    @pytest.fixture
    def sdh(self) -> DeckStyle:
        return resolve_style("sdh")

    def test_it_is_a_builtin(self) -> None:
        assert "sdh" in BUILTIN_STYLES

    def test_carries_every_named_type_role(self, sdh: DeckStyle) -> None:
        assert len(sdh.type) == 22
        # The deck's single most-used style, and its rarest.
        assert sdh.type_role("label.service") == {
            "font": "HoeflerText-Regular",
            "size": 22,
            "color": "#000000",
        }
        assert sdh.type_role("title.canvas")["size"] == 69

    def test_carries_the_semantic_palette(self, sdh: DeckStyle) -> None:
        assert sdh.resolve_color("@zone.private") == "#98C1DA"
        assert sdh.resolve_color("@accent.deep") == "#830041"
        assert sdh.resolve_color("#123456") == "#123456", "plain hex must pass through"

    def test_carries_all_eight_semantic_connectors(self, sdh: DeckStyle) -> None:
        assert len(sdh.connectors) == 8
        assert sdh.connector("data") == {
            "color": "#8A2052",
            "width": 5,
            "dash": "solid",
            "meaning": "Retrieve / Update",
        }
        assert sdh.connector("denied")["dash"] == "dotted"

    def test_grid_module_pitch_produces_the_real_column_positions(self, sdh: DeckStyle) -> None:
        """The x values a spec previously had to hand-compute."""
        xs = [sdh.module_origin("accountColumn3up", i)[0] for i in (1, 2, 3)]
        assert xs == [27, 383, 739]
        assert sdh.module_origin("accountColumn3up", 1)[2] == 351  # width, not pitch

    def test_carries_named_zones(self, sdh: DeckStyle) -> None:
        assert sdh.zones["legend"]["y"] == 1016
        assert sdh.zones["title"]["height"] == 97

    def test_records_its_own_version(self, sdh: DeckStyle) -> None:
        assert sdh.version
        assert sdh.description


class TestUnknownNamesFailLoudly:
    """A misspelt name must not silently fall back to a default."""

    @pytest.fixture
    def sdh(self) -> DeckStyle:
        return resolve_style("sdh")

    def test_unknown_palette_colour(self, sdh: DeckStyle) -> None:
        with pytest.raises(ParameterError) as e:
            sdh.resolve_color("@zone.nope")
        assert "zone.private" in str(e.value), "the error must list what IS defined"

    def test_unknown_type_role(self, sdh: DeckStyle) -> None:
        with pytest.raises(ParameterError, match="Unknown type role"):
            sdh.type_role("label.nope")

    def test_unknown_connector(self, sdh: DeckStyle) -> None:
        with pytest.raises(ParameterError, match="Unknown connector"):
            sdh.connector("telepathy")

    def test_unknown_module(self, sdh: DeckStyle) -> None:
        with pytest.raises(ParameterError, match="Unknown grid module"):
            sdh.module_origin("nope", 1)


class TestNestedTableLoading:
    """The loader accepted only scalars, which is why a design system could not
    be expressed at all."""

    def test_loads_all_five_vocabularies(self) -> None:
        style = _style_from_mapping(
            {
                "name": "t",
                "type": {"h1": {"font": "Georgia", "size": 40, "color": "#111111"}},
                "palette": {"brand": "#830041"},
                "connectors": {"data": {"color": "@brand", "width": 3, "dash": "dotted"}},
                "zones": {"legend": {"x": 0, "y": 1016, "width": 1920, "height": 44}},
                "modules": {"col": {"width": 300, "height": 500, "pitch": 320, "origin_x": 40}},
            },
            "test",
        )
        assert style.type["h1"]["size"] == 40
        assert style.palette["brand"] == "#830041"
        assert style.connector("data")["dash"] == "dotted"
        assert style.zones["legend"]["height"] == 44
        assert style.module_origin("col", 2)[0] == 360

    def test_a_palette_reference_inside_a_connector_is_validated(self) -> None:
        with pytest.raises(ParameterError, match=r"connectors\.data\.color"):
            _style_from_mapping(
                {"connectors": {"data": {"color": "@missing"}}},
                "test",
            )

    def test_a_bad_palette_colour_fails_at_load_not_mid_build(self) -> None:
        with pytest.raises(ParameterError, match=r"palette\.brand"):
            _style_from_mapping({"palette": {"brand": "not-a-colour"}}, "test")

    def test_misspelt_entry_key_is_rejected(self) -> None:
        """ "colour" must fail rather than be silently ignored - the same
        principle as the server's unknown-argument guard."""
        with pytest.raises(ParameterError, match="unknown keys"):
            _style_from_mapping({"type": {"h1": {"colour": "#000000"}}}, "test")

    def test_a_vocabulary_must_be_a_table(self) -> None:
        with pytest.raises(ParameterError, match="must be a table"):
            _style_from_mapping({"palette": "not a table"}, "test")

    def test_scalar_fields_still_work(self) -> None:
        style = _style_from_mapping({"title_size": 70.5, "keynote_theme": "Black"}, "test")
        assert style.title_size == 70.5
        assert style.keynote_theme == "Black"

    def test_styles_without_vocabularies_get_empty_ones(self) -> None:
        assert resolve_style("plain").type == {}
        assert resolve_style("plain").palette == {}
