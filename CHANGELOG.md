# Changelog

## 2.6.33 — 2026-07-27

- Route Return and keypad Enter through both a viewport-local event filter and
  the application event filter, preventing Qt item-view handling from swallowing
  activation before the view override runs.
- Prefer an actually selected row over a stale current index when opening an
  item, while retaining current-index fallback for keyboard navigation.
- Normalize Qt5/Qt6 key values and keep the view-level Enter handler as a second
  activation path.
- Store each file view's Tabs back-reference weakly, avoid duplicating the
  per-view action list during teardown, and bound retained open-error details.

## 2.6.32 — 2026-07-27

- Fix Return and keypad Enter under PyQt6 by defining the missing `Qt.Key_Return` and `Qt.Key_Enter` compatibility aliases.
- Ignore unavailable key aliases defensively so keyboard activation cannot silently degrade into a set containing only `None`.

## 2.6.31 — 2026-07-27

- Return and keypad Enter now reliably open the current selected file or folder.
- Activation is handled directly by the file view instead of relying on shortcut routing through its viewport.

## 2.6.30 — 2026-07-27

- Stream large multi-selections from compact Qt selection ranges, collapse selected descendants beneath a selected parent directory, recycle filesystem caches sooner, cap the icon cache at 8 MiB, and avoid repeated desktop-clipboard MIME queries.
- Batch ordinary Trash requests, bound retained directory-retargeting records, stream large Trash listings through a temporary file, and release transfer plans and worker payloads promptly after completion.
- Add reliable toolbar and keyboard bulk deletion, including explicit Shift+Delete permanent removal and clear mixed Trash/permanent-delete confirmation.
- Publish Cut and Copy selections as standard desktop file URLs for cross-instance paste, protect completed Cut cleanup with a per-clipboard token, and add Copy to Folder and Move to Folder controls for multi-selection workflows.
- Add Keep Both and apply-to-all conflict choices, unique same-folder copies, duplicate-destination handling, and physical Ctrl-key copy-mode feedback in the bottom status bar.
- Remove the packaged pytest/runtime-test tree and autopkgtest dependency for now; retain cache-free syntax, shell, archive, and package-hygiene verification through `make verify`.

## 2.6.29 — 2026-07-27

- Prevent constructor-time splitter callbacks while restoring saved window state.
- Defer sidebar-width capture until the restored UI is stable.
- Disable the native pyudev observer during pytest to avoid leaked polling threads after aborted UI tests.

## 2.6.28 — 2026-07-27

- Restore reliable Delete-key handling in the active file view and show a bottom-status indicator while the physical Ctrl key enables copy-mode dragging.

## 2.6.27 — 2026-07-27

- Keep the location bar on the current directory when a file or folder is single-clicked; selection still updates asynchronous size, MIME, and modification details.
- Coalesce deferred file-information callbacks with owned timers and shorten idle worker-thread retention so queued callbacks and native thread stacks are released sooner.
- Cap deferred filesystem-model path tracking, count very large selections without materializing one model index per item, and release closed-tab actions, models, metadata, and window references during teardown.
- Import `Worker` explicitly in the PyQt progress-rate regression and add coverage for terminal progress delivery, stable location text, bounded deferred path tracking, and range-based selection counting.

## 2.6.26 — 2026-07-27

- Publish the worker payload-disposal marker before the private completion signal, so `active_count == 0` cannot be observed while `_disposed` is false.
- Track callback and signal-object teardown with a separate idempotence guard, preserving public finished delivery while still disconnecting retained closures exactly once.
- Restore bounded error text and rate-limited progress events, and add a regression matching the completed-payload lifecycle failure.

## 2.6.25 — 2026-07-27

- Route completed-worker cleanup through a dedicated queued signal to the TaskManager thread instead of a zero-delay timer created in a QThreadPool thread without an event loop.
- Dispose workers before removing their final active-task state, so payload release, callback disconnection, signal-object deletion, and `_disposed` complete before the manager reports itself idle.
- Keep public finished callbacks ordered before internal cleanup and add regression checks that prohibit the timer/partial callback path.

## 2.6.24 — 2026-07-27

- Recycle the shared filesystem model after a bounded number of distinct navigations and after closed tabs, preserving open paths, ordinary selections, and scroll positions while releasing stale directory caches and watchers.
- Reuse icon delegates, detach closed-tab callbacks and widgets, delete temporary menus and dialogs, and cap application pixmap and stylesheet caches.
- Dispose completed worker signal objects and callbacks, keep recursive folder-scan identity tracking bounded, and avoid strong fallback references to closed file views.
- Delete retired MPRIS adaptors and disconnect and detach Qt Multimedia backends before deferred QObject destruction.
- Add regression coverage for bounded scans, non-retaining view fallback, shared-model recycling, worker disposal, adaptor cleanup, and cache limits.

## 2.6.23 — 2026-07-27

- Render icon-view file and folder names with a dedicated wrapped-text painter so Qt styles cannot replace any part of a long name with an ellipsis.
- Keep variable item heights synchronized with the exact text rectangle, including unbroken long names that must wrap anywhere.
- Make ordinary drag and drop move items while Ctrl+drag copies them between tabs, windows, or separate Spin FM instances.
- Advertise both copy and move drag actions and add regression coverage for full-name painting and modifier-aware transfers.

## 2.6.22 — 2026-07-20

- Restore and require the canonical `.gitattributes` distribution policy.
- Validate `.gitattributes`, `.gitignore`, and Debian source exclusions before building source archives.
- Require both Git policy files in every published source ZIP.
- Add regression coverage for missing or incomplete distribution-policy files.

## 2.6.21 — 2026-07-20

- Align file-information tests with the intentional MiB-only status format.
- Keep selected paths in the location bar rather than duplicating them in status text.
- Preserve asynchronous metadata inspection while verifying queued click handling.
- Keep source tests usable when a download tool omits dotfiles.

- Replace the fragile application-wide mouse filter with direct, one-time `clicked(QModelIndex)` bindings for every existing and future file tab.
- Add cancellable asynchronous recursive folder-size calculation with item counts, mount-boundary protection, and partial-result reporting.
- Add a normal right-elided file-information status field that keeps the selected size first, yields to core operation messages, and returns afterward.
- Isolate `python3-magic` failures so a broken MIME binding can never suppress file size or modification time.
- Add file, folder, direct-signal, persistent-status, real-click, and new-tab regression coverage.

## 2.6.19 — 2026-07-19

- Make main.py the only application bootstrap and remove stale references to the nonexistent extension_main.py from the launcher and Debian package.
- Attach the independent file-information module through an explicit window setup callback instead of replacing MainWindow at runtime.
- Support python3-magic class, module, structured-result, and legacy cookie APIs, including MIME encodings and older bytes-path implementations.
- Add MIME compatibility and unified-launcher regression tests.

## 2.6.18 — 2026-07-19

- Preserve executable permissions across GitHub Actions artifact downloads by uploading one tar file without artifact re-zipping and verifying it in a separate download job.
- Add an interpreter-driven permission repair/check tool and make every check, test, and Debian build restore the audited executable set before running.
- Make source ZIP permissions independent of checkout modes, so archives built after GitHub web upload or artifact download retain canonical `0755` scripts and `0644` data files.
- Add mode-loss, source-archive, Makefile, and GitHub workflow regression tests plus dedicated GitHub Actions documentation.

## 2.6.17 — 2026-07-19

- Replace per-tab `clicked(QModelIndex)` connections with one application-level Qt event filter.
- Make all existing and future file tabs work automatically without tab scans, identity registries, or per-view callback storage.
- Ignore drag releases using Qt's configured drag-distance threshold while leaving normal selection, double-click, and drag behavior untouched.
- Add real mouse-event regression tests proving that artificial `clicked` emissions are no longer the integration path.

## 2.6.16 — 2026-07-19

- Integrate the independent file-information module with the real Qt `clicked(QModelIndex)` signal.
- Bind every existing tab during startup and each newly activated tab at runtime without editing `main.py`, `app.py`, `main_window.py`, or `tabs.py`.
- Prevent duplicate view connections and release per-tab callback references when tabs are destroyed or the application shuts down.
- Add Qt regression tests that emit actual click signals in the first tab and a newly created tab and verify the displayed file size.

## 2.6.15 — 2026-07-19

- Restore click-selected path, size, modification time, and MIME details through an independent bounded background module.
- Integrate the legacy parent callback at runtime while keeping main.py, app.py, main_window.py, and tabs.py unchanged.

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
