# Desktop Menu Architecture — SchemeKnit

## Overview

The SchemeKnit desktop application uses Electron and provides a native
menu structure aligned with platform conventions. Menus are defined in
`main.js` (Electron main process) and applied via `Menu.buildFromTemplate()`.

---

## Menu Structure

### File

| Item | Shortcut | Description |
|------|----------|-------------|
| New Scheme | `Ctrl+N` | Open the new scheme upload dialog |
| Open Scheme | `Ctrl+O` | Open scheme from recent list |
| Save | `Ctrl+S` | Trigger browser save / DOCX export |
| Save As… | `Ctrl+Shift+S` | Export as DOCX with filename prompt |
| Print… | `Ctrl+P` | Print current lesson plan |
| — | | Separator |
| Sign Out | | Clear session and return to login |
| Exit | `Alt+F4` | Quit the application |

### Edit

| Item | Shortcut | Description |
|------|----------|-------------|
| Undo | `Ctrl+Z` | Undo last text edit |
| Redo | `Ctrl+Shift+Z` | Redo last text edit |
| Cut | `Ctrl+X` | Cut selection |
| Copy | `Ctrl+C` | Copy selection |
| Paste | `Ctrl+V` | Paste from clipboard |
| Select All | `Ctrl+A` | Select all text in focused field |

### View

| Item | Shortcut | Description |
|------|----------|-------------|
| Reload | `Ctrl+R` | Reload the renderer |
| Force Reload | `Ctrl+Shift+R` | Hard reload bypassing cache |
| Toggle DevTools | `Ctrl+Shift+I` | Open Chrome DevTools |
| — | | Separator |
| Zoom In | `Ctrl+=` | Increase zoom |
| Zoom Out | `Ctrl+-` | Decrease zoom |
| Reset Zoom | `Ctrl+0` | Restore 100% zoom |
| — | | Separator |
| Fullscreen | `F11` | Toggle fullscreen mode |

### Help

| Item | Shortcut | Description |
|------|----------|-------------|
| Documentation | | Open `/docs` in default browser |
| What's New | | Open `/docs/CHANGELOG.md` in browser |
| Keyboard Shortcuts | | Open `/docs/KEYBOARD.md` in browser |
| — | | Separator |
| Report a Problem | | Open `https://github.com/schemeknit/issues` |
| — | | Separator |
| About SchemeKnit | | Show version, platform, and licence info |

---

## Implementation Notes

1. **No production rebuild**: the EXE is not rebuilt during this
   milestone. Changes are applied to `main.js` and take effect on the
   next Electron launch from source.

2. **Menu definition lives in `main.js`** using `Menu.buildFromTemplate()`.
   Individual items use `role` for built-in actions (e.g. `cut`, `copy`)
   and `click` for custom handlers.

3. **Help menu items** open URLs via `shell.openExternal()`, which is
   the standard Electron pattern for external links.

4. **Shortcuts** follow platform conventions: `Ctrl` on Windows/Linux,
   `Cmd` on macOS. Electron handles this automatically when using `accelerator`.

5. **The renderer does not need to know about menus** — all menu actions
   are handled in the main process and communicated via IPC where needed
   (e.g. export file dialog).

---

## File Locations

- `desktop/main.js` — Electron entry point; menu definition
- `desktop/package.json` — Electron project config
- `desktop/preload.js` — preload script for IPC bridge

No changes to `preload.js` or renderer files are required for the
menu architecture itself — this is all main-process Electron code.
