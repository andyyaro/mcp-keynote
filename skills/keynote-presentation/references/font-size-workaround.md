# Font Size — No Workaround Needed (kept for history)

## Current behavior (server ≥ 2.2)

Large fonts need NO workaround. `add_title` / `add_subtitle` / `add_text_box`
apply the font size in the same call that creates the item, let Keynote's
auto-fit size the box to the rendered text (verified live at 96/150/300/500pt),
re-set the text as insurance, and return the settled geometry in the reply.
Keynote wraps lines that would outgrow the slide.

`centered=true` (add_title / add_subtitle) centers the rendered text exactly:
the auto-fit box hugs the text, so centering the box centers the text
(pixel-verified within 4pt at 24/48/96pt). Do not pass a manual `width`
when you want centering — a wider box leaves the left-aligned text inside it
off-center.

## If you still see 1-2 characters (old server only)

That was the v1 flow: the item was created at the default box size and the
font applied in a later call, truncating the stored text. Fix on old servers:

```yaml
get_slide_content(slide_number=1)          # find the index and truncated text
resize_element(..., width=900, height=140) # make room
edit_text_item(..., new_text="Keynote MCP")# restore the text
```

On a current server, seeing this means the MCP server is running old code —
restart it (/mcp or restart the session).
