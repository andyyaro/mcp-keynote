"""Deck spec validation, the markdown dialect compiler, auto-flow layout, and
table-cell round-trip typing. All pure functions - no osascript involved."""

from keynote_mcp.tools.deck import (
    _flow_slide,
    _parse_attrs,
    _parse_cell,
    markdown_to_spec,
    validate_spec,
)
from keynote_mcp.utils.styles import BUILTIN_STYLES

PLAIN = BUILTIN_STYLES["plain"]


def _slide(**kwargs):
    return {"slides": [{"elements": [], **kwargs}]}


def _element(el):
    return {"slides": [{"elements": [el]}]}


class TestValidateSpec:
    def test_non_object_spec(self):
        assert validate_spec([1, 2]) == ["spec must be a JSON object"]

    def test_empty_slides(self):
        assert "spec.slides must be a non-empty array" in validate_spec({"slides": []})

    def test_collects_multiple_errors_not_just_first(self):
        errors = validate_spec(
            {
                "width": 10,
                "slides": [
                    "not-a-dict",
                    {"elements": [{"type": "title"}, {"type": "nope"}]},
                ],
            }
        )
        assert len(errors) >= 4
        assert any("spec.width" in e for e in errors)
        assert any("slides[0]" in e and "must be an object" in e for e in errors)
        assert any("slides[1].elements[0]" in e and "non-empty 'text'" in e for e in errors)
        assert any("slides[1].elements[1]" in e and "unknown element type" in e for e in errors)

    def test_slide_field_types(self):
        errors = validate_spec(
            {"slides": [{"title": 3, "skipped": "yes", "elements": "not-a-list"}]}
        )
        assert any(".title" in e for e in errors)
        assert any(".skipped" in e for e in errors)
        assert any(".elements" in e for e in errors)

    def test_transition_validation(self):
        assert any(".transition" in e for e in validate_spec(_slide(transition="push")))
        errors = validate_spec(
            _slide(transition={"effect": "teleport", "duration": -1, "delay": "x"})
        )
        assert any("transition.effect" in e for e in errors)
        assert any("transition.duration" in e for e in errors)
        assert any("transition.delay" in e for e in errors)
        assert validate_spec(_slide(transition={"effect": "magic_move", "duration": 2})) == []

    def test_element_geometry_and_color(self):
        errors = validate_spec(
            _element({"type": "text", "text": "t", "x": -5, "width": "wide", "color": "#XYZ"})
        )
        assert any(".x" in e for e in errors)
        assert any(".width" in e for e in errors)
        assert any(".color" in e for e in errors)

    def test_column_must_be_left_or_right(self):
        errors = validate_spec(_element({"type": "text", "text": "t", "column": "middle"}))
        assert any("column" in e for e in errors)

    def test_bullets_need_string_items(self):
        assert any(
            "'items'" in e for e in validate_spec(_element({"type": "bullets", "items": []}))
        )
        assert any(
            "'items'" in e for e in validate_spec(_element({"type": "numbered", "items": [1]}))
        )

    def test_image_needs_existing_file(self, tmp_path):
        assert any("needs a 'path'" in e for e in validate_spec(_element({"type": "image"})))
        assert any(
            "does not exist" in e
            for e in validate_spec(_element({"type": "image", "path": str(tmp_path / "no.png")}))
        )
        real = tmp_path / "yes.png"
        real.write_bytes(b"x")
        assert validate_spec(_element({"type": "image", "path": str(real)})) == []

    def test_panel_needs_explicit_geometry(self):
        errors = validate_spec(_element({"type": "panel", "x": 1, "y": 2}))
        assert any("'width'" in e for e in errors)
        assert any("'height'" in e for e in errors)

    def test_table_shape_errors(self):
        assert any(
            "at least 2 rows" in e
            for e in validate_spec(_element({"type": "table", "data": [["a", "b"]]}))
        )
        assert any(
            "rows (arrays)" in e
            for e in validate_spec(_element({"type": "table", "data": ["a", "b"]}))
        )
        assert any(
            "same length" in e
            for e in validate_spec(_element({"type": "table", "data": [["a", "b"], ["c"]]}))
        )
        assert any(
            "at least 2 columns" in e
            for e in validate_spec(_element({"type": "table", "data": [["a"], ["b"]]}))
        )

    def test_chart_errors(self):
        errors = validate_spec(_element({"type": "chart", "chart_type": "donut"}))
        assert any("chart_type" in e for e in errors)
        assert any("'row_names'" in e for e in errors)
        assert any("'column_names'" in e for e in errors)
        assert any("'data'" in e for e in errors)
        errors = validate_spec(
            _element(
                {
                    "type": "chart",
                    "chart_type": "bar",
                    "row_names": ["a"],
                    "column_names": ["x", "y"],
                    "data": [[1, 2], [3, 4]],
                    "group_by": "series",
                }
            )
        )
        assert any("2 rows for 1 row_names" in e for e in errors)
        assert any("group_by" in e for e in errors)
        errors = validate_spec(
            _element(
                {
                    "type": "chart",
                    "chart_type": "bar",
                    "row_names": ["a"],
                    "column_names": ["x", "y"],
                    "data": [[1]],
                }
            )
        )
        assert any("one number per column_name" in e for e in errors)

    def test_line_needs_all_endpoints(self):
        errors = validate_spec(_element({"type": "line", "x1": 0, "y1": 0, "x2": 5}))
        assert any("'y2'" in e for e in errors)

    def test_valid_spec_has_no_errors(self):
        spec = {
            "width": 1920,
            "height": 1080,
            "slides": [
                {
                    "title": "T",
                    "notes": "n",
                    "skipped": True,
                    "elements": [
                        {"type": "title", "text": "Hello"},
                        {"type": "bullets", "items": ["a", "b"], "column": "left"},
                        {"type": "table", "data": [["a", "b"], [1, 2]]},
                        {"type": "line", "x1": 0, "y1": 0, "x2": 5, "y2": 5},
                    ],
                }
            ],
        }
        assert validate_spec(spec) == []


class TestParseAttrs:
    def test_no_comment(self):
        assert _parse_attrs("plain line") == ("plain line", {})

    def test_typed_values_and_flags(self):
        text, attrs = _parse_attrs("body <!-- x=10 y=2.5 centered=true flag skip=false -->")
        assert text == "body"
        assert attrs == {"x": 10, "y": 2.5, "centered": True, "flag": True, "skip": False}


class TestMarkdownToSpec:
    def test_frontmatter(self):
        spec = markdown_to_spec(
            "---\ntitle: My Deck\ntheme: Slate\nstyle: boardroom\n"
            "width: 1024\nheight: not-a-number\nignored: x\n---\n\n# My Deck\n"
        )
        assert spec["title"] == "My Deck"
        assert spec["theme"] == "Slate"
        assert spec["style"] == "boardroom"
        assert spec["width"] == 1024
        assert "height" not in spec
        assert "ignored" not in spec

    def test_h1_makes_centered_title_slide(self):
        spec = markdown_to_spec("# Big Deck <!-- font_size=90 -->\n")
        assert spec["title"] == "Big Deck"
        (el,) = spec["slides"][0]["elements"]
        assert el["type"] == "title"
        assert el["centered"] is True
        assert el["font_size"] == 90

    def test_h2_starts_new_slide(self):
        spec = markdown_to_spec("# One\n\n## Two\n\nSome body text\n")
        assert len(spec["slides"]) == 2
        title_el = spec["slides"][1]["elements"][0]
        assert title_el["type"] == "title"
        assert "centered" not in title_el
        assert spec["slides"][1]["elements"][1] == {"type": "text", "text": "Some body text"}

    def test_bullets_and_numbered(self):
        spec = markdown_to_spec(
            "## S\n\n- one\n- two <!-- column=left -->\n\n1. first\n2. second\n"
        )
        els = spec["slides"][0]["elements"][1:]
        assert els[0] == {"type": "bullets", "items": ["one", "two"], "column": "left"}
        assert els[1] == {"type": "numbered", "items": ["first", "second"]}

    def test_quote(self):
        spec = markdown_to_spec("## S\n\n> wise words\n> over two lines\n")
        assert spec["slides"][0]["elements"][1] == {
            "type": "quote",
            "text": "wise words over two lines",
        }

    def test_code_fence(self):
        spec = markdown_to_spec("## S\n\n```python <!-- font_size=14 -->\nx = 1\ny = 2\n```\n")
        el = spec["slides"][0]["elements"][1]
        assert el["type"] == "code"
        assert el["text"] == "x = 1\ny = 2"
        assert el["font_size"] == 14

    def test_chart_fence_with_json(self):
        spec = markdown_to_spec(
            "## S\n\n```chart <!-- height=400 -->\n"
            '{"chart_type": "bar", "row_names": ["r"], "column_names": ["c"], "data": [[1]]}\n'
            "```\n"
        )
        el = spec["slides"][0]["elements"][1]
        assert el["type"] == "chart"
        assert el["chart_type"] == "bar"
        assert el["data"] == [[1]]
        assert el["height"] == 400

    def test_chart_fence_bad_json_becomes_text(self):
        spec = markdown_to_spec("## S\n\n```chart\nnot json\n```\n")
        el = spec["slides"][0]["elements"][1]
        assert el["type"] == "text"
        assert "invalid chart JSON" in el["text"]

    def test_github_table_with_typed_cells(self):
        spec = markdown_to_spec(
            "## S\n\n| Region | Q1 | Growth |\n|---|---:|---|\n"
            "| North | 120 | 1.5 |\n| South | abc | 2 |\n"
        )
        el = spec["slides"][0]["elements"][1]
        assert el["type"] == "table"
        assert el["data"] == [
            ["Region", "Q1", "Growth"],
            ["North", 120, 1.5],
            ["South", "abc", 2],
        ]

    def test_image_line(self):
        spec = markdown_to_spec("## S\n\n![diagram](/tmp/pic.png) <!-- width=300 -->\n")
        el = spec["slides"][0]["elements"][1]
        assert el == {
            "type": "image",
            "path": "/tmp/pic.png",
            "description": "diagram",
            "width": 300,
        }

    def test_notes_paragraph(self):
        spec = markdown_to_spec("## S\n\nNotes: remember to smile\n")
        assert spec["slides"][0]["notes"] == "remember to smile"

    def test_transition_and_skip_directives(self):
        spec = markdown_to_spec("## S\n\n<!-- transition: push 0.5 auto -->\n<!-- skip -->\n")
        slide = spec["slides"][0]
        assert slide["transition"] == {"effect": "push", "duration": 0.5, "automatic": True}
        assert slide["skipped"] is True

    def test_transition_default_duration(self):
        spec = markdown_to_spec("## S\n\n<!-- transition: dissolve -->\n")
        assert spec["slides"][0]["transition"] == {
            "effect": "dissolve",
            "duration": 1.0,
            "automatic": False,
        }

    def test_paragraph_attribute_comment(self):
        spec = markdown_to_spec("## S\n\nCallout text <!-- x=10 width=200 column=left -->\n")
        el = spec["slides"][0]["elements"][1]
        assert el == {
            "type": "text",
            "text": "Callout text",
            "x": 10,
            "width": 200,
            "column": "left",
        }


class TestFlowSlide:
    def test_full_width_elements_stack_down(self):
        slide = {
            "elements": [
                {"type": "text", "text": "first"},
                {"type": "text", "text": "second"},
            ]
        }
        placed, bottom = _flow_slide(slide, PLAIN, 1920, 1080)
        assert placed[0]["x"] == PLAIN.margin_x(1920)
        assert placed[0]["y"] == PLAIN.margin_top(1080)
        assert placed[0]["width"] == PLAIN.content_width(1920)
        assert placed[1]["y"] > placed[0]["y"]
        assert bottom > placed[1]["y"]

    def test_columns_flow_independently(self):
        slide = {
            "elements": [
                {"type": "title", "text": "T"},
                {"type": "text", "text": "left one", "column": "left"},
                {"type": "text", "text": "left two", "column": "left"},
                {"type": "text", "text": "right one", "column": "right"},
            ]
        }
        placed, _ = _flow_slide(slide, PLAIN, 1920, 1080)
        _, l1, l2, r1 = placed
        assert l1["x"] == PLAIN.margin_x(1920)
        assert r1["x"] > l1["x"]
        # both columns start below the full-width title
        assert l1["y"] == r1["y"]
        # the second left element flows below the first; the right column
        # cursor is independent of the left one
        assert l2["y"] > l1["y"]
        assert l1["width"] == r1["width"]
        assert l1["width"] < PLAIN.content_width(1920) / 2

    def test_column_still_places_x_when_y_is_pinned(self):
        """A pinned y must not silently cancel the column.

        Regression: `{"column": "left"/"right", "y": ...}` fell through to
        fully-manual placement, which set no x at all - both columns landed
        at x=0, drawn on top of each other, with a clean zero-error build.
        Only a rendered check caught it.
        """
        slide = {
            "elements": [
                {"type": "bullets", "items": ["L1"], "column": "left", "y": 550},
                {"type": "bullets", "items": ["R1"], "column": "right", "y": 550},
            ]
        }
        left, right = _flow_slide(slide, PLAIN, 1920, 1080)[0]
        assert left["x"] == PLAIN.margin_x(1920)
        assert right["x"] > left["x"] + left["width"]
        assert left["y"] == right["y"] == 550  # the pinned y is honored
        assert left["width"] == right["width"] < PLAIN.content_width(1920) / 2

    def test_pinning_only_y_still_gets_the_flow_x(self):
        """Half-placed elements must not lose the other coordinate.

        A model asked for a 15-slide deck pinned `y` on two slides' titles
        and got x=0 (flush to the slide edge) while every other title sat at
        the style margin — the element had opted out of layout entirely.
        """
        slide = {
            "elements": [
                {"type": "title", "text": "T", "y": 60},
                {"type": "text", "text": "body", "x": 400},
            ]
        }
        title, body = _flow_slide(slide, PLAIN, 1920, 1080)[0]
        assert title["x"] == PLAIN.margin_x(1920)
        assert title["y"] == 60
        assert body["x"] == 400
        assert body["y"] > 60  # flowed below the pinned title, not left unset

    def test_explicit_position_passes_through_unflowed(self):
        slide = {"elements": [{"type": "text", "text": "t", "x": 10, "y": 20}]}
        placed, _ = _flow_slide(slide, PLAIN, 1920, 1080)
        el = placed[0]
        assert el["x"] == 10
        assert el["y"] == 20
        assert "width" not in el

    def test_panel_line_shape_are_never_flowed(self):
        slide = {
            "elements": [
                {"type": "panel", "x": 1, "y": 2, "width": 3, "height": 4},
                {"type": "line", "x1": 0, "y1": 0, "x2": 9, "y2": 9},
                {"type": "shape"},
            ]
        }
        placed, bottom = _flow_slide(slide, PLAIN, 1920, 1080)
        assert placed[0] == {"type": "panel", "x": 1, "y": 2, "width": 3, "height": 4}
        assert "x" not in placed[2]
        # nothing flowed: the estimate never moved past the top margin
        assert bottom == PLAIN.margin_top(1080) - PLAIN.gap(1080)

    def test_centered_title_gets_no_x(self):
        slide = {"elements": [{"type": "title", "text": "T", "centered": True}]}
        placed, _ = _flow_slide(slide, PLAIN, 1920, 1080)
        assert "x" not in placed[0]
        assert placed[0]["y"] == PLAIN.margin_top(1080)

    def test_image_table_chart_defaults(self):
        slide = {
            "elements": [
                {"type": "image", "path": "/x.png"},
                {"type": "table", "data": [["a", "b"], ["c", "d"]]},
                {"type": "chart", "chart_type": "bar"},
            ]
        }
        placed, _ = _flow_slide(slide, PLAIN, 1920, 1080)
        image, table, chart = placed
        assert image["width"] == PLAIN.content_width(1920) * 0.6
        assert table["height"] >= 80
        assert chart["height"] == min(1080 * 0.5, PLAIN.content_width(1920) * 0.55)


class TestParseCell:
    def test_formulas_stay_strings(self):
        assert _parse_cell("=SUM(A1)") == "=SUM(A1)"

    def test_whole_floats_become_ints(self):
        assert _parse_cell("24.0") == 24
        assert isinstance(_parse_cell("24.0"), int)

    def test_fractions_stay_floats(self):
        assert _parse_cell("1.5") == 1.5

    def test_text_stays_text(self):
        assert _parse_cell("abc") == "abc"
