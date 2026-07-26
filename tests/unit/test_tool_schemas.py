"""Every tool advertises a well-formed JSON schema."""

import inspect

import pytest

from keynote_mcp.tools.content import ContentTools
from keynote_mcp.tools.deck import DeckTools
from keynote_mcp.tools.export import ExportTools
from keynote_mcp.tools.objects import ObjectTools
from keynote_mcp.tools.presentation import PresentationTools
from keynote_mcp.tools.slide import SlideTools
from keynote_mcp.tools.unsplash import UnsplashTools

_TOOL_CLASSES = (
    PresentationTools,
    SlideTools,
    ContentTools,
    ObjectTools,
    DeckTools,
    ExportTools,
    UnsplashTools,
)


def all_tools(monkeypatch):
    monkeypatch.setenv("UNSPLASH_KEY", "dummy-key-for-schema-tests")
    tools = []
    for cls in _TOOL_CLASSES:
        tools.extend(cls().get_tools())
    return tools


@pytest.fixture
def tools(monkeypatch):
    return all_tools(monkeypatch)


@pytest.fixture
def tools_with_owners(monkeypatch):
    """Every tool paired with the instance that implements it."""
    monkeypatch.setenv("UNSPLASH_KEY", "dummy-key-for-schema-tests")
    pairs = []
    for cls in _TOOL_CLASSES:
        inst = cls()
        pairs.extend((tool, inst) for tool in inst.get_tools())
    return pairs


def test_schema_properties_match_method_signature(tools_with_owners):
    """A schema property with no parameter, or a parameter with no schema
    property, is a defect in BOTH directions - and both shipped.

    Since 4.0.0 the dispatcher REJECTS unknown arguments, which turns a
    parameter missing from the schema into a capability nothing can reach:
    ``add_build_in``/``remove_build_in``/``add_builds_to_slide`` each grew a
    working ``doc_name`` that no caller could pass, while the CHANGELOG
    announced it. The other direction is worse than dead surface - it is a
    documented lie: ``describe_deck.include_text_runs`` was implemented and
    written up in TOOL_MATRIX.md, but absent from the schema, so passing it was
    an error. Nothing at the time compared the two.
    """
    for tool, inst in tools_with_owners:
        method = getattr(inst, tool.name, None)
        assert method is not None, f"{tool.name} has no implementing method"
        params = set(inspect.signature(method).parameters) - {"self"}
        props = set(tool.inputSchema.get("properties", {}))
        assert props - params == set(), (
            f"{tool.name}: schema advertises {sorted(props - params)}, which the "
            "method does not accept"
        )
        assert params - props == set(), (
            f"{tool.name}: {sorted(params - props)} are implemented but not in the "
            "schema, so the dispatcher rejects them and the capability is unreachable"
        )


def test_expected_tool_count(tools):
    # 59 at v3.0.0; +export_assets (Task 4) +styled_line (Task 5) = 61.
    assert len(tools) == 61


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


_SENTINELS = {
    "string": "__sentinel__",
    "integer": 7,
    "number": 7.5,
    "boolean": False,  # not the default of any boolean argument, so it must travel
    "array": ["__sentinel__"],
    "object": {"__sentinel__": 1},
}


@pytest.mark.asyncio
async def test_dispatch_forwards_every_schema_argument(monkeypatch, mock_subprocess_run):
    """A schema property the DISPATCHER never reads is dead surface too.

    The third way an argument goes missing, after the two in
    ``test_schema_properties_match_method_signature``: schema and method agree,
    but ``_dispatch`` does not pass it along, so it is accepted and silently
    dropped - the exact failure 4.0.0 set out to end at this boundary. Calls
    every tool with every argument set to a sentinel and asserts each one
    arrives.
    """
    from keynote_mcp.server import KeynoteMCPServer

    monkeypatch.setenv("UNSPLASH_KEY", "dummy-key-for-schema-tests")
    server = KeynoteMCPServer()

    for tool in server.all_tools():
        arguments = {
            prop: _SENTINELS[spec["type"]]
            for prop, spec in tool.inputSchema.get("properties", {}).items()
        }
        received: dict = {}

        async def recorder(_received=received, **kwargs):
            _received.update(kwargs)
            return []

        owner = next(
            inst
            for inst in (
                server.presentation_tools,
                server.slide_tools,
                server.content_tools,
                server.object_tools,
                server.deck_tools,
                server.export_tools,
                server.unsplash_tools,
            )
            if inst is not None and hasattr(inst, tool.name)
        )
        monkeypatch.setattr(owner, tool.name, recorder)
        await server._dispatch(tool.name, dict(arguments))

        dropped = sorted(k for k, v in arguments.items() if received.get(k, object()) != v)
        assert not dropped, f"{tool.name}: _dispatch never forwards {dropped}"
