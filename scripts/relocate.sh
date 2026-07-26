#!/usr/bin/env bash
# relocate.sh — move this repo from ~/Downloads/mcp-keynote to ~/dev/mcp-keynote
# and re-register the keynote-mcp server at the new path.
#
# Run this OUTSIDE any Claude Code session that has the repo as its working
# directory (and outside any running keynote-mcp server): both hold the old
# path.
#
#   ~/Downloads/mcp-keynote/scripts/relocate.sh

set -euo pipefail

SRC="${HOME}/Downloads/mcp-keynote"
DST="${HOME}/dev/mcp-keynote"

if [ ! -d "${SRC}" ]; then
  echo "Refusing: ${SRC} does not exist (already moved?)" >&2
  exit 1
fi
if [ -e "${DST}" ]; then
  echo "Refusing: ${DST} already exists — will not overwrite. Move or remove it first." >&2
  exit 1
fi
if [ -n "$(git -C "${SRC}" status --porcelain)" ]; then
  echo "Refusing: git tree at ${SRC} is dirty. Commit or stash first:" >&2
  git -C "${SRC}" status --short >&2
  exit 1
fi

cd "${HOME}"
mkdir -p "${HOME}/dev"
mv "${SRC}" "${DST}"
echo "Moved ${SRC} -> ${DST}"

# Re-register the MCP server at the new path. Remove may fail if it was
# already unregistered; that must not abort the re-add.
claude mcp remove keynote-mcp || echo "note: keynote-mcp was not registered; adding fresh"
claude mcp add keynote-mcp -- uv --directory "${DST}" run keynote-mcp

echo
echo "claude mcp list:"
LIST="$(claude mcp list)"
printf '%s\n' "${LIST}"
if ! printf '%s' "${LIST}" | grep -q "keynote-mcp"; then
  echo "Verification FAILED: keynote-mcp missing from 'claude mcp list'" >&2
  exit 1
fi
echo
echo "Done. Repo now lives at ${DST}; start your next session there."
