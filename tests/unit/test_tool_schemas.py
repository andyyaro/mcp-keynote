"""Every tool advertises a well-formed JSON schema."""

import pytest

from keynote_mcp.tools.content import ContentTools
from keynote_mcp.tools.deck import DeckTools
from keynote_mcp.tools.export import ExportTools
from keynote_mcp.tools.objects import ObjectTools
from keynote_mcp.tools.presentation import PresentationTools
from keynote_mcp.tools.slide import SlideTools
from keynote_mcp.tools.unsplash import UnsplashTools


def all_tools(monkeypatch):
    monkeypatch.setenv("UNSPLASH_KEY", "dummy-key-for-schema-tests")
    tools = []
    for cls in (
        PresentationTools,
        SlideTools,
        ContentTools,
        ObjectTools,
        DeckTools,
        ExportTools,
        UnsplashTools,
    ):
        tools.extend(cls().get_tools())
    return tools


@pytest.fixture
def tools(monkeypatch):
    return all_tools(monkeypatch)


def test_expected_tool_count(tools):
    assert len(tools) == 59


def test_tool_names_unique(tools):
    names = [t.name for t in tools]
    assert len(names) == len(set(names)), f"duplicate tool names: {names}"


def test_every_tool_has_description(tools):
    for tool in tools:
        assert tool.description and len(tool.description) > 10, tool.name


def test_schemas_are_well_formed_objects(tools):
    for tool in tools:
        schema = tool.inputSchema
        assert schema["type"] == "object", tool.name
        assert isinstance(schema["properties"], dict), tool.name
        for prop_name, prop in schema["properties"].items():
            assert "type" in prop, f"{tool.name}.{prop_name} missing type"
            assert "description" in prop, f"{tool.name}.{prop_name} missing description"


def test_required_fields_exist_in_properties(tools):
    for tool in tools:
        schema = tool.inputSchema
        required = schema.get("required", [])
        for field in required:
            assert field in schema["properties"], f"{tool.name} requires unknown field {field}"


def test_removed_tools_stay_removed(tools):
    names = {t.name for t in tools}
    assert "get_presentation_resolution" not in names, (
        "get_presentation_resolution was removed as a duplicate of get_slide_size"
    )
    assert "template" not in (PresentationTools().get_tools()[0].inputSchema["properties"]), (
        "create_presentation.template was removed as dead schema surface"
    )


def test_enum_fields_are_constrained(tools):
    by_name = {t.name: t for t in tools}
    for tool_name in ("delete_element", "move_element", "resize_element", "set_element_opacity"):
        prop = by_name[tool_name].inputSchema["properties"]["element_type"]
        assert set(prop["enum"]) == {"text", "image", "shape", "table"}, tool_name
    for tool_name in ("add_build_in", "remove_build_in"):
        prop = by_name[tool_name].inputSchema["properties"]["element_type"]
        assert set(prop["enum"]) == {"text", "image", "shape"}, tool_name


def test_unsplash_requires_key(monkeypatch):
    from keynote_mcp.utils import ParameterError

    monkeypatch.delenv("UNSPLASH_KEY", raising=False)
    with pytest.raises(ParameterError):
        UnsplashTools()
