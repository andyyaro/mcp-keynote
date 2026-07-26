"""Behavior of the capability-expansion tool methods (slide transitions and
skipping, slide size, document settings, whole-presentation export) with a
mocked runner."""

from tests.unit.test_tool_behavior import last_script


class TestSetSlideTransition:
    async def test_script_contains_mapped_effect_literal(self, slide_tools, mock_subprocess_run):
        mock_subprocess_run.return_value.stdout = "magic move|2.0"
        result = await slide_tools.set_slide_transition(1, "magic_move", duration=2)
        script = last_script(mock_subprocess_run)
        assert "transition effect:magic move" in script
        assert "magic_move" not in script
        assert "Set slide 1 transition to 'magic move' (2.0s, on click)" in result[0].text

    async def test_automatic_reports_delay(self, slide_tools, mock_subprocess_run):
        mock_subprocess_run.return_value.stdout = "push|1.0"
        result = await slide_tools.set_slide_transition(2, "push", delay=3, automatic=True)
        assert "automatic after 3s" in result[0].text
        assert "automatic transition:true" in last_script(mock_subprocess_run)

    async def test_unknown_effect_never_runs(self, slide_tools, mock_subprocess_run):
        result = await slide_tools.set_slide_transition(1, "teleport")
        assert "Failed to set slide transition" in result[0].text
        assert "Unknown transition effect" in result[0].text
        assert not mock_subprocess_run.called


class TestSetSlideSkipped:
    async def test_exists_guard_and_state_report(self, slide_tools, mock_subprocess_run):
        mock_subprocess_run.return_value.stdout = "true"
        result = await slide_tools.set_slide_skipped(3, True)
        script = last_script(mock_subprocess_run)
        assert "if not (exists slide 3 of targetDoc)" in script
        assert "set skipped of slide 3 of targetDoc to true" in script
        assert "Slide 3 is now skipped" in result[0].text

    async def test_unskip(self, slide_tools, mock_subprocess_run):
        mock_subprocess_run.return_value.stdout = "false"
        result = await slide_tools.set_slide_skipped(3, False)
        assert "not skipped" in result[0].text

    async def test_bad_slide_number_never_runs(self, slide_tools, mock_subprocess_run):
        result = await slide_tools.set_slide_skipped(0, True)
        assert "Failed to set slide skipped" in result[0].text
        assert not mock_subprocess_run.called


class TestSetSlideSize:
    async def test_bounds_validation_never_runs(self, presentation_tools, mock_subprocess_run):
        for bad in ((100, 1080), (1920, 100), (20000, 1080)):
            result = await presentation_tools.set_slide_size(*bad)
            assert "Failed to set slide size" in result[0].text
        assert not mock_subprocess_run.called

    async def test_happy_path_reads_back_size(self, presentation_tools, mock_subprocess_run):
        mock_subprocess_run.return_value.stdout = "1024x768"
        result = await presentation_tools.set_slide_size(1024, 768)
        script = last_script(mock_subprocess_run)
        assert "set width of targetDoc to 1024" in script
        assert "set height of targetDoc to 768" in script
        assert "Slide size is now 1024x768 pt" in result[0].text
        assert "re-check element geometry" in result[0].text


class TestSetDocumentSettings:
    async def test_nothing_to_set_never_runs(self, presentation_tools, mock_subprocess_run):
        result = await presentation_tools.set_document_settings()
        assert "nothing to set" in result[0].text
        assert not mock_subprocess_run.called

    async def test_partial_settings_only_touch_requested_props(
        self, presentation_tools, mock_subprocess_run
    ):
        result = await presentation_tools.set_document_settings(
            auto_loop=True, maximum_idle_duration=60
        )
        script = last_script(mock_subprocess_run)
        assert "set auto loop of targetDoc to true" in script
        assert "set maximum idle duration of targetDoc to 60" in script
        assert "auto play" not in script
        assert "slide numbers" not in script
        assert "auto loop=true, maximum idle duration=60s" in result[0].text

    async def test_bad_idle_duration_never_runs(self, presentation_tools, mock_subprocess_run):
        result = await presentation_tools.set_document_settings(maximum_idle_duration=0)
        assert "Failed to set document settings" in result[0].text
        assert not mock_subprocess_run.called


class TestExportPdfValidation:
    async def test_invalid_layout_never_runs(self, export_tools, mock_subprocess_run):
        result = await export_tools.export_pdf("/tmp/x.pdf", layout="poster")
        assert "Failed to export PDF" in result[0].text
        assert "Invalid layout" in result[0].text
        assert not mock_subprocess_run.called

    async def test_invalid_quality_never_runs(self, export_tools, mock_subprocess_run):
        result = await export_tools.export_pdf("/tmp/x.pdf", image_quality="ultra")
        assert "Invalid image_quality" in result[0].text
        assert not mock_subprocess_run.called

    async def test_notes_layout_literal_in_script(self, export_tools, mock_subprocess_run):
        result = await export_tools.export_pdf(
            "/tmp/x.pdf", layout="slides_with_notes", include_skipped=True
        )
        script = last_script(mock_subprocess_run)
        assert "export style:SlideWithNotes" in script
        assert "skipped slides:true" in script
        assert "(slides_with_notes layout)" in result[0].text


class TestExportPresentation:
    async def test_invalid_format_never_runs(self, export_tools, mock_subprocess_run):
        result = await export_tools.export_presentation("pdf", "/tmp/x.pdf")
        assert "Failed to export presentation" in result[0].text
        assert "Invalid format" in result[0].text
        assert not mock_subprocess_run.called

    async def test_invalid_movie_format_never_runs(self, export_tools, mock_subprocess_run):
        result = await export_tools.export_presentation("movie", "/tmp/x.m4v", movie_format="480p")
        assert "Invalid movie_format" in result[0].text
        assert not mock_subprocess_run.called

    async def test_invalid_image_format_never_runs(self, export_tools, mock_subprocess_run):
        result = await export_tools.export_presentation("images", "/tmp/x", image_format="bmp")
        assert "Invalid image_format" in result[0].text
        assert not mock_subprocess_run.called

    async def test_movie_gets_extended_timeout_and_extension(
        self, export_tools, mock_subprocess_run, tmp_path
    ):
        result = await export_tools.export_presentation("movie", str(tmp_path / "deck"))
        assert mock_subprocess_run.call_args.kwargs["timeout"] == 600.0
        script = last_script(mock_subprocess_run)
        assert "movie format:format1080p" in script
        assert f"{tmp_path}/deck.m4v" in result[0].text

    async def test_pptx_path_gets_extension_appended(
        self, export_tools, mock_subprocess_run, tmp_path
    ):
        result = await export_tools.export_presentation("pptx", str(tmp_path / "deck"))
        assert f"{tmp_path}/deck.pptx" in result[0].text
        assert "as Microsoft PowerPoint" in last_script(mock_subprocess_run)
        assert mock_subprocess_run.call_args.kwargs["timeout"] == 120.0
        # mocked run produced no file - the honesty warning must say so
        assert "WARNING: output not found" in result[0].text

    async def test_images_script_contains_format_literal(
        self, export_tools, mock_subprocess_run, tmp_path
    ):
        result = await export_tools.export_presentation(
            "images", str(tmp_path / "out"), image_format="jpeg"
        )
        script = last_script(mock_subprocess_run)
        assert "image format:JPEG" in script
        assert "skipped slides:false" in script
        assert "as slide images" in script
        assert "(jpeg per slide)" in result[0].text
