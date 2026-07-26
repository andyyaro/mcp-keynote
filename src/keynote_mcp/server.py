"""Keynote-MCP server: controls Apple Keynote via AppleScript over MCP stdio.

stdout carries framed JSON-RPC only; all logging goes to stderr
(level via the KEYNOTE_MCP_LOG_LEVEL environment variable).
"""

import asyncio
import logging
import os
import sys
from collections.abc import Sequence
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import EmbeddedResource, ImageContent, TextContent, Tool

from .tools import (
    ContentTools,
    DeckTools,
    ExportTools,
    ObjectTools,
    PresentationTools,
    SlideTools,
    UnsplashTools,
)
from .utils import (
    SESSION,
    AppleScriptError,
    FileOperationError,
    KeynoteError,
    ParameterError,
)

logger = logging.getLogger(__name__)

# Arguments a caller plausibly invents for capabilities Keynote's AppleScript
# dictionary does not have. Silently dropping these is how a caller concludes
# the server can do something it cannot: PHASE 9 Task 0 traced the field
# report's "set_element_style CAN write shape fill" to exactly that - an
# unknown argument accepted, ignored, and reported as success. Each entry maps
# the invented argument to what the caller should actually reach for.
_UNSUPPORTED_ARG_HINTS: dict[str, str] = {
    "fill": "shape/text fill color is not writable by AppleScript",
    "fill_color": "shape/text fill color is not writable by AppleScript",
    "background_color": "shape/text fill color is not writable by AppleScript",
    "background_fill": "shape/text fill color is not writable by AppleScript",
    "color_fill": "shape/text fill color is not writable by AppleScript",
    "shape_type": "only rectangles exist; there is no `shape type` term",
    "corner_radius": "shapes have no corner-radius property",
    "stroke": "lines and shapes have no stroke properties at all",
    "stroke_color": "lines and shapes have no stroke properties at all",
    "stroke_width": "lines and shapes have no stroke properties at all",
    "line_color": "lines and shapes have no stroke properties at all",
    "line_width": "lines and shapes have no stroke properties at all",
    "dash": "lines and shapes have no stroke properties at all",
    "dash_pattern": "lines and shapes have no stroke properties at all",
    "arrowhead": "lines and shapes have no stroke properties at all",
    "start_arrow": "lines and shapes have no stroke properties at all",
    "end_arrow": "lines and shapes have no stroke properties at all",
    "shadow": "there is no shadow term on any iWork class",
    "border": "there is no border term on any iWork class",
    "z_order": "z-order is creation order and cannot be changed",
    "group": "grouping is a silent no-op in AppleScript",
    "alignment": "text alignment exists only on table ranges",
    "text_align": "text alignment exists only on table ranges",
    "bold": "there is no bold attribute; pass the bold face name as font_name",
    "italic": "there is no italic attribute; pass the italic face name as font_name",
}

# Where to send a caller whose invented argument names a real design need.
_UNSUPPORTED_ARG_ALTERNATIVES: dict[str, str] = {
    "fill": "add_colored_panel (rendered PNG, exact color) or set_element_opacity",
    "fill_color": "add_colored_panel (rendered PNG, exact color) or set_element_opacity",
    "background_color": "add_colored_panel, or add_table range styling for cell fills",
    "background_fill": "add_colored_panel (rendered PNG, exact color)",
    "color_fill": "add_colored_panel (rendered PNG, exact color)",
    "shape_type": "add_colored_panel for rectangles/rounded rectangles, or add_image",
    "corner_radius": "add_colored_panel, which takes a `radius`",
    "stroke": "styled_line, which renders the stroke to a transparent PNG",
    "stroke_color": "styled_line, which renders the stroke to a transparent PNG",
    "stroke_width": "styled_line, which renders the stroke to a transparent PNG",
    "line_color": "styled_line, which renders the stroke to a transparent PNG",
    "line_width": "styled_line, which renders the stroke to a transparent PNG",
    "dash": "styled_line, which takes a `dash` pattern",
    "dash_pattern": "styled_line, which takes a `dash` pattern",
    "arrowhead": "styled_line, which takes `start_arrow`/`end_arrow`",
    "start_arrow": "styled_line, which takes `start_arrow`/`end_arrow`",
    "end_arrow": "styled_line, which takes `start_arrow`/`end_arrow`",
    "z_order": "build_deck, where spec order IS paint order",
    "group": "build_deck, composing elements in paint order",
    "alignment": "add_title/add_subtitle `centered`, or add_table range styling",
    "text_align": "add_title/add_subtitle `centered`, or add_table range styling",
    "bold": "style_text_range with the bold PostScript face name",
    "italic": "style_text_range with the italic PostScript face name",
}


def _echo_resolved_document(
    result: Sequence[TextContent | ImageContent | EmbeddedResource],
) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
    """Append the document a call actually acted on to its reply.

    The field report's highest-value ask, and the cheapest: every reply names
    its target, so a call that landed on the wrong deck is self-evident instead
    of silently confident. ``screenshot_slide`` once returned "the export
    matches the editor view" for slides belonging to a presentation nobody had
    asked about, and nothing in the response gave it away.

    Applied centrally at the MCP entry point rather than in each of ~50 tools,
    so a new tool cannot forget it. Skipped when the reply already names the
    document (create/open say it themselves) or when no document was resolved.
    """
    doc = SESSION.last_resolved
    if not doc or not result:
        return result
    last = result[-1]
    if not isinstance(last, TextContent) or doc in last.text:
        return result
    return [*result[:-1], TextContent(type="text", text=f"{last.text}\n[document: {doc}]")]


def _configure_logging() -> None:
    level_name = os.environ.get("KEYNOTE_MCP_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        stream=sys.stderr,
        level=level,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )


class KeynoteMCPServer:
    """Keynote MCP Server"""

    def __init__(self) -> None:
        self.server: Server = Server("keynote-mcp")
        self.presentation_tools = PresentationTools()
        self.slide_tools = SlideTools()
        self.content_tools = ContentTools()
        self.export_tools = ExportTools()
        self.object_tools = ObjectTools()
        self.deck_tools = DeckTools()
        self._arg_names: dict[str, set[str]] | None = None
        self.unsplash_tools: UnsplashTools | None
        try:
            self.unsplash_tools = UnsplashTools()
        except ParameterError as e:
            logger.info("Unsplash tools disabled: %s", e)
            self.unsplash_tools = None

        self._register_handlers()

    def all_tools(self) -> list[Tool]:
        """Every tool this server exposes, with schemas closed to unknown args.

        ``additionalProperties: False`` is stamped on centrally rather than
        authored into each ``get_tools()``, so a new tool cannot forget it.
        """
        tools: list[Tool] = []
        tools.extend(self.presentation_tools.get_tools())
        tools.extend(self.slide_tools.get_tools())
        tools.extend(self.content_tools.get_tools())
        tools.extend(self.object_tools.get_tools())
        tools.extend(self.deck_tools.get_tools())
        tools.extend(self.export_tools.get_tools())
        if self.unsplash_tools:
            tools.extend(self.unsplash_tools.get_tools())
        for tool in tools:
            tool.inputSchema.setdefault("additionalProperties", False)
        return tools

    def _accepted_args(self, name: str) -> set[str] | None:
        """Argument names a tool accepts, or None if the tool is unknown."""
        if self._arg_names is None:
            self._arg_names = {
                t.name: set(t.inputSchema.get("properties", {})) for t in self.all_tools()
            }
        return self._arg_names.get(name)

    def _reject_unknown_arguments(self, name: str, arguments: dict[str, Any]) -> str | None:
        """Return an error message if ``arguments`` contains names the tool
        does not accept, else None.

        A dropped argument is worse than a rejected one: the tool reports
        success and the caller believes a capability exists. See
        ``_UNSUPPORTED_ARG_HINTS``.
        """
        accepted = self._accepted_args(name)
        if accepted is None:
            return None  # unknown tool - _dispatch reports that itself
        unknown = sorted(set(arguments) - accepted)
        if not unknown:
            return None

        lines = [
            f"Unrecognized argument(s) for {name}: {', '.join(unknown)}. "
            "The call was REJECTED and nothing was changed - this server never "
            "silently ignores an argument, because that reads as success."
        ]
        for arg in unknown:
            hint = _UNSUPPORTED_ARG_HINTS.get(arg)
            if hint:
                alt = _UNSUPPORTED_ARG_ALTERNATIVES.get(arg)
                lines.append(
                    f"  - `{arg}`: not a capability of Keynote's AppleScript "
                    f"dictionary ({hint})." + (f" Use {alt}." if alt else "")
                )
        lines.append(f"{name} accepts: {', '.join(sorted(accepted)) or '(no arguments)'}.")
        return "\n".join(lines)

    def _register_handlers(self) -> None:
        """Register MCP handlers"""

        # The mcp 1.x registration decorators are untyped; v2 replaces them
        # with constructor params (see docs/MCP_V2_MIGRATION.md).
        @self.server.list_tools()  # type: ignore[no-untyped-call, untyped-decorator]
        async def list_tools() -> list[Tool]:
            """List all available tools"""
            return self.all_tools()

        @self.server.call_tool()  # type: ignore[untyped-decorator]
        async def call_tool(
            name: str, arguments: dict[str, Any]
        ) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
            """Call a tool. Never lets an exception escape - every failure
            comes back as an error text result so the server stays alive."""
            try:
                rejection = self._reject_unknown_arguments(name, arguments or {})
                if rejection:
                    return [TextContent(type="text", text=f"Parameter error: {rejection}")]
                # Cleared first so a tool that touches no document (list_
                # presentations, get_available_themes) cannot echo a stale name
                # left by the previous call.
                SESSION.note_resolved("")
                result = await self._dispatch(name, arguments or {})
                return _echo_resolved_document(result)
            except KeyError as e:
                return [
                    TextContent(
                        type="text",
                        text=f"Parameter error: missing required parameter {e}",
                    )
                ]
            except (TypeError, ValueError) as e:
                return [TextContent(type="text", text=f"Parameter error: {e}")]
            except ParameterError as e:
                return [TextContent(type="text", text=f"Parameter error: {e}")]
            except AppleScriptError as e:
                return [TextContent(type="text", text=f"AppleScript error: {e}")]
            except FileOperationError as e:
                return [TextContent(type="text", text=f"File operation error: {e}")]
            except KeynoteError as e:
                return [TextContent(type="text", text=f"Keynote error: {e}")]
            except Exception as e:
                logger.exception("Unhandled error in tool %s", name)
                return [TextContent(type="text", text=f"Unknown error: {e}")]

    async def _dispatch(
        self, name: str, arguments: dict[str, Any]
    ) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        doc_name = arguments.get("doc_name", "")

        # Presentation management tools
        if name == "create_presentation":
            return await self.presentation_tools.create_presentation(
                title=arguments["title"],
                theme=arguments.get("theme", ""),
                save_path=arguments.get("save_path", ""),
            )
        elif name == "open_presentation":
            return await self.presentation_tools.open_presentation(file_path=arguments["file_path"])
        elif name == "save_presentation":
            return await self.presentation_tools.save_presentation(
                doc_name=doc_name, save_path=arguments.get("save_path", "")
            )
        elif name == "close_presentation":
            return await self.presentation_tools.close_presentation(
                doc_name=doc_name,
                should_save=arguments.get("should_save", True),
            )
        elif name == "list_presentations":
            return await self.presentation_tools.list_presentations()
        elif name == "set_presentation_theme":
            return await self.presentation_tools.set_presentation_theme(
                theme_name=arguments["theme_name"], doc_name=doc_name
            )
        elif name == "get_presentation_info":
            return await self.presentation_tools.get_presentation_info(doc_name=doc_name)
        elif name == "get_available_themes":
            return await self.presentation_tools.get_available_themes()
        elif name == "get_slide_size":
            return await self.presentation_tools.get_slide_size(doc_name=doc_name)

        # Slide operation tools
        elif name == "add_slide":
            return await self.slide_tools.add_slide(
                doc_name=doc_name,
                position=arguments.get("position", 0),
                layout=arguments.get("layout", "Blank"),
            )
        elif name == "delete_slide":
            return await self.slide_tools.delete_slide(
                slide_number=arguments["slide_number"], doc_name=doc_name
            )
        elif name == "duplicate_slide":
            return await self.slide_tools.duplicate_slide(
                slide_number=arguments["slide_number"],
                doc_name=doc_name,
                new_position=arguments.get("new_position", 0),
            )
        elif name == "move_slide":
            return await self.slide_tools.move_slide(
                from_position=arguments["from_position"],
                to_position=arguments["to_position"],
                doc_name=doc_name,
            )
        elif name == "get_slide_count":
            return await self.slide_tools.get_slide_count(doc_name=doc_name)
        elif name == "select_slide":
            return await self.slide_tools.select_slide(
                slide_number=arguments["slide_number"], doc_name=doc_name
            )
        elif name == "set_slide_layout":
            return await self.slide_tools.set_slide_layout(
                slide_number=arguments["slide_number"],
                layout=arguments["layout"],
                doc_name=doc_name,
            )
        elif name == "get_slide_info":
            return await self.slide_tools.get_slide_info(
                slide_number=arguments["slide_number"], doc_name=doc_name
            )
        elif name == "get_available_layouts":
            return await self.slide_tools.get_available_layouts(doc_name=doc_name)

        # Content management tools
        elif name == "add_text_box":
            return await self.content_tools.add_text_box(
                slide_number=arguments["slide_number"],
                text=arguments["text"],
                x=arguments.get("x"),
                y=arguments.get("y"),
                font_size=arguments.get("font_size"),
                font_name=arguments.get("font_name", ""),
                color=arguments.get("color", ""),
                width=arguments.get("width"),
                height=arguments.get("height"),
                doc_name=doc_name,
            )
        elif name == "add_title":
            return await self.content_tools.add_title(
                slide_number=arguments["slide_number"],
                title=arguments["title"],
                x=arguments.get("x"),
                y=arguments.get("y"),
                font_size=arguments.get("font_size"),
                font_name=arguments.get("font_name", ""),
                color=arguments.get("color", ""),
                centered=arguments.get("centered", False),
                doc_name=doc_name,
            )
        elif name == "add_subtitle":
            return await self.content_tools.add_subtitle(
                slide_number=arguments["slide_number"],
                subtitle=arguments["subtitle"],
                x=arguments.get("x"),
                y=arguments.get("y"),
                font_size=arguments.get("font_size"),
                font_name=arguments.get("font_name", ""),
                color=arguments.get("color", ""),
                centered=arguments.get("centered", False),
                doc_name=doc_name,
            )
        elif name == "add_bullet_list":
            return await self.content_tools.add_bullet_list(
                slide_number=arguments["slide_number"],
                items=arguments["items"],
                x=arguments.get("x"),
                y=arguments.get("y"),
                font_size=arguments.get("font_size"),
                font_name=arguments.get("font_name", ""),
                doc_name=doc_name,
            )
        elif name == "add_numbered_list":
            return await self.content_tools.add_numbered_list(
                slide_number=arguments["slide_number"],
                items=arguments["items"],
                x=arguments.get("x"),
                y=arguments.get("y"),
                font_size=arguments.get("font_size"),
                font_name=arguments.get("font_name", ""),
                doc_name=doc_name,
            )
        elif name == "add_code_block":
            return await self.content_tools.add_code_block(
                slide_number=arguments["slide_number"],
                code=arguments["code"],
                x=arguments.get("x"),
                y=arguments.get("y"),
                font_size=arguments.get("font_size"),
                font_name=arguments.get("font_name", ""),
                color=arguments.get("color", ""),
                doc_name=doc_name,
            )
        elif name == "add_quote":
            return await self.content_tools.add_quote(
                slide_number=arguments["slide_number"],
                quote=arguments["quote"],
                x=arguments.get("x"),
                y=arguments.get("y"),
                font_size=arguments.get("font_size"),
                font_name=arguments.get("font_name", ""),
                doc_name=doc_name,
            )
        elif name == "set_slide_content":
            return await self.content_tools.set_slide_content(
                slide_number=arguments["slide_number"],
                title=arguments.get("title"),
                body=arguments.get("body"),
                doc_name=doc_name,
            )
        elif name == "add_image":
            return await self.content_tools.add_image(
                slide_number=arguments["slide_number"],
                image_path=arguments["image_path"],
                x=arguments.get("x"),
                y=arguments.get("y"),
                width=arguments.get("width"),
                height=arguments.get("height"),
                description=arguments.get("description", ""),
                doc_name=doc_name,
            )
        elif name == "get_slide_content":
            return await self.content_tools.get_slide_content(
                slide_number=arguments["slide_number"], doc_name=doc_name
            )
        elif name == "edit_text_item":
            return await self.content_tools.edit_text_item(
                slide_number=arguments["slide_number"],
                item_index=arguments["item_index"],
                new_text=arguments["new_text"],
                doc_name=doc_name,
            )
        elif name == "delete_element":
            return await self.content_tools.delete_element(
                slide_number=arguments["slide_number"],
                element_type=arguments["element_type"],
                element_index=arguments["element_index"],
                doc_name=doc_name,
            )
        elif name == "move_element":
            return await self.content_tools.move_element(
                slide_number=arguments["slide_number"],
                element_type=arguments["element_type"],
                element_index=arguments["element_index"],
                x=arguments["x"],
                y=arguments["y"],
                doc_name=doc_name,
            )
        elif name == "resize_element":
            return await self.content_tools.resize_element(
                slide_number=arguments["slide_number"],
                element_type=arguments["element_type"],
                element_index=arguments["element_index"],
                width=arguments["width"],
                height=arguments["height"],
                doc_name=doc_name,
            )
        elif name == "get_speaker_notes":
            return await self.content_tools.get_speaker_notes(
                slide_number=arguments["slide_number"], doc_name=doc_name
            )
        elif name == "set_speaker_notes":
            return await self.content_tools.set_speaker_notes(
                slide_number=arguments["slide_number"],
                notes=arguments["notes"],
                doc_name=doc_name,
            )
        elif name == "clear_slide":
            return await self.content_tools.clear_slide(
                slide_number=arguments["slide_number"], doc_name=doc_name
            )
        elif name == "set_element_opacity":
            return await self.content_tools.set_element_opacity(
                slide_number=arguments["slide_number"],
                element_type=arguments["element_type"],
                element_index=arguments["element_index"],
                opacity=arguments["opacity"],
                doc_name=doc_name,
            )
        elif name == "add_build_in":
            return await self.content_tools.add_build_in(
                slide_number=arguments["slide_number"],
                element_type=arguments["element_type"],
                element_index=arguments["element_index"],
                effect=arguments.get("effect", "Appear"),
                delivery=arguments.get("delivery", "By Paragraph"),
            )
        elif name == "remove_build_in":
            return await self.content_tools.remove_build_in(
                slide_number=arguments["slide_number"],
                element_type=arguments["element_type"],
                element_index=arguments["element_index"],
            )
        elif name == "add_builds_to_slide":
            return await self.content_tools.add_builds_to_slide(
                slide_number=arguments["slide_number"],
                element_indices=arguments["element_indices"],
                element_type=arguments.get("element_type", "text"),
                effect=arguments.get("effect", "Appear"),
            )
        elif name == "add_shape":
            return await self.content_tools.add_shape(
                slide_number=arguments["slide_number"],
                x=arguments.get("x"),
                y=arguments.get("y"),
                width=arguments.get("width"),
                height=arguments.get("height"),
                opacity=arguments.get("opacity"),
                doc_name=doc_name,
            )

        # Native objects, styling, and declarative deck tools
        elif name == "add_table":
            return await self.object_tools.add_table(
                slide_number=arguments["slide_number"],
                data=arguments["data"],
                x=arguments.get("x"),
                y=arguments.get("y"),
                width=arguments.get("width"),
                height=arguments.get("height"),
                header_row=arguments.get("header_row", True),
                header_column=arguments.get("header_column", False),
                font_name=arguments.get("font_name", ""),
                font_size=arguments.get("font_size"),
                column_widths=arguments.get("column_widths"),
                style=arguments.get("style", ""),
                doc_name=doc_name,
            )
        elif name == "add_chart":
            return await self.object_tools.add_chart(
                slide_number=arguments["slide_number"],
                chart_type=arguments["chart_type"],
                row_names=arguments["row_names"],
                column_names=arguments["column_names"],
                data=arguments["data"],
                group_by=arguments.get("group_by", "row"),
                x=arguments.get("x"),
                y=arguments.get("y"),
                width=arguments.get("width"),
                height=arguments.get("height"),
                doc_name=doc_name,
            )
        elif name == "add_line":
            return await self.object_tools.add_line(
                slide_number=arguments["slide_number"],
                x1=arguments["x1"],
                y1=arguments["y1"],
                x2=arguments["x2"],
                y2=arguments["y2"],
                doc_name=doc_name,
            )
        elif name == "add_colored_panel":
            return await self.object_tools.add_colored_panel(
                slide_number=arguments["slide_number"],
                x=arguments["x"],
                y=arguments["y"],
                width=arguments["width"],
                height=arguments["height"],
                color=arguments.get("color", ""),
                radius=arguments.get("radius"),
                opacity=arguments.get("opacity", 100),
                style=arguments.get("style", ""),
                doc_name=doc_name,
            )
        elif name == "style_text_range":
            return await self.object_tools.style_text_range(
                slide_number=arguments["slide_number"],
                item_index=arguments["item_index"],
                start=arguments["start"],
                end=arguments["end"],
                unit=arguments.get("unit", "characters"),
                color=arguments.get("color", ""),
                font_name=arguments.get("font_name", ""),
                font_size=arguments.get("font_size"),
                doc_name=doc_name,
            )
        elif name == "replace_image":
            return await self.object_tools.replace_image(
                slide_number=arguments["slide_number"],
                image_index=arguments["image_index"],
                image_path=arguments["image_path"],
                doc_name=doc_name,
            )
        elif name == "set_element_style":
            return await self.object_tools.set_element_style(
                slide_number=arguments["slide_number"],
                element_type=arguments["element_type"],
                element_index=arguments["element_index"],
                rotation=arguments.get("rotation"),
                reflection_showing=arguments.get("reflection_showing"),
                reflection_value=arguments.get("reflection_value"),
                locked=arguments.get("locked"),
                doc_name=doc_name,
            )
        elif name == "set_slide_transition":
            return await self.slide_tools.set_slide_transition(
                slide_number=arguments["slide_number"],
                effect=arguments["effect"],
                duration=arguments.get("duration", 1.0),
                delay=arguments.get("delay", 0.0),
                automatic=arguments.get("automatic", False),
                doc_name=doc_name,
            )
        elif name == "set_slide_skipped":
            return await self.slide_tools.set_slide_skipped(
                slide_number=arguments["slide_number"],
                skipped=arguments["skipped"],
                doc_name=doc_name,
            )
        elif name == "set_slide_size":
            return await self.presentation_tools.set_slide_size(
                width=arguments["width"],
                height=arguments["height"],
                doc_name=doc_name,
            )
        elif name == "set_document_settings":
            return await self.presentation_tools.set_document_settings(
                slide_numbers_showing=arguments.get("slide_numbers_showing"),
                auto_loop=arguments.get("auto_loop"),
                auto_play=arguments.get("auto_play"),
                auto_restart=arguments.get("auto_restart"),
                maximum_idle_duration=arguments.get("maximum_idle_duration"),
                doc_name=doc_name,
            )
        elif name == "build_deck":
            return await self.deck_tools.build_deck(
                spec=arguments.get("spec"),
                markdown=arguments.get("markdown", ""),
                save_path=arguments.get("save_path", ""),
                style=arguments.get("style", ""),
            )
        elif name == "describe_deck":
            return await self.deck_tools.describe_deck(
                doc_name=doc_name,
                slide_range=arguments.get("slide_range", ""),
                element_types=arguments.get("element_types"),
                detail=arguments.get("detail", "full"),
                round_coordinates=arguments.get("round_coordinates", True),
            )

        # Export and screenshot tools
        elif name == "screenshot_slide":
            return await self.export_tools.screenshot_slide(
                slide_number=arguments["slide_number"],
                output_path=arguments["output_path"],
                format=arguments.get("format", "png"),
                doc_name=doc_name,
            )
        elif name == "export_pdf":
            return await self.export_tools.export_pdf(
                output_path=arguments["output_path"],
                layout=arguments.get("layout", "slides"),
                image_quality=arguments.get("image_quality", "best"),
                include_skipped=arguments.get("include_skipped", False),
                doc_name=doc_name,
            )
        elif name == "export_presentation":
            return await self.export_tools.export_presentation(
                format=arguments["format"],
                output_path=arguments["output_path"],
                movie_format=arguments.get("movie_format", "1080p"),
                image_format=arguments.get("image_format", "png"),
                include_skipped=arguments.get("include_skipped", False),
                doc_name=doc_name,
            )

        # Unsplash image tools
        elif name in (
            "search_unsplash_images",
            "add_unsplash_image_to_slide",
            "get_random_unsplash_image",
        ):
            if not self.unsplash_tools:
                return [
                    TextContent(
                        type="text",
                        text=(
                            "Unsplash tools are not available: set the UNSPLASH_KEY "
                            "environment variable in your MCP client config."
                        ),
                    )
                ]
            if name == "search_unsplash_images":
                return await self.unsplash_tools.search_unsplash_images(
                    query=arguments["query"],
                    per_page=arguments.get("per_page", 10),
                    orientation=arguments.get("orientation"),
                    order_by=arguments.get("order_by", "relevant"),
                )
            elif name == "add_unsplash_image_to_slide":
                return await self.unsplash_tools.add_unsplash_image_to_slide(
                    slide_number=arguments["slide_number"],
                    query=arguments["query"],
                    image_index=arguments.get("image_index", 0),
                    orientation=arguments.get("orientation"),
                    x=arguments.get("x"),
                    y=arguments.get("y"),
                    width=arguments.get("width"),
                    height=arguments.get("height"),
                )
            else:
                return await self.unsplash_tools.get_random_unsplash_image(
                    slide_number=arguments["slide_number"],
                    query=arguments.get("query"),
                    orientation=arguments.get("orientation"),
                    x=arguments.get("x"),
                    y=arguments.get("y"),
                    width=arguments.get("width"),
                    height=arguments.get("height"),
                )

        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    async def run(self) -> None:  # pragma: no cover - exercised via subprocess stdio tests
        """Start the server on stdio."""
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options(),
            )


async def _async_main() -> None:  # pragma: no cover - exercised via subprocess stdio tests
    """Async entry point."""
    server = KeynoteMCPServer()
    await server.run()


def main() -> None:  # pragma: no cover - exercised via subprocess stdio tests
    """Sync entry point for console_scripts."""
    _configure_logging()
    asyncio.run(_async_main())


if __name__ == "__main__":
    main()
