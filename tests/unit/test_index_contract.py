"""PHASE 9 Task 2 — one numbering across every emitting and consuming tool.

The field report found describe_deck and get_slide_content numbering text items
differently, and the offset existed only on slides using the title placeholder,
so it was not even constant. Phase 8.2 fixed the same CLASS of bug per-instance
for the add_* tools and it came back here. These tests pin the shared
machinery, so a third instance cannot land quietly.

See docs/INDEX_CONTRACT.md.
"""

from __future__ import annotations

import pytest

from keynote_mcp.tools import content as content_mod
from keynote_mcp.tools import deck as deck_mod
from keynote_mcp.tools.fragments import TEXT_ITEM_FILTER, exists_guard


class TestSharedFilter:
    def test_both_readers_use_the_shared_filter_not_a_private_copy(self) -> None:
        """Two hand-rolled copies of the placeholder predicate is exactly how
        the two tools came to disagree."""
        for module in (content_mod, deck_mod):
            source = module.__file__
            assert source is not None
            text = open(source).read()
            assert "TEXT_ITEM_FILTER" in text, f"{module.__name__} hand-rolls the filter"

    def test_filter_keeps_the_first_showing_placeholder_and_flags_its_role(self) -> None:
        # The predicate is AppleScript, so assert on its structure: a showing
        # placeholder's FIRST sighting must set a role rather than be skipped.
        assert 'set role to "title"' in TEXT_ITEM_FILTER
        assert 'set role to "body"' in TEXT_ITEM_FILTER
        assert "realRoles" in TEXT_ITEM_FILTER

    def test_filter_skips_repeats_and_hidden_placeholders(self) -> None:
        assert "if seenTitle or (not titleShown) then" in TEXT_ITEM_FILTER
        assert "if seenBody or (not bodyShown) then" in TEXT_ITEM_FILTER

    def test_filter_identifies_placeholders_by_object_identity(self) -> None:
        """Not by emptiness or 0x0 geometry - those heuristics misfired both
        ways before Phase 8."""
        assert "ti is defT" in TEXT_ITEM_FILTER
        assert "ti is defB" in TEXT_ITEM_FILTER


class TestExistsGuard:
    def test_guard_raises_1719_for_the_addressed_class_and_index(self) -> None:
        script = exists_guard("text item", 7, 3)
        assert "exists text item 7 of slide 3 of targetDoc" in script
        assert "number -1719" in script

    @pytest.mark.parametrize(
        "tool_source",
        ["edit_text_item", "move_element", "resize_element", "set_element_opacity"],
    )
    def test_content_write_tools_guard_their_index(self, tool_source: str) -> None:
        """A stale index addresses a DIFFERENT object, not none - so an
        unguarded write silently edits the wrong element and reports success."""
        source = content_mod.__file__
        assert source is not None
        text = open(source).read()
        start = text.index(f"async def {tool_source}")
        body = text[start : start + 3000]
        assert "exists_guard(" in body, f"{tool_source} does not guard its index"

    def test_style_text_range_guards_its_index(self) -> None:
        from keynote_mcp.tools import objects as objects_mod

        source = objects_mod.__file__
        assert source is not None
        text = open(source).read()
        start = text.index("async def style_text_range")
        assert "exists_guard(" in text[start : start + 3000]


class TestClearSlideProtectsPlaceholders:
    def test_shape_loop_is_identity_guarded_like_the_text_loop(self) -> None:
        """The sdef types default title/body items as SHAPES. describe_deck
        already guarded its shape loop; clear_slide deleted shapes blind, which
        would destroy a theme placeholder wherever they surface that way."""
        source = content_mod.__file__
        assert source is not None
        text = open(source).read()
        start = text.index("async def clear_slide")
        body = text[start : start + 3000]
        assert "keepShape" in body
        assert "delete shape i" not in body, "shape deletion is unguarded again"


class TestDescribeDeckEmitsAddressableIndices:
    """describe_deck's array position is NOT an address: it walks class by
    class, so elements[3] can be image 2. Every element must carry its own
    class and index."""

    def test_every_element_branch_sets_element_class_and_index(self) -> None:
        source = deck_mod.__file__
        assert source is not None
        text = open(source).read()
        start = text.index('elif kind == "T":')
        end = text.index("return slide", start)
        body = text[start:end]
        for cls in ("text item", "image", "shape", "table", "chart", "line"):
            assert f'"element_class": "{cls}"' in body, f"{cls} carries no element_class"
        assert body.count('"index":') >= 6

    def test_placeholder_role_is_carried_through(self) -> None:
        source = deck_mod.__file__
        assert source is not None
        text = open(source).read()
        assert 'el["placeholder"] = fields[10]' in text
