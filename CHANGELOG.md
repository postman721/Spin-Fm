# Changelog

## 2.6.14 — 2026-07-18

- Prevent the second or mounted-volume Trash chooser row from inheriting a white system alternate-row color before it is selected.

## 2.6.13 — 2026-07-18

- Remove the redundant view-scoped Ctrl+T action so the single window-level New Tab shortcut no longer triggers Qt's ambiguous-shortcut warning.

## 2.6.12 — 2026-07-17

- Replace the compact Trash selector with a large, resizable chooser that shows clear location names and complete home or mounted-volume paths.
- Keep F9 device actions visible with a fixed action column, bounded sidebar sizing, and a remembered width when the sidebar is hidden and restored.
- Prefer Adwaita for first-run icons with installed-theme fallbacks and style the new production dialogs consistently across every Spin FM theme.
- Remove retired compatibility wrappers, release worker payloads promptly, stream fallback Trash cleanup, normalize archive permissions, and align both project changelogs.

## 2.6.11 — 2026-07-17

- Discover and open existing home and mounted-device Trash locations, supporting both freedesktop USB Trash layouts without creating them.
- Keep direct Home Trash navigation when no mounted Trash is present.

## 2.6.10 — 2026-07-17

- Fix Trash toolbar navigation when Qt has not indexed the hidden freedesktop Trash directory hierarchy.

## 2.6.9 — 2026-07-17

- Make the Trash toolbar open Trash, use GIO for complete desktop-trash emptying, and permanently delete items already inside Trash folders.
- Make local drag-and-drop a confirmed Cut/Paste-style move with same-name overwrite or skip prompts and clean cancellation.
- Document complete PyQt 5 source dependencies while retaining PyQt 6 for Debian packaging and production defaults.

## 2.6.8 — 2026-07-17

- Register the embedded player through MPRIS for playerctl, desktop media controls, and Wayland_OSD; publish Alt+P and button state immediately.
- Show complete wrapped file and folder names and add native LWM Dark and LWM Graphite application themes.
- Simplify Debian automation to make check, make tests, make deb, and make all; remove Ruff, retired packaging files, and generated legacy artifacts.
- Keep launch, test, archive, and Debian staging paths bytecode-free while treating optional OSD and D-Bus failures as non-fatal.

## 2.6.7 — 2026-07-17

- Make Alt+P deterministic when Qt Multimedia state reporting is delayed.
- Route audio shortcuts before child widgets and emit immediate OSD feedback.
- Standardize GPL-2.0-or-later metadata and tighten release validation.

## 2.6.6 — 2026-07-16

- Fix application-wide Alt+P Wayland_OSD play/pause feedback.
- Harden cache-free Debian releases, remove legacy artifacts, and focus docs.

## 2.6.5 — 2026-07-16

- Make supported workflows cache-free and add deterministic source validation.
- Reject Python-index packaging metadata and generated distribution artifacts.

## 2.6.4 — 2026-07-16

- Remove PyPI packaging and install application-private source directly.
- Harden optional Wayland_OSD discovery, socket validation, and startup retries.

## 2.6.3 — 2026-07-16

- Restore double-click activation and expand the seekable embedded player.
- Add failure-isolated Wayland_OSD media and volume feedback.

## 2.6.2 — 2026-07-15

- Add Ctrl+Up parent navigation and lazy embedded audio playback.
- Add themed controls, external-player fallback, and Qt5/Qt6 tests.

## 2.6.1 — 2026-07-15

- Harden launching, storage caching, task cleanup, and overwrite safety.
- Add symlink-aware operation checks and broader runtime coverage.

## 2.6.0 — 2026-07-15

- Add asynchronous operations, bounded caches, refreshed themes, and packaging.
