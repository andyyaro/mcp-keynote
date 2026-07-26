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

from .tools import ContentTools, ExportTools, PresentationTools, SlideTools, UnsplashTools
from .utils import (
    AppleScriptError,
    FileOperationError,
    KeynoteError,
    ParameterError,
)

logger = logging.getLogger(__name__)


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
        self.unsplash_tools: UnsplashTools | None
        try:
            self.unsplash_tools = UnsplashTools()
        except ParameterError as e:
            logger.info("Unsplash tools disabled: %s", e)
            self.unsplash_tools = None

        self._register_handlers()

    def _register_handlers(self) -> None:
        """Register MCP handlers"""

        @self.server.list_tools()
        async def list_tools() -> list[Tool]:
            """List all available tools"""
            tools = []
            tools.extend(self.presentation_tools.get_tools())
            tools.extend(self.slide_tools.get_tools())
            tools.extend(self.content_tools.get_tools())
            tools.extend(self.export_tools.get_tools())
            if self.unsplash_tools:
                tools.extend(self.unsplash_tools.get_tools())
            return tools

        @self.server.call_tool()
        async def call_tool(
            name: str, arguments: dict[str, Any]
        ) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
            """Call a tool. Never lets an exception escape - every failure
            comes back as an error text result so the server stays alive."""
            try:
                return await self._dispatch(name, arguments or {})
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
            except Exception as e:  # noqa: BLE001 - last-resort process guard
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
            return await self.presentation_tools.open_presentation(
                file_path=arguments["file_path"]
            )
        elif name == "save_presentation":
            return await self.presentation_tools.save_presentation(doc_name=doc_name)
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
                output_path=arguments["output_path"], doc_name=doc_name
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

    async def run(self) -> None:
        """Start the server on stdio."""
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options(),
            )


async def _async_main() -> None:
    """Async entry point."""
    server = KeynoteMCPServer()
    await server.run()


def main() -> None:
    """Sync entry point for console_scripts."""
    _configure_logging()
    asyncio.run(_async_main())


if __name__ == "__main__":
    main()
