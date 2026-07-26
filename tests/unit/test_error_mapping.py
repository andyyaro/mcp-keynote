"""Error mapping: osascript stderr becomes typed, actionable exceptions."""

import pytest

from keynote_mcp.utils.error_handler import (
    AppleScriptError,
    FileOperationError,
    ParameterError,
    handle_applescript_error,
    parse_color,
    validate_coordinates,
    validate_dimensions,
    validate_element_type,
    validate_file_path,
    validate_index,
    validate_number,
    validate_slide_number,
)


class TestAppleScriptErrorMapping:
    def test_empty_stderr_does_not_raise(self):
        handle_applescript_error("")
        handle_applescript_error("   \n")

    def test_1743_names_the_automation_pane(self):
        stderr = "execution error: Not authorized to send Apple events to Keynote. (-1743)"
        with pytest.raises(AppleScriptError) as exc:
            handle_applescript_error(stderr)
        message = str(exc.value)
        assert "Automation" in message
        assert "System Settings" in message
        assert "Privacy & Security" in message
        assert "-1743" in message

    def test_1728_is_actionable(self):
        stderr = "execution error: Keynote got an error: Can't get slide 99 of document 1. (-1728)"
        with pytest.raises(AppleScriptError) as exc:
            handle_applescript_error(stderr)
        message = str(exc.value)
        assert "-1728" in message
        assert "get_slide_count" in message

    def test_1719_invalid_index_is_not_found(self):
        # Keynote 14.5 reports out-of-range slide indices exactly like this
        # (with a curly quote), verified live.
        stderr = (
            "30:63: execution error: Keynote got an error: "
            "Can’t get slide 99 of document 1. Invalid index. (-1719)"
        )
        with pytest.raises(AppleScriptError) as exc:
            handle_applescript_error(stderr)
        message = str(exc.value)
        assert "get_slide_count" in message
        assert "Accessibility" not in message

    def test_assistive_access_names_accessibility_pane(self):
        stderr = "execution error: osascript is not allowed assistive access. (-25211)"
        with pytest.raises(AppleScriptError) as exc:
            handle_applescript_error(stderr)
        message = str(exc.value)
        assert "Accessibility" in message
        assert "System Settings" in message

    def test_600_keynote_not_running(self):
        stderr = "execution error: Keynote got an error: Application isn't running. (-600)"
        with pytest.raises(AppleScriptError) as exc:
            handle_applescript_error(stderr)
        assert "not running" in str(exc.value)

    def test_1712_event_timeout(self):
        stderr = "execution error: Keynote got an error: AppleEvent timed out. (-1712)"
        with pytest.raises(AppleScriptError) as exc:
            handle_applescript_error(stderr)
        assert "modal dialog" in str(exc.value)

    def test_file_not_found_maps_to_file_error(self):
        with pytest.raises(FileOperationError):
            handle_applescript_error("error: the file was not found somewhere")

    def test_unknown_error_still_raises(self):
        with pytest.raises(AppleScriptError):
            handle_applescript_error("execution error: something novel (-9999)")


class TestValidators:
    def test_slide_number_valid(self):
        assert validate_slide_number(3) == 3

    @pytest.mark.parametrize("bad", [None, 0, -1, 1.5, "2", True])
    def test_slide_number_invalid(self, bad):
        with pytest.raises(ParameterError):
            validate_slide_number(bad)

    def test_slide_number_exceeds_max(self):
        with pytest.raises(ParameterError):
            validate_slide_number(10, max_slides=5)

    def test_index_valid(self):
        assert validate_index(1) == 1

    @pytest.mark.parametrize("bad", [0, -3, "1", True])
    def test_index_invalid(self, bad):
        with pytest.raises(ParameterError):
            validate_index(bad)

    def test_coordinates_defaults(self):
        assert validate_coordinates(None, None) == (0.0, 0.0)
        assert validate_coordinates(10, None) == (10.0, 0.0)

    @pytest.mark.parametrize("bad", [-1, "5", True])
    def test_coordinates_invalid(self, bad):
        with pytest.raises(ParameterError):
            validate_coordinates(bad, 0)

    def test_number_bounds(self):
        assert validate_number(50, "opacity", 0, 100) == 50.0
        with pytest.raises(ParameterError):
            validate_number(101, "opacity", 0, 100)
        with pytest.raises(ParameterError):
            validate_number("50", "opacity", 0, 100)

    def test_dimensions(self):
        assert validate_dimensions(10, 20) == (10.0, 20.0)
        with pytest.raises(ParameterError):
            validate_dimensions(0, 20)
        with pytest.raises(ParameterError):
            validate_dimensions(10, -5)

    def test_element_type(self):
        assert validate_element_type("text") == "text"
        with pytest.raises(ParameterError):
            validate_element_type("movie")

    def test_file_path(self):
        assert validate_file_path("  /tmp/x.key ") == "/tmp/x.key"
        for bad in ("", "   ", None):
            with pytest.raises(ParameterError):
                validate_file_path(bad)


class TestParseColor:
    def test_empty_is_none(self):
        assert parse_color("") is None

    def test_valid(self):
        assert parse_color("65535,0,128") == (65535, 0, 128)
        assert parse_color(" 1 , 2 , 3 ") == (1, 2, 3)

    def test_hex_rrggbb(self):
        # 0-255 channels widen to 0-65535 via *257 (0xFF -> 0xFFFF)
        assert parse_color("#16294A") == (0x16 * 257, 0x29 * 257, 0x4A * 257)
        assert parse_color("#FFFFFF") == (65535, 65535, 65535)
        assert parse_color("#000000") == (0, 0, 0)

    def test_hex_shorthand_rgb(self):
        assert parse_color("#FFF") == (65535, 65535, 65535)
        assert parse_color("#a1c") == parse_color("#aa11cc")

    @pytest.mark.parametrize(
        "bad",
        [
            "65535,0",
            "1,2,3,4",
            "a,b,c",
            "65536,0,0",
            "-1,0,0",
            '0,0,0} & (do shell script "true")',
            "0,0,0\ntell app",
            "#12345",
            "#GGHHII",
            "#",
            '#FFF" & (do shell script "true")',
        ],
    )
    def test_invalid(self, bad):
        with pytest.raises(ParameterError):
            parse_color(bad)
