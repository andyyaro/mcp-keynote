"""build_deck / describe_deck against a mocked runner: session sequencing,
report parsing, per-element error isolation, and spec round-trip typing."""

import json
import subprocess

_FS = "\x1f"
_RS = "\x1e"


def _cp(cmd, stdout):
    return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=stdout, stderr="")


def _deck_side_effect(batch_stdout="", layouts="Blank|||Title & Bullets", calls=None):
    """Route each osascript call by its script content, mimicking the live
    session sequence: keynote-running check, setup, N batches, save."""

    def fake_run(cmd, **kwargs):
        script = kwargs.get("input", "")
        if calls is not None:
            calls.append((cmd, script))
        if "System Events" in script:
            return _cp(cmd, "true")
        if "make new document" in script:
            return _cp(cmd, f"deck.key{_FS}theme: White{_FS}{layouts}")
        if "close document" in script:
            return _cp(cmd, "")
        if "save document docName" in script:
            return _cp(cmd, "1")
        return _cp(cmd, batch_stdout)

    return fake_run


def _spec(tmp_path, **overrides):
    spec = {
        "save_path": str(tmp_path / "deck.key"),
        "slides": [{"elements": [{"type": "text", "text": "hello"}]}],
    }
    spec.update(overrides)
    return spec


class TestBuildDeckValidation:
    async def test_invalid_spec_reports_all_errors_without_touching_keynote(
        self, deck_tools, mock_subprocess_run
    ):
        result = await deck_tools.build_deck(
            spec={"slides": [{"elements": [{"type": "nope"}, {"type": "title"}]}]}
        )
        text = result[0].text
        assert "Spec validation failed" in text
        assert "2 problem(s)" in text
        assert "nothing was created" in text
        assert not mock_subprocess_run.called

    async def test_both_spec_and_markdown_fails(self, deck_tools, mock_subprocess_run):
        result = await deck_tools.build_deck(spec={"slides": [{}]}, markdown="# x")
        assert "only one of 'spec' or 'markdown'" in result[0].text
        assert not mock_subprocess_run.called

    async def test_neither_spec_nor_markdown_fails(self, deck_tools, mock_subprocess_run):
        result = await deck_tools.build_deck()
        assert "Pass either 'spec'" in result[0].text
        assert not mock_subprocess_run.called

    async def test_bad_on_exists_fails(self, deck_tools, mock_subprocess_run, tmp_path):
        result = await deck_tools.build_deck(spec=_spec(tmp_path, on_exists="clobber"))
        assert "on_exists must be" in result[0].text
        assert not mock_subprocess_run.called

    async def test_on_exists_error_refuses_existing_file(
        self, deck_tools, mock_subprocess_run, tmp_path
    ):
        (tmp_path / "deck.key").write_bytes(b"x")
        result = await deck_tools.build_deck(spec=_spec(tmp_path, on_exists="error"))
        assert "already exists" in result[0].text
        assert not mock_subprocess_run.called

    async def test_on_exists_unique_appends_counter(
        self, deck_tools, mock_subprocess_run, tmp_path
    ):
        (tmp_path / "deck.key").write_bytes(b"x")
        mock_subprocess_run.side_effect = _deck_side_effect("s1.e0|1|10,20|30,40\n")
        result = await deck_tools.build_deck(spec=_spec(tmp_path, on_exists="unique"))
        assert str(tmp_path / "deck-2.key") in result[0].text


class TestBuildDeckHappyPath:
    async def test_report_carries_settled_geometry_and_session_count(
        self, deck_tools, mock_subprocess_run, tmp_path
    ):
        calls = []
        mock_subprocess_run.side_effect = _deck_side_effect("s1.e0|1|100,200|300,50\n", calls=calls)
        result = await deck_tools.build_deck(spec=_spec(tmp_path))
        summary, _, raw_report = result[0].text.partition("\n")
        assert "Built 1-slide deck 'deck.key'" in summary
        assert "in 3 AppleScript sessions" in summary
        assert "(0 element error(s))" in summary
        report = json.loads(raw_report)
        assert report["document"] == "deck.key"
        assert report["path"] == str(tmp_path / "deck.key")
        assert report["slides"] == [
            {
                "slide": 1,
                "elements": [{"type": "text", "index": 1, "position": "100,200", "size": "300,50"}],
                "errors": [],
            }
        ]
        # exactly one setup, one batch, one save script hit osascript
        scripts = [s for _, s in calls]
        assert sum("make new document" in s for s in scripts) == 1
        assert sum("save document docName" in s for s in scripts) == 1

    async def test_slides_batch_five_per_session(self, deck_tools, mock_subprocess_run, tmp_path):
        spec = _spec(tmp_path)
        spec["slides"] = [{"elements": [{"type": "text", "text": f"s{i}"}]} for i in range(6)]
        mock_subprocess_run.side_effect = _deck_side_effect("")
        result = await deck_tools.build_deck(spec=spec)
        # 6 slides -> 2 batches -> setup + 2 + save = 4 sessions
        assert "in 4 AppleScript sessions" in result[0].text

    async def test_placeholder_and_notes_slides(self, deck_tools, mock_subprocess_run, tmp_path):
        spec = _spec(tmp_path)
        spec["slides"] = [
            {
                "title": "T",
                "body": "B",
                "notes": "remember",
                "skipped": True,
                "transition": {"effect": "push"},
                "elements": [],
            }
        ]
        calls = []
        mock_subprocess_run.side_effect = _deck_side_effect(
            "s1.ph|placeholders-set||\n", calls=calls
        )
        result = await deck_tools.build_deck(spec=spec)
        report = json.loads(result[0].text.partition("\n")[2])
        assert report["slides"][0]["placeholders"] == "set"
        batch = next(s for _, s in calls if "set out to" in s and "make new document" not in s)
        assert "set title showing to true" in batch
        assert "transition effect:push" in batch
        assert "set skipped of targetSlide to true" in batch

    async def test_markdown_source_builds(self, deck_tools, mock_subprocess_run, tmp_path):
        mock_subprocess_run.side_effect = _deck_side_effect("s1.e0|1|0,0|10,10\n")
        result = await deck_tools.build_deck(
            markdown="# Hello\n", save_path=str(tmp_path / "md.key")
        )
        assert "Built 1-slide deck" in result[0].text


class TestBuildDeckErrorIsolation:
    async def test_err_tokens_land_in_slide_errors(self, deck_tools, mock_subprocess_run, tmp_path):
        mock_subprocess_run.side_effect = _deck_side_effect("ERR|s1.e0|-10000|boom\n")
        result = await deck_tools.build_deck(spec=_spec(tmp_path))
        assert "(1 element error(s))" in result[0].text
        report = json.loads(result[0].text.partition("\n")[2])
        assert report["slides"][0]["errors"] == [{"element": "text", "error": "boom (-10000)"}]
        assert report["slides"][0]["elements"] == []

    async def test_unknown_layout_discards_fresh_document(
        self, deck_tools, mock_subprocess_run, tmp_path
    ):
        calls = []
        mock_subprocess_run.side_effect = _deck_side_effect(calls=calls)
        spec = _spec(tmp_path)
        spec["slides"][0]["layout"] = "Nope"
        result = await deck_tools.build_deck(spec=spec)
        text = result[0].text
        assert "Layout validation failed" in text
        assert "'Nope'" in text
        assert "discarded" in text
        assert any("close document" in s for _, s in calls)
        # no slide batch and no save ran after the failed validation
        assert not any("save document docName" in s for _, s in calls)

    async def test_runner_exception_in_batch_is_reported_per_slide(
        self, deck_tools, mock_subprocess_run, tmp_path
    ):
        def fake_run(cmd, **kwargs):
            script = kwargs.get("input", "")
            if "System Events" in script:
                return _cp(cmd, "true")
            if "make new document" in script:
                return _cp(cmd, f"deck.key{_FS}theme: White{_FS}Blank")
            if "save document docName" in script:
                return _cp(cmd, "1")
            return subprocess.CompletedProcess(
                args=cmd, returncode=1, stdout="", stderr="execution error: bad (-1728)"
            )

        mock_subprocess_run.side_effect = fake_run
        result = await deck_tools.build_deck(spec=_spec(tmp_path))
        report = json.loads(result[0].text.partition("\n")[2])
        (err,) = report["slides"][0]["errors"]
        assert err["element"] == "slide"
        assert "-1728" in err["error"]


class TestDescribeDeck:
    _HEAD = f"doc.key{_FS}White{_FS}1920{_FS}1080{_FS}1"
    _RECORDS = _RS.join(
        [
            # "D" delimits a slide: describe_deck now batches several slides
            # into one osascript session instead of one call per slide.
            f"D{_FS}1",
            f"L{_FS}Blank",
            f"K{_FS}true",
            f"X{_FS}fade through color{_FS}1.5{_FS}0.5{_FS}true",
            f"N{_FS}my notes",
            f"PT{_FS}Placeholder Title",
            f"PB{_FS}Placeholder Body",
            # Trailing field on every element record is its per-class
            # AppleScript index; text carries index THEN placeholder role.
            f"T{_FS}Hello{_FS}100{_FS}200{_FS}300{_FS}50{_FS}Helvetica{_FS}24{_FS}100,200,300{_FS}3{_FS}",
            f"I{_FS}img.png{_FS}10{_FS}20{_FS}30{_FS}40{_FS}1",
            f"S{_FS}shape text{_FS}1{_FS}2{_FS}3{_FS}4{_FS}80{_FS}1",
            f"B{_FS}1{_FS}0{_FS}5{_FS}6{_FS}7{_FS}8{_FS}Region\tQ1\nNorth\t120\n=SUM(B2)\t1.5{_FS}1",
            f"C{_FS}9{_FS}8{_FS}7{_FS}6{_FS}1",
            f"G{_FS}1{_FS}2{_FS}3{_FS}4{_FS}1",
        ]
    )

    def _wire(self, mock_run, records=None):
        def fake_run(cmd, **kwargs):
            script = kwargs.get("input", "")
            if "count of slides of targetDoc" in script:
                return _cp(cmd, self._HEAD)
            return _cp(cmd, records if records is not None else self._RECORDS)

        mock_run.side_effect = fake_run

    async def test_round_trips_every_record_kind(self, deck_tools, mock_subprocess_run):
        self._wire(mock_subprocess_run)
        result = await deck_tools.describe_deck()
        spec = json.loads(result[0].text)
        assert spec["title"] == "doc"
        assert spec["theme"] == "White"
        assert (spec["width"], spec["height"]) == (1920, 1080)
        (slide,) = spec["slides"]
        assert slide["layout"] == "Blank"
        assert slide["skipped"] is True
        assert slide["transition"] == {
            "effect": "fade_through_color",
            "duration": 1.5,
            "delay": 0.5,
            "automatic": True,
        }
        assert slide["notes"] == "my notes"
        assert slide["title"] == "Placeholder Title"
        assert slide["body"] == "Placeholder Body"
        text, image, shape, table, chart, line = slide["elements"]
        assert text == {
            "type": "text",
            "element_class": "text item",
            "index": 3,
            "text": "Hello",
            "x": 100.0,
            "y": 200.0,
            "width": 300.0,
            "height": 50.0,
            "font_name": "Helvetica",
            "font_size": 24.0,
            "color": "100,200,300",
        }
        # Every element carries the per-class index a consuming tool takes.
        for el in slide["elements"]:
            assert el["index"] >= 1, el
            assert el["element_class"] in {
                "text item",
                "image",
                "shape",
                "table",
                "chart",
                "line",
            }, el
        assert image["type"] == "image"
        assert image["path"] == "img.png"
        assert shape["type"] == "shape"
        assert shape["text"] == "shape text"
        assert shape["opacity"] == 80.0
        assert table["header_row"] is True
        assert table["header_column"] is False
        # cell typing round-trips: ints back to int, formulas stay strings
        assert table["data"] == [["Region", "Q1"], ["North", 120], ["=SUM(B2)", 1.5]]
        assert chart["chart_type"] is None
        assert "geometry only" in chart["note"]
        assert line == {
            "type": "line",
            "element_class": "line",
            "index": 1,
            "x1": 1.0,
            "y1": 2.0,
            "x2": 3.0,
            "y2": 4.0,
        }

    async def test_no_transition_effect_is_omitted(self, deck_tools, mock_subprocess_run):
        records = _RS.join(
            [
                f"D{_FS}1",
                f"L{_FS}Blank",
                f"K{_FS}false",
                f"X{_FS}no transition effect{_FS}0{_FS}0{_FS}false",
            ]
        )
        self._wire(mock_subprocess_run, records)
        spec = json.loads((await deck_tools.describe_deck())[0].text)
        (slide,) = spec["slides"]
        assert "transition" not in slide
        assert "skipped" not in slide

    async def test_runner_failure_reports_not_raises(self, deck_tools, mock_subprocess_run):
        mock_subprocess_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="execution error: nope (-1728)"
        )
        result = await deck_tools.describe_deck()
        assert result[0].text.startswith("Failed to describe deck")
