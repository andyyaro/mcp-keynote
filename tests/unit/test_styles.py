"""Deck style resolution: built-ins, TOML loading, config discovery, and
derived layout metrics."""

import pytest

from keynote_mcp.utils import ParameterError
from keynote_mcp.utils.styles import (
    BUILTIN_STYLES,
    DeckStyle,
    load_style_file,
    resolve_style,
    style_color,
)


class TestBuiltins:
    def test_expected_names(self):
        assert set(BUILTIN_STYLES) == {"plain", "boardroom", "midnight", "editorial"}

    def test_resolve_boardroom(self):
        style = resolve_style("boardroom")
        assert style.name == "boardroom"
        assert style.title_color == "#16294A"
        assert style.keynote_theme == "White"

    def test_unknown_name_lists_builtins(self):
        with pytest.raises(ParameterError) as exc:
            resolve_style("corporate")
        message = str(exc.value)
        for name in ("plain", "boardroom", "midnight", "editorial"):
            assert name in message


class TestTomlLoading:
    def test_flat_keys(self, tmp_path):
        f = tmp_path / "s.toml"
        f.write_text('title_size = 72\ntitle_color = "#112233"\n')
        style = load_style_file(f)
        assert style.title_size == 72.0
        assert style.title_color == "#112233"
        # untouched keys keep the plain defaults
        assert style.body_size == DeckStyle().body_size

    def test_style_table_form(self, tmp_path):
        f = tmp_path / "s.toml"
        f.write_text("[style]\nbody_size = 30\n")
        assert load_style_file(f).body_size == 30.0

    def test_extends_chain(self, tmp_path):
        f = tmp_path / "s.toml"
        f.write_text('extends = "midnight"\ntitle_size = 90\n')
        style = load_style_file(f)
        assert style.title_size == 90.0
        assert style.keynote_theme == "Black"  # inherited from midnight
        assert style.accent_color == "#E8A33D"

    def test_bad_extends_raises(self, tmp_path):
        f = tmp_path / "s.toml"
        f.write_text('extends = "corporate"\n')
        with pytest.raises(ParameterError, match="'extends' must be one of"):
            load_style_file(f)

    def test_unknown_key_raises(self, tmp_path):
        f = tmp_path / "s.toml"
        f.write_text("heading_size = 40\n")
        with pytest.raises(ParameterError, match="unknown keys"):
            load_style_file(f)

    def test_wrong_type_raises(self, tmp_path):
        # NOTE: the expected type in the message comes from the built-in
        # default's runtime type (66 is stored as int), so only the "got str"
        # half is asserted here - a string must be rejected either way.
        f = tmp_path / "s.toml"
        f.write_text('title_size = "huge"\n')
        with pytest.raises(ParameterError, match=r"key 'title_size' must be .*, got str"):
            load_style_file(f)

    def test_bad_color_raises(self, tmp_path):
        f = tmp_path / "s.toml"
        f.write_text('title_color = "#XYZXYZ"\n')
        with pytest.raises(ParameterError, match="Invalid color"):
            load_style_file(f)

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(ParameterError, match="not found"):
            load_style_file(tmp_path / "no.toml")

    def test_invalid_toml_raises(self, tmp_path):
        f = tmp_path / "s.toml"
        f.write_text("[[[not toml")
        with pytest.raises(ParameterError, match="not valid TOML"):
            load_style_file(f)

    def test_resolve_by_path(self, tmp_path):
        f = tmp_path / "custom.toml"
        f.write_text("quote_size = 44\n")
        assert resolve_style(str(f)).quote_size == 44.0


class TestDiscovery:
    def test_config_next_to_save_path_wins(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)  # cwd has no config; only the deck dir does
        deck_dir = tmp_path / "decks"
        deck_dir.mkdir()
        (deck_dir / ".keynote-mcp.toml").write_text("title_size = 55\n")
        style = resolve_style("", near_path=str(deck_dir / "my.key"))
        assert style.title_size == 55.0

    def test_no_config_defaults_to_plain(self, tmp_path, monkeypatch):
        empty = tmp_path / "empty"
        empty.mkdir()
        monkeypatch.chdir(empty)
        style = resolve_style("", near_path=str(empty / "my.key"))
        assert style.name == "plain"

    def test_cwd_config_is_the_fallback(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".keynote-mcp.toml").write_text("body_size = 21\n")
        assert resolve_style("").body_size == 21.0


class TestDerivedMetrics:
    def test_margins_and_gap_scale_with_slide_size(self):
        plain = BUILTIN_STYLES["plain"]
        assert plain.margin_x(1920) == round(1920 * plain.margin_x_frac)
        assert plain.margin_top(1080) == round(1080 * plain.margin_top_frac)
        assert plain.margin_bottom(1080) == round(1080 * plain.margin_bottom_frac)
        assert plain.gap(1080) == round(1080 * plain.gap_frac)
        assert plain.content_width(1920) == 1920 - 2 * plain.margin_x(1920)
        # half the slide size -> half (rounded) the derived metrics
        assert plain.margin_x(960) == round(960 * plain.margin_x_frac)
        assert plain.content_width(960) < plain.content_width(1920)

    def test_style_color_parses_or_defers(self):
        plain = BUILTIN_STYLES["plain"]
        assert style_color(plain, "body_color") is None  # theme keeps styling
        assert style_color(plain, "accent_color") == (0x3B * 257, 0x6E * 257, 0xCC * 257)
