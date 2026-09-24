"""theme_file on create_presentation and build_deck against a mocked runner:
a .kth is staged inside Keynote's container and removed afterwards."""

import json
import os
import subprocess

import pytest

_FS = "\x1f"


def _cp(cmd, stdout):
    return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=stdout, stderr="")


class TestThemeFile:
    @pytest.fixture
    def container(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        data = home / "Library/Containers/com.apple.Keynote/Data"
        data.mkdir(parents=True)
        monkeypatch.setenv("HOME", str(home))
        return data / "tmp"

    @pytest.fixture
    def kth(self, tmp_path):
        path = tmp_path / "Shared drives" / "Brand & Co.kth"
        path.parent.mkdir()
        path.write_bytes(b"PK fake theme")
        return path

    async def test_create_stages_copy_and_removes_it(
        self, presentation_tools, mock_subprocess_run, container, kth, tmp_path
    ):
        seen = {}

        def fake_run(cmd, **kwargs):
            script = kwargs.get("input", "")
            if "make new document with data" in script:
                staged = cmd[4]
                seen["staged"] = staged
                seen["existed"] = os.path.exists(staged)
                seen["argv"] = cmd[2:]
                return _cp(cmd, "Deck.key|theme file: Brand & Co.kth|first slide: Blank layout")
            return _cp(cmd, "true")

        mock_subprocess_run.side_effect = fake_run
        result = await presentation_tools.create_presentation(
            "Deck", theme_file=str(kth), save_path=str(tmp_path / "Deck.key")
        )
        assert seen["staged"].startswith(str(container))
        assert seen["existed"], "Keynote must be handed a copy that exists"
        assert not os.path.exists(seen["staged"]), "the staged copy is removed afterwards"
        assert "Brand & Co.kth" in seen["argv"]
        assert "theme file: Brand & Co.kth" in result[0].text

    async def test_copy_is_removed_when_keynote_fails(
        self, presentation_tools, mock_subprocess_run, container, kth, tmp_path
    ):
        def fake_run(cmd, **kwargs):
            if "make new document with data" in kwargs.get("input", ""):
                return subprocess.CompletedProcess(
                    args=cmd, returncode=1, stdout="", stderr="execution error: bad (-10000)"
                )
            return _cp(cmd, "true")

        mock_subprocess_run.side_effect = fake_run
        result = await presentation_tools.create_presentation(
            "Deck", theme_file=str(kth), save_path=str(tmp_path / "Deck.key")
        )
        assert result[0].text.startswith("Failed")
        assert os.listdir(container) == []

    @pytest.mark.parametrize(
        "kwargs, message",
        [
            ({"theme": "White", "theme_file": "/x.kth"}, "not both"),
            ({"theme_file": "/no/such/theme.kth"}, "does not exist"),
            ({"theme_file": "/etc/hosts"}, ".kth"),
        ],
    )
    async def test_bad_arguments_never_run(
        self, presentation_tools, mock_subprocess_run, kwargs, message
    ):
        result = await presentation_tools.create_presentation("Deck", **kwargs)
        assert message in result[0].text
        assert not mock_subprocess_run.called

    async def test_no_container_is_an_actionable_error(
        self, presentation_tools, mock_subprocess_run, kth, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("HOME", str(tmp_path / "empty-home"))
        mock_subprocess_run.return_value.stdout = "true"
        result = await presentation_tools.create_presentation(
            "Deck", theme_file=str(kth), save_path=str(tmp_path / "Deck.key")
        )
        assert "sandbox container was not found" in result[0].text

    async def test_build_deck_uses_the_themes_own_size(
        self, deck_tools, mock_subprocess_run, container, kth, tmp_path
    ):
        calls = []

        def fake_run(cmd, **kwargs):
            script = kwargs.get("input", "")
            calls.append((cmd, script))
            if "System Events" in script:
                return _cp(cmd, "true")
            if "make new document" in script:
                return _cp(cmd, f"deck.key{_FS}theme file: Brand & Co.kth{_FS}1024x768{_FS}Blank")
            if "save document docName" in script:
                return _cp(cmd, "1")
            return _cp(cmd, "")

        mock_subprocess_run.side_effect = fake_run
        spec = {
            "theme_file": str(kth),
            "save_path": str(tmp_path / "deck.key"),
            "slides": [{"elements": [{"type": "text", "text": "hi"}]}],
        }
        result = await deck_tools.build_deck(spec=spec)
        setup_cmd, setup = next(c for c in calls if "make new document" in c[1])
        assert "make new document with data (POSIX file themeFile)" in setup
        # no explicit size: the theme's own is kept, not the style default
        assert "if 0 > 0 then set width of newDoc" in setup
        assert setup_cmd[4].startswith(str(container))
        assert os.listdir(container) == []
        report = json.loads(result[0].text[result[0].text.index("{") :])
        assert report["size"] == "1024x768"

    async def test_build_deck_rejects_theme_and_theme_file(self, deck_tools, tmp_path):
        spec = {
            "theme": "White",
            "theme_file": "/x.kth",
            "save_path": str(tmp_path / "deck.key"),
            "slides": [{"elements": [{"type": "text", "text": "hi"}]}],
        }
        result = await deck_tools.build_deck(spec=spec)
        assert "not both" in result[0].text
