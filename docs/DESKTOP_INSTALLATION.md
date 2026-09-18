# TeachFlow Desktop 1.0.4 — Installation

## Requirements
Windows 10/11 x64. No Node.js, Python, conda, Docker, or repository needed.

## Install
1. Run `TeachFlow-Setup-1.0.4-x64.exe` (SmartScreen may warn: unsigned build → More info → Run anyway).
2. Follow the installer (per-user; shortcuts on Desktop + Start Menu).
3. Launch **TeachFlow**. First run creates your private data folder; no login needed until
   you create your administrator account on the setup screen.

## Accounts (first run)
- The setup screen creates your local administrator.
- That administrator creates teacher accounts (School Admin → Teachers).
- Teachers sign in at the app login screen. All data stays on your PC.

## Optional local AI
Lesson-assist buttons use Ollama on your machine if present
(default model `llama3`; install Ollama separately). Without it, the buttons show a
controlled unavailable message — everything else works fully offline-capable and
deterministic.

## Data & uninstall
- Your data: `%APPDATA%\teachflow-desktop\data` (database, uploads, exports, diagnostics).
- Uninstall keeps your data (per installer configuration). Back up that folder to migrate PCs.

## Verify integrity
`certutil -hashfile TeachFlow-Setup-1.0.4-x64.exe SHA256` must match
`TeachFlow-1.0.4-Windows-x64.sha256`.
