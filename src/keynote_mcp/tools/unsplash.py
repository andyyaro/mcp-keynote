"""
Unsplash image tools
"""

import os
import tempfile
from typing import List, Optional

import aiofiles
import aiohttp
from mcp.types import TextContent, Tool

from ..utils import AppleScriptRunner, ParameterError, validate_slide_number


class UnsplashTools:
    """Unsplash image tools class"""
    
    def __init__(self):
        self.runner = AppleScriptRunner()

        self.api_key = os.getenv('UNSPLASH_KEY')
        if not self.api_key:
            raise ParameterError(
                "UNSPLASH_KEY environment variable not set. Configure it in your "
                "MCP client's server config to enable Unsplash tools."
            )

        self.base_url = "https://api.unsplash.com"
        self.headers = {
            "Authorization": f"Client-ID {self.api_key}",
            "Accept-Version": "v1"
        }

    def get_tools(self) -> List[Tool]:
        """Get all Unsplash image tools"""
        return [
            Tool(
                name="search_unsplash_images",
                description="Search Unsplash for images",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query"
                        },
                        "per_page": {
                            "type": "integer",
                            "description": "Results per page (1-30, default 10)",
                            "minimum": 1,
                            "maximum": 30
                        },
                        "orientation": {
                            "type": "string",
                            "description": "Image orientation (landscape/portrait/squarish)",
                            "enum": ["landscape", "portrait", "squarish"]
                        },
                        "order_by": {
                            "type": "string",
                            "description": "Sort order (relevant/latest/popular)",
                            "enum": ["relevant", "latest", "popular"]
                        }
                    },
                    "required": ["query"]
                }
            ),
            Tool(
                name="add_unsplash_image_to_slide",
                description="Search Unsplash and add an image to a slide",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "slide_number": {
                            "type": "integer",
                            "description": "Slide number"
                        },
                        "query": {
                            "type": "string",
                            "description": "Search query"
                        },
                        "image_index": {
                            "type": "integer",
                            "description": "Image index to select (0-9, default 0)",
                            "minimum": 0,
                            "maximum": 9
                        },
                        "orientation": {
                            "type": "string",
                            "description": "Image orientation (landscape/portrait/squarish)",
                            "enum": ["landscape", "portrait", "squarish"]
                        },
                        "x": {
                            "type": "number",
                            "description": "X coordinate (optional)"
                        },
                        "y": {
                            "type": "number",
                            "description": "Y coordinate (optional)"
                        },
                        "width": {
                            "type": "number",
                            "description": "Image width (optional)"
                        },
                        "height": {
                            "type": "number",
                            "description": "Image height (optional)"
                        }
                    },
                    "required": ["slide_number", "query"]
                }
            ),
            Tool(
                name="get_random_unsplash_image",
                description="Get a random Unsplash image and add it to a slide",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "slide_number": {
                            "type": "integer",
                            "description": "Slide number"
                        },
                        "query": {
                            "type": "string",
                            "description": "Search query (optional)"
                        },
                        "orientation": {
                            "type": "string",
                            "description": "Image orientation (landscape/portrait/squarish)",
                            "enum": ["landscape", "portrait", "squarish"]
                        },
                        "x": {
                            "type": "number",
                            "description": "X coordinate (optional)"
                        },
                        "y": {
                            "type": "number",
                            "description": "Y coordinate (optional)"
                        },
                        "width": {
                            "type": "number",
                            "description": "Image width (optional)"
                        },
                        "height": {
                            "type": "number",
                            "description": "Image height (optional)"
                        }
                    },
                    "required": ["slide_number"]
                }
            )
        ]
    
    async def search_unsplash_images(self, query: str, per_page: int = 10, orientation: Optional[str] = None, order_by: str = "relevant") -> List[TextContent]:
        """Search Unsplash images"""
        try:
            params = {
                "query": query,
                "per_page": min(per_page, 30),
                "order_by": order_by
            }
            
            if orientation:
                params["orientation"] = orientation
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/search/photos",
                    headers=self.headers,
                    params=params
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        return [TextContent(
                            type="text",
                            text=f"❌ Unsplash API error ({response.status}): {error_text}"
                        )]
                    
                    data = await response.json()
                    photos = data.get("results", [])
                    
                    if not photos:
                        return [TextContent(
                            type="text",
                            text=f"❌ No images found for '{query}'"
                        )]
                    
                    # Format search results
                    result_text = f"🔍 Found {len(photos)} images for '{query}':\n\n"
                    
                    for i, photo in enumerate(photos):
                        photographer = photo.get("user", {}).get("name", "Unknown")
                        description = photo.get("description") or photo.get("alt_description") or "No description"
                        width = photo.get("width", 0)
                        height = photo.get("height", 0)
                        likes = photo.get("likes", 0)
                        
                        result_text += f"[{i}] 📸 {description[:50]}{'...' if len(description) > 50 else ''}\n"
                        result_text += f"    👤 Photographer: {photographer}\n"
                        result_text += f"    📐 Size: {width}x{height}\n"
                        result_text += f"    ❤️ Likes: {likes}\n"
                        result_text += f"    🔗 Link: {photo.get('links', {}).get('html', '')}\n\n"
                    
                    return [TextContent(
                        type="text",
                        text=result_text
                    )]
                    
        except Exception as e:
            return [TextContent(
                type="text",
                text=f"❌ Image search failed: {str(e)}"
            )]
    
    async def add_unsplash_image_to_slide(self, slide_number: int, query: str, image_index: int = 0, 
                                        orientation: Optional[str] = None, x: Optional[float] = None, 
                                        y: Optional[float] = None, width: Optional[float] = None, 
                                        height: Optional[float] = None) -> List[TextContent]:
        """Search Unsplash images and add to slide"""
        try:
            validate_slide_number(slide_number)
            
            # Search images
            params = {
                "query": query,
                "per_page": max(image_index + 1, 10),
                "order_by": "relevant"
            }
            
            if orientation:
                params["orientation"] = orientation
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/search/photos",
                    headers=self.headers,
                    params=params
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        return [TextContent(
                            type="text",
                            text=f"❌ Unsplash API error ({response.status}): {error_text}"
                        )]
                    
                    data = await response.json()
                    photos = data.get("results", [])
                    
                    if not photos:
                        return [TextContent(
                            type="text",
                            text=f"❌ No images found for '{query}'"
                        )]
                    
                    if image_index >= len(photos):
                        return [TextContent(
                            type="text",
                            text=f"❌ Image index {image_index} out of range, found {len(photos)} images"
                        )]
                    
                    # Select image at specified index
                    selected_photo = photos[image_index]
                    
                    # Get image info
                    photographer = selected_photo.get("user", {}).get("name", "Unknown")
                    description = selected_photo.get("description") or selected_photo.get("alt_description") or "No description"

                    # Select appropriate image size (prefer regular)
                    image_url = selected_photo.get("urls", {}).get("regular")
                    if not image_url:
                        image_url = selected_photo.get("urls", {}).get("full")
                    
                    if not image_url:
                        return [TextContent(
                            type="text",
                            text="❌ Unable to get image download URL"
                        )]
                    
                    # Download image
                    temp_dir = tempfile.gettempdir()
                    image_filename = f"unsplash_{selected_photo.get('id', 'unknown')}.jpg"
                    image_path = os.path.join(temp_dir, image_filename)
                    
                    async with session.get(image_url) as img_response:
                        if img_response.status != 200:
                            return [TextContent(
                                type="text",
                                text=f"❌ Image download failed: HTTP {img_response.status}"
                            )]
                        
                        async with aiofiles.open(image_path, 'wb') as f:
                            async for chunk in img_response.content.iter_chunked(8192):
                                await f.write(chunk)
                    
                    # Add image to slide
                    await self._add_image_to_slide(slide_number, image_path, x, y, width, height)

                    # Record download stats (per Unsplash API requirements)
                    download_url = selected_photo.get("links", {}).get("download_location")
                    if download_url:
                        try:
                            async with session.get(download_url, headers=self.headers) as _:
                                pass  # Just trigger the download stat
                        except:
                            pass  # Ignore stats errors
                    
                    return [TextContent(
                        type="text",
                        text=f"✅ Successfully added image to slide {slide_number}\n"
                             f"📸 Image: {description[:50]}{'...' if len(description) > 50 else ''}\n"
                             f"👤 Photographer: {photographer}\n"
                             f"📁 Temp file: {image_path}"
                    )]
                    
        except Exception as e:
            return [TextContent(
                type="text",
                text=f"❌ Failed to add image: {str(e)}"
            )]
    
    async def get_random_unsplash_image(self, slide_number: int, query: Optional[str] = None, 
                                      orientation: Optional[str] = None, x: Optional[float] = None, 
                                      y: Optional[float] = None, width: Optional[float] = None, 
                                      height: Optional[float] = None) -> List[TextContent]:
        """Get a random Unsplash image and add to slide"""
        try:
            validate_slide_number(slide_number)
            
            params = {}
            if query:
                params["query"] = query
            if orientation:
                params["orientation"] = orientation
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/photos/random",
                    headers=self.headers,
                    params=params
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        return [TextContent(
                            type="text",
                            text=f"❌ Unsplash API error ({response.status}): {error_text}"
                        )]
                    
                    photo = await response.json()
                    
                    # Get image info
                    photographer = photo.get("user", {}).get("name", "Unknown")
                    description = photo.get("description") or photo.get("alt_description") or "No description"

                    # Select appropriate image size
                    image_url = photo.get("urls", {}).get("regular")
                    if not image_url:
                        image_url = photo.get("urls", {}).get("full")
                    
                    if not image_url:
                        return [TextContent(
                            type="text",
                            text="❌ Unable to get image download URL"
                        )]
                    
                    # Download image
                    temp_dir = tempfile.gettempdir()
                    image_filename = f"unsplash_random_{photo.get('id', 'unknown')}.jpg"
                    image_path = os.path.join(temp_dir, image_filename)
                    
                    async with session.get(image_url) as img_response:
                        if img_response.status != 200:
                            return [TextContent(
                                type="text",
                                text=f"❌ Image download failed: HTTP {img_response.status}"
                            )]
                        
                        async with aiofiles.open(image_path, 'wb') as f:
                            async for chunk in img_response.content.iter_chunked(8192):
                                await f.write(chunk)
                    
                    # Add image to slide
                    await self._add_image_to_slide(slide_number, image_path, x, y, width, height)

                    # Record download stats
                    download_url = photo.get("links", {}).get("download_location")
                    if download_url:
                        try:
                            async with session.get(download_url, headers=self.headers) as _:
                                pass
                        except:
                            pass
                    
                    return [TextContent(
                        type="text",
                        text=f"✅ Successfully added random image to slide {slide_number}\n"
                             f"📸 Image: {description[:50]}{'...' if len(description) > 50 else ''}\n"
                             f"👤 Photographer: {photographer}\n"
                             f"📁 Temp file: {image_path}"
                    )]
                    
        except Exception as e:
            return [TextContent(
                type="text",
                text=f"❌ Failed to get random image: {str(e)}"
            )]
    
    async def _add_image_to_slide(self, slide_number: int, image_path: str, x: Optional[float] = None, y: Optional[float] = None, width: Optional[float] = None, height: Optional[float] = None) -> None:
        """Add image to specified slide"""
        abs_path = os.path.abspath(image_path)

        set_position = (
            f"set position of newImage to {{{float(x)}, {float(y)}}}"
            if (x is not None and y is not None)
            else "-- default position"
        )
        set_width = (
            f"set width of newImage to {float(width)}" if width is not None else "-- default width"
        )
        set_height = (
            f"set height of newImage to {float(height)}"
            if height is not None
            else "-- default height"
        )

        self.runner.run(
            f"""
            on run argv
                set imageFile to POSIX file (item 1 of argv) as alias
                tell application "Keynote"
                    tell slide {slide_number} of front document
                        set newImage to make new image with properties {{file:imageFile}}
                        {set_position}
                        {set_width}
                        {set_height}
                    end tell
                end tell
            end run
            """,
            abs_path,
        ) 