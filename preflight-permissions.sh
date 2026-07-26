#!/usr/bin/env bash
# preflight-permissions.sh
#
# Triggers every macOS permission dialog that Claude Code will need while
# forking/modernizing the Keynote MCP server, so you can grant them all in one
# sitting and then walk away.
#
# RUN THIS IN THE SAME TERMINAL APP you will run Claude Code in. macOS attributes
# Apple Events and screen capture to the *responsible process* — which is your
# terminal emulator, not python, not uv, not claude. Granting from Terminal.app
# and then running Claude Code in iTerm means you granted nothing.
#
#   chmod +x preflight-permissions.sh && ./preflight-permissions.sh

set -uo pipefail

SCRATCH="${HOME}/Downloads/mcp-keynote/.scratch"
BOLD=$'\033[1m'; DIM=$'\033[2m'; GRN=$'\033[32m'; RED=$'\033[31m'; YLW=$'\033[33m'; RST=$'\033[0m'

ok()   { printf "  ${GRN}✓${RST} %s\n" "$1"; }
bad()  { printf "  ${RED}✗${RST} %s\n" "$1"; }
warn() { printf "  ${YLW}!${RST} %s\n" "$1"; }
hdr()  { printf "\n${BOLD}%s${RST}\n" "$1"; }
pane() { open "x-apple.systempreferences:com.apple.preference.security?$1" 2>/dev/null || true; }

pause() { printf "\n${DIM}  ↳ press return when you've granted it${RST} "; read -r _; }

# ── Identify the responsible process ────────────────────────────────────────────
case "${TERM_PROGRAM:-unknown}" in
  Apple_Terminal) TERM_APP="Terminal";      TERM_BID="com.apple.Terminal" ;;
  iTerm.app)      TERM_APP="iTerm2";        TERM_BID="com.googlecode.iterm2" ;;
  ghostty)        TERM_APP="Ghostty";       TERM_BID="com.mitchellh.ghostty" ;;
  WarpTerminal)   TERM_APP="Warp";          TERM_BID="dev.warp.Warp-Stable" ;;
  vscode)         TERM_APP="VS Code";       TERM_BID="com.microsoft.VSCode" ;;
  Hyper)          TERM_APP="Hyper";         TERM_BID="co.zeit.hyper" ;;
  *)              TERM_APP="${TERM_PROGRAM:-your terminal}"; TERM_BID="" ;;
esac

hdr "Responsible process"
printf "  Every permission below will be recorded against: ${BOLD}%s${RST}\n" "$TERM_APP"
printf "  ${DIM}Start Claude Code from this same app or none of this counts.${RST}\n"

mkdir -p "$SCRATCH"

# ── 0. Keynote first-run dialogs ────────────────────────────────────────────────
# A "What's New" sheet or an iCloud sign-in prompt will silently block every
# scripted command. Clear them by hand, once, before anything else.
hdr "0 · Keynote first-run state"
open -a Keynote 2>/dev/null || { bad "Keynote not found in /Applications"; exit 1; }
printf "  Keynote is launching. Dismiss any 'What's New', iCloud, or theme-chooser\n"
printf "  dialogs, then leave it running.\n"
pause

# ── 1. Automation: terminal → Keynote ───────────────────────────────────────────
hdr "1 · Automation — ${TERM_APP} → Keynote"
printf "  ${DIM}Expect: \"%s wants access to control Keynote.\" Click OK.${RST}\n" "$TERM_APP"
osascript -e 'tell application "Keynote" to activate' >/dev/null 2>&1
until osascript -e 'tell application "Keynote" to get name' >/dev/null 2>&1; do
  bad "not granted yet"
  pane "Privacy_Automation"
  printf "  Enable ${BOLD}%s → Keynote${RST} in the pane that just opened.\n" "$TERM_APP"
  pause
done
ok "terminal can drive Keynote"

# ── 2. Automation: terminal → System Events (UI scripting) ──────────────────────
# Build animations and anything the AppleScript can't reach through Keynote's
# own dictionary go through System Events.
hdr "2 · Automation — ${TERM_APP} → System Events"
osascript -e 'tell application "System Events" to get name of first process' >/dev/null 2>&1
until osascript -e 'tell application "System Events" to get name of first process' >/dev/null 2>&1; do
  bad "not granted yet"
  pane "Privacy_Automation"
  printf "  Enable ${BOLD}%s → System Events${RST}.\n" "$TERM_APP"
  pause
done
ok "terminal can drive System Events"

# ── 3. Accessibility ────────────────────────────────────────────────────────────
# This one does NOT grant from its dialog — the dialog only offers to open
# Settings. You must flip the toggle yourself.
hdr "3 · Accessibility (UI scripting)"
while [[ "$(osascript -e 'tell application "System Events" to return UI elements enabled' 2>/dev/null)" != "true" ]]; do
  bad "not granted yet"
  pane "Privacy_Accessibility"
  printf "  Add and enable ${BOLD}%s${RST} in Privacy & Security → Accessibility.\n" "$TERM_APP"
  printf "  ${DIM}Use the + button if it isn't listed. This toggle is per-binary and\n"
  printf "  shared by every process your terminal spawns.${RST}\n"
  pause
done
ok "UI scripting enabled"

# ── 4. Screen Recording (slide screenshot tools) ────────────────────────────────
hdr "4 · Screen Recording (screenshot tools)"
SR_OK=0
if command -v uv >/dev/null 2>&1; then
  # CGRequestScreenCaptureAccess raises the real prompt and reports the answer.
  SR=$(uv run --quiet --with pyobjc-framework-Quartz python -c \
    'from Quartz import CGPreflightScreenCaptureAccess, CGRequestScreenCaptureAccess
print("yes" if (CGPreflightScreenCaptureAccess() or CGRequestScreenCaptureAccess()) else "no")' 2>/dev/null)
  [[ "$SR" == "yes" ]] && SR_OK=1
fi
if [[ $SR_OK -eq 0 ]]; then
  screencapture -x "$SCRATCH/preflight-shot.png" 2>/dev/null
  open "$SCRATCH/preflight-shot.png" 2>/dev/null
  warn "check the image that just opened"
  printf "  If it shows your windows, you're granted. If it shows only wallpaper,\n"
  printf "  enable ${BOLD}%s${RST} under Screen Recording and ${BOLD}restart the terminal${RST}.\n" "$TERM_APP"
  pane "Privacy_ScreenCapture"
  pause
else
  ok "screen capture allowed"
fi

# ── 5. Files & Folders — Downloads ──────────────────────────────────────────────
hdr "5 · Files & Folders — Downloads"
ls "${HOME}/Downloads" >/dev/null 2>&1 && ok "terminal can read ~/Downloads" || {
  bad "denied"; pane "Privacy_FilesAndFolders"; pause; }
# Keynote is sandboxed and needs its own grant to save into Downloads.
osascript >/dev/null 2>&1 <<APPLESCRIPT
tell application "Keynote"
  set d to make new document
  save d in POSIX file "${SCRATCH}/preflight-save-test.key"
  close d saving no
end tell
APPLESCRIPT
if [[ -e "$SCRATCH/preflight-save-test.key" ]]; then
  ok "Keynote can save into the scratch dir"
  rm -rf "$SCRATCH/preflight-save-test.key"
else
  bad "Keynote could not save into ~/Downloads"
  pane "Privacy_FilesAndFolders"
  printf "  Grant ${BOLD}Keynote → Downloads Folder${RST}. Keynote is sandboxed, so this is a\n"
  printf "  separate entry from your terminal's.\n"
  pause
fi

# ── 6. Verification sweep ───────────────────────────────────────────────────────
hdr "6 · Final verification"
PASS=1
osascript -e 'tell application "Keynote" to get name' >/dev/null 2>&1 \
  && ok "Automation → Keynote" || { bad "Automation → Keynote"; PASS=0; }
osascript -e 'tell application "System Events" to get name of first process' >/dev/null 2>&1 \
  && ok "Automation → System Events" || { bad "Automation → System Events"; PASS=0; }
[[ "$(osascript -e 'tell application "System Events" to return UI elements enabled' 2>/dev/null)" == "true" ]] \
  && ok "Accessibility" || { bad "Accessibility"; PASS=0; }
osascript >/dev/null 2>&1 <<'APPLESCRIPT'
tell application "Keynote"
  set d to make new document
  tell d
    set s to slide 1
    tell s to make new text item with properties {object text:"preflight"}
  end tell
  close d saving no
end tell
APPLESCRIPT
[[ $? -eq 0 ]] && ok "end-to-end: create doc, add text item, close" \
               || { bad "end-to-end script failed"; PASS=0; }

hdr "Result"
if [[ $PASS -eq 1 ]]; then
  printf "  ${GRN}${BOLD}All clear.${RST}\n\n"
  printf "  ${BOLD}Before you walk away:${RST}\n"
  printf "  1. Quit and reopen %s. Screen Recording and Accessibility grants only\n" "$TERM_APP"
  printf "     take effect for processes started after the grant.\n"
  printf "  2. Close every Keynote document you care about. The integration tests\n"
  printf "     will drive the GUI and a stray 'save changes?' sheet blocks everything.\n"
  printf "  3. Turn off the lock screen for the session: System Settings → Lock Screen →\n"
  printf "     'Require password after screen saver begins' → Never. UI scripting fails\n"
  printf "     against a locked screen, and caffeinate does not prevent locking.\n"
  printf "  4. Start the run under caffeinate so nothing sleeps mid-phase:\n\n"
  printf "     ${BOLD}cd ~/Downloads/mcp-keynote && caffeinate -dimsu claude --dangerously-skip-permissions${RST}\n\n"
else
  printf "  ${RED}${BOLD}Not ready.${RST} Fix the ✗ items above and re-run.\n"
  printf "  If a dialog never appears, you previously denied it — reset and retry:\n\n"
  if [[ -n "$TERM_BID" ]]; then
    printf "     tccutil reset AppleEvents %s\n" "$TERM_BID"
    printf "     tccutil reset Accessibility %s\n" "$TERM_BID"
    printf "     tccutil reset ScreenCapture %s\n" "$TERM_BID"
    printf "     tccutil reset SystemPolicyDownloadsFolder %s\n\n" "$TERM_BID"
  else
    printf "     tccutil reset AppleEvents <your-terminal-bundle-id>\n\n"
  fi
fi

rm -f "$SCRATCH/preflight-shot.png"
