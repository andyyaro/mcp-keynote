"""Deck spec validation, the markdown dialect compiler, auto-flow layout, and
table-cell round-trip typing. All pure functions - no osascript involved."""

from keynote_mcp.tools.deck import (
    _flow_slide,
    _parse_attrs,
    _parse_cell,
    markdown_to_spec,
    tolerated_keys,
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


class TestUnknownKeysAreRejected:
    """Unknown keys in the spec were silently ignored at ALL THREE levels.

    Same failure class 4.0.0 fixed at the tool-argument boundary, still live in
    the largest model-authored input the server takes: a deck with a mistyped
    `layuot`, an invented `fill_color` and a plausible `font` built with zero
    errors, and only the render showed it.
    """

    def test_unknown_deck_key(self):
        errors = validate_spec({"widht": 1920, "slides": [{"elements": []}]})
        assert any("spec.widht" in e and "Did you mean 'width'" in e for e in errors)
        assert any("the deck accepts:" in e for e in errors)

    def test_unknown_slide_key(self):
        errors = validate_spec({"slides": [{"layuot": "Blank", "elements": []}]})
        assert any("slides[0].layuot" in e and "Did you mean 'layout'" in e for e in errors)
        assert any("a slide accepts:" in e for e in errors)

    def test_unknown_element_key(self):
        errors = validate_spec(_element({"type": "text", "text": "x", "centred": True}))
        assert any(".centred" in e and "Did you mean 'centered'" in e for e in errors)
        assert any("an element of type 'text' accepts:" in e for e in errors)

    def test_unknown_transition_key(self):
        errors = validate_spec(
            {"slides": [{"elements": [], "transition": {"effect": "push", "speed": 2}}]}
        )
        assert any("transition.speed" in e for e in errors)

    def test_invented_capability_gets_the_real_reason(self):
        """Not a typo - a capability Keynote does not have. Says so, and where
        to go instead, from the same table the argument boundary uses."""
        errors = validate_spec(_element({"type": "text", "text": "x", "fill_color": "#f00"}))
        joined = "\n".join(errors)
        assert "not writable by AppleScript" in joined
        assert "add_colored_panel" in joined

    def test_key_valid_on_another_type_is_still_rejected(self):
        """`centered` does something on a title and nothing on an image. Being
        a real key SOMEWHERE is what makes this one hard to notice."""
        errors = validate_spec(_element({"type": "image", "path": __file__, "centered": True}))
        assert any(".centered" in e for e in errors)
        assert not validate_spec(_element({"type": "title", "text": "x", "centered": True}))

    def test_good_spec_still_validates(self):
        assert validate_spec({"title": "t", "slides": [{"elements": []}]}) == []


# One realistic describe_deck payload, key-for-key as _describe_slides emits it:
# every read-only field, every element class, the placeholder in both of its
# reported forms. This is the spec format's own output, so it MUST validate -
# strict unknown-key rejection is worthless if it rejects the round trip.
DESCRIBED = {
    "title": "deck",
    "theme": "Black",
    "width": 1920,
    "height": 1080,
    "slide_count": 1,
    "not_reported": {"z_order": "NOT reported and NOT recoverable."},
    "slides": [
        {
            "slide": 1,
            "layout": "Title & Subtitle",
            "skipped": True,
            "transition": {
                "effect": "push",
                "duration": 1.0,
                "delay": 0.0,
                "automatic": False,
            },
            "notes": "say hello",
            "title": "Heading",
            "groups": {"count": 2, "note": "made by hand"},
            "elements": [
                {
                    "type": "text",
                    "element_class": "text item",
                    "index": 1,
                    "placeholder": "title",
                    "text": "Heading",
                    "x": 100,
                    "y": 100,
                    "width": 800,
                    "height": 90,
                    "font_name": "LibreCaslonCondensed-Medium",
                    "font_family": "LibreCaslon-Condensed",
                    "font_weight": "Medium",
                    "font_style": "Normal",
                    "font_size": 69,
                    "color": "#830041",
                    "color_65535": "33410,0,16705",
                    "rotation": 0,
                    "opacity": 100,
                    "fill_type": "no fill",
                    "runs": [
                        {"start": 1, "end": 4, "color": "#000000", "color_65535": "0,0,0"},
                        {"start": 5, "end": 7, "color": "#830041", "color_65535": "33410,0,16705"},
                    ],
                },
                {
                    "type": "panel",
                    "element_class": "image",
                    "index": 1,
                    "rendered": True,
                    "description": "colored panel",
                    "x": 0,
                    "y": 0,
                    "width": 400,
                    "height": 200,
                    "color": "#EFA3A0",
                    "radius": 12,
                    "opacity": 100,
                    "rotation": 0,
                },
                {
                    "type": "styled_line",
                    "element_class": "image",
                    "index": 2,
                    "rendered": True,
                    "description": "styled line (dotted, #000000)",
                    "x1": 10,
                    "y1": 10,
                    "x2": 200,
                    "y2": 10,
                    "color": "#000000",
                    "stroke_width": 2.0,
                    "dash": "dotted",
                    "start_arrow": False,
                    "end_arrow": True,
                },
                {
                    "type": "shape",
                    "element_class": "shape",
                    "index": 1,
                    "x": 5,
                    "y": 5,
                    "width": 50,
                    "height": 50,
                    "opacity": 60,
                    "rotation": 45,
                    "fill_type": "color fill",
                    "reflection_showing": False,
                    "locked": False,
                },
                {
                    "type": "table",
                    "element_class": "table",
                    "index": 1,
                    "header_row": True,
                    "header_column": False,
                    "x": 0,
                    "y": 300,
                    "width": 600,
                    "height": 200,
                    "data": [["a", "b"], [1, "=SUM(A1)"]],
                },
                {
                    "type": "line",
                    "element_class": "line",
                    "index": 1,
                    "x1": 1,
                    "y1": 2,
                    "x2": 3,
                    "y2": 4,
                    "rotation": 0,
                },
            ],
        }
    ],
}


class TestDescribeDeckOutputRebuilds:
    def test_a_full_description_validates(self):
        """The live harness found two keys this list was missing - a decoded
        panel carries `rendered` and the image `description` Keynote holds for
        it - and the failure mode was the round trip refusing its own output."""
        assert validate_spec(DESCRIBED) == []

    def test_chart_geometry_only_is_still_rejected(self):
        """describe_deck returns chart_type null because Keynote exposes no
        chart data. Rebuilding as-is must FAIL, not build an empty chart."""
        spec = {
            "slides": [
                {
                    "elements": [
                        {
                            "type": "chart",
                            "element_class": "chart",
                            "index": 1,
                            "chart_type": None,
                            "note": "chart data is not readable via AppleScript",
                            "x": 0,
                            "y": 0,
                            "width": 10,
                            "height": 10,
                        }
                    ]
                }
            ]
        }
        errors = validate_spec(spec)
        assert any("chart_type" in e for e in errors)

    def test_unwritable_keys_are_reported_not_dropped(self):
        """Tolerating a key so the round trip works is only honest if the
        build says which ones it could not write."""
        reported = tolerated_keys(DESCRIBED)
        assert "rotation" in reported
        assert "locked" in reported or "reflection_showing" in reported
        assert "groups" in reported

    def test_a_clean_spec_reports_nothing_unwritable(self):
        assert tolerated_keys({"title": "t", "slides": [{"elements": []}]}) == []


class TestRunAuthoring:
    """build_deck could not author runs, so a tri-colour title needed three
    follow-up style_text_range calls and a described deck lost its runs on
    rebuild - describe->build fidelity being the point of the format."""

    def _title(self, runs, text="Building A Secure Client Data Hub"):
        return _element({"type": "title", "text": text, "runs": runs})

    def test_runs_validate(self):
        assert (
            validate_spec(
                self._title(
                    [
                        {"start": 1, "end": 10, "color": "#000000"},
                        {"start": 12, "end": 17, "color": "#830041"},
                        {"start": 19, "end": 33, "color": "#F09490"},
                    ]
                )
            )
            == []
        )

    def test_run_past_the_end_of_the_text_is_rejected(self):
        """`characters 5 thru 400` is a runtime error one element deep in a
        batched build. Caught here so nothing is created."""
        errors = validate_spec(self._title([{"start": 5, "end": 400, "color": "#000"}]))
        assert any("but the text is 33 character(s) long" in e for e in errors)

    def test_backwards_run_is_rejected(self):
        errors = validate_spec(self._title([{"start": 9, "end": 2, "color": "#000"}]))
        assert any("runs[0].end" in e for e in errors)

    def test_run_that_styles_nothing_is_rejected(self):
        errors = validate_spec(self._title([{"start": 1, "end": 4}]))
        assert any("styles nothing" in e for e in errors)

    def test_unknown_run_key_is_rejected(self):
        errors = validate_spec(self._title([{"start": 1, "end": 4, "bold": True}]))
        assert any("a text run" in e for e in errors)

    def test_describe_deck_run_shape_is_accepted_verbatim(self):
        """The read side reports font_family/weight/style and color_65535 next
        to each run. They are derived, so they must not fail validation."""
        assert (
            validate_spec(
                self._title(
                    [
                        {
                            "start": 1,
                            "end": 8,
                            "font_name": "LibreCaslonCondensed-Medium",
                            "font_family": "LibreCaslon-Condensed",
                            "font_weight": "Medium",
                            "font_style": "Normal",
                            "font_size": 69.0,
                            "color": "#830041",
                            "color_65535": "33410,0,16705",
                        }
                    ]
                )
            )
            == []
        )

    def test_runs_only_on_text_bearing_types(self):
        errors = validate_spec(_element({"type": "image", "path": __file__, "runs": []}))
        assert any(".runs" in e for e in errors)


class TestRunFragment:
    def _lines(self, el, style=PLAIN):
        from keynote_mcp.tools.deck import _element_fragment
        from keynote_mcp.tools.fragments import Argv

        argv = Argv()
        argv.ref("Doc")
        return _element_fragment(el, "s1.e0", argv, style, "/tmp"), argv

    def test_runs_are_written_after_the_text_is_reset_and_before_position(self):
        """Both halves matter: re-setting `object text` discards every run, and
        a run that changes size re-triggers auto-fit, which keeps the box's
        vertical CENTRE fixed - so a position set earlier drifts."""
        lines, _ = self._lines(
            {
                "type": "title",
                "text": "Secure Data Hub",
                "x": 100,
                "y": 461,
                "font_size": 69,
                "runs": [{"start": 8, "end": 11, "color": "#830041", "font_size": 40}],
            }
        )
        reset = max(i for i, ln in enumerate(lines) if ln.startswith("set object text of newItem"))
        run = next(i for i, ln in enumerate(lines) if "characters 8 thru 11" in ln)
        position = next(i for i, ln in enumerate(lines) if ln.startswith("set position of newItem"))
        assert reset < run < position

    def test_colors_are_interpolated_as_validated_numbers(self):
        lines, _ = self._lines(
            {"type": "text", "text": "abcdef", "runs": [{"start": 1, "end": 3, "color": "#830041"}]}
        )
        assert any(
            "set color of characters 1 thru 3 of object text of newItem to {33667, 0, 16705}" in ln
            for ln in lines
        )

    def test_a_quote_shifts_offsets_past_the_curly_quote_it_adds(self):
        """The builder wraps a quote in typographic quotes, so the caller's
        character 1 is Keynote's character 2. Runs address the text the caller
        wrote."""
        lines, _ = self._lines(
            {
                "type": "quote",
                "text": "abcdef",
                "runs": [{"start": 1, "end": 6, "color": "#000000"}],
            }
        )
        assert any("characters 2 thru 7" in ln for ln in lines)

    def test_palette_names_resolve_inside_a_run(self):
        style = BUILTIN_STYLES["sdh"]
        name = sorted(style.palette)[0]
        lines, _ = self._lines(
            {
                "type": "text",
                "text": "abcdef",
                "runs": [{"start": 1, "end": 3, "color": f"@{name}"}],
            },
            style,
        )
        assert any("set color of characters 1 thru 3" in ln for ln in lines)
        assert not any("@" in ln for ln in lines)
