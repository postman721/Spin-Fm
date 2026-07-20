# Spin FM file manager

Spin FM is a lightweight tabbed Qt file manager for Linux with removable-device controls, asynchronous file operations, selected-item metadata, and a seekable embedded audio player. A single click reports the path, file size or recursive folder size, modification time, and MIME information in a persistent status field; double click opens. While an audio track is loaded, Spin FM advertises a native MPRIS player so `playerctl`, desktop media controls, and compatible OSD services can control it.

<img width="800" height="600" alt="Image" src="https://github.com/user-attachments/assets/6860d9ec-ef6d-4e19-9cac-b7e53890e6a1" />

Default theme.
</br>

<img width="800" height="600" alt="spin_music" src="https://github.com/user-attachments/assets/e17ba081-97fa-4964-b1b3-4dccfb005f74" />

Alternative theme and music playback.
</br>


## Download and validation

Release archives and the Debian package are produced from the same cache-free source tree. `make tests` runs the Python, syntax, shell, source-archive, and release-hygiene checks; `make all` performs dependency validation, tests, and the Debian build in sequence.

### Archive permissions

No GitHub workflow is required. Git stores executable bits for the launcher and
Debian scripts, and Spin FM's source-archive builder writes audited `0755` modes
for executable files even when the local checkout has lost them. A damaged
checkout can be repaired or checked directly with:

```sh
python3 -B tools/normalize_permissions.py --fix
python3 -B tools/normalize_permissions.py --check
```

## Debian installation and packaging

Install the native build and test dependencies:

```sh
sudo apt update
sudo apt install \
  make debhelper dpkg-dev \
  python3 python3-pyqt6 python3-pyqt6.qtmultimedia \
  python3-pyudev python3-magic python3-pytest file
```

The public build interface has four targets:

```sh
make check   # verify commands, Python modules, and debian/control Build-Depends
make tests   # run tests, syntax/shell checks, and cache/legacy release gates
make deb     # build and inspect the unsigned Debian binary package
make all     # run check, tests, and deb in that order
```

Install the resulting package:

```sh
sudo apt install ../spin-fm_2.6.21_all.deb
```

The Debian package installs application-private source under `/usr/share/spin-fm`; it does not build a wheel, sdist, or Python-index package. `make check`, `make deb`, and `make all` validate the PyQt 6 Debian package path.

## Run from source

PyQt 6 is preferred:

```sh
sudo apt install \
  python3 python3-pyqt6 python3-pyqt6.qtmultimedia python3-pyudev \
  python3-magic file udisks2 util-linux xdg-utils libglib2.0-bin adwaita-icon-theme \
  gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-libav
```

Debian source checkouts also support PyQt 5 when PyQt 6 is unavailable:

```sh
sudo apt install \
  python3 python3-pyqt5 python3-pyqt5.qtmultimedia python3-pyudev \
  python3-magic file udisks2 util-linux xdg-utils libglib2.0-bin adwaita-icon-theme \
  gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-libav
```

`python3-pyqt5` supplies the Qt Widgets and Qt D-Bus bindings;
`python3-pyqt5.qtmultimedia` supplies audio playback. Install either the PyQt 6
or PyQt 5 set, then launch:

```sh
./bin/spin-fm [PATH_OR_URI ...]
```

Equivalent direct launch:

```sh
python3 -B main.py [PATH_OR_URI ...]
```

`main.py` is the single bootstrap for both source and Debian installations.
`bin/spin-fm` delegates to it, and `main.py` passes the independent file-info
installer to the application as a window-setup callback. There is no separate
`extension_main.py` entry point. Both launch paths disable Python bytecode before
project modules are imported.

## Usage

- Single click selects a file or folder; double click opens it or starts supported audio.
- A single click also places the complete selected path in the location bar and reports file size or recursive folder-content size, modification time, and MIME information through the independent `file_info_extension` module.
- `Return` or keypad `Enter` opens the selected item.
- `Alt+P` toggles embedded play/pause from any non-modal Spin FM view.
- `Alt+M` toggles player mute.
- `Ctrl+T` / `Ctrl+W` opens or closes a tab; `Ctrl+L` focuses the location bar.
- `Ctrl+Up` opens the parent folder; `F5` or `Ctrl+R` refreshes.
- File and folder labels wrap to show their complete names instead of middle ellipses.
- The Trash toolbar opens Home Trash directly when it is the only location. When USB or mounted-volume Trash folders exist, it opens a large chooser with clear names and complete paths.
- `Delete` moves ordinary items to Trash and permanently deletes items already inside a recognized Trash folder.
- Dropping local files or folders onto a folder asks for confirmation, then moves them like Cut/Paste; same-name destinations always receive an overwrite/skip prompt.
- `F9` shows or hides the removable-device panel. Its remembered production width keeps Mount and Unmount actions visible.
- The timeline supports clicks, dragging, keyboard input, the mouse wheel, and 10-second rewind/forward controls when the backend reports seekability.
- LWM Dark and LWM Graphite are available under **Appearance → Application Theme**.
- Adwaita is the first-run icon theme when installed; other installed themes remain selectable under **Appearance → Icon Theme**.

Both `.Trash-UID/files` and `.Trash/UID/files` mounted-device layouts are recognized without creating Trash directories during browsing. **File → Empty Trash** empties the desktop Trash through GIO.

Keyboard shortcuts apply while the Spin FM window has focus. 

## Independent file information module

`src/spin_fm/file_info_extension.py` restores the historical
`on_treeview2_clicked` and `changed(current)` behaviour while remaining an
independent module. Integration happens in four steps:

1. `bin/spin-fm` launches the standard `main.py` entry point.
2. `main.py` imports `file_info_extension.install` and passes it to
   `spin_fm.app.main` as `window_setup`.
3. The application constructs its normal `MainWindow`, then invokes that setup
   callback once for the new window.
4. `FileInfoExtension` connects each existing file view's native
   `clicked(QModelIndex)` signal and binds newly created tabs when the active tab
   changes. Each view is connected once and released when its tab is destroyed.

A click resolves the path through that tab's existing `QFileSystemModel`, writes
the complete path to the location bar, and submits metadata work to one bounded
worker. Files use `st_size`; folders are scanned recursively with `os.scandir`
without following child symlinks or crossing into another mounted filesystem.
A newer click cancels a stale folder scan and retains only the latest pending
request.

Results are written to a normal, right-elided status field beside the disk
indicator. The size is placed first, so it remains visible even when the status
bar is narrow. The complete path stays in the location bar and is intentionally
not duplicated in the status text. Copy, move, device, and other core status
messages temporarily replace
this field and the selected-item information returns afterward. Folder results
include logical content size, file/folder counts, and a partial-result warning
when entries are inaccessible.

The module supports the official `python3-magic` `Magic` class and
module-level `from_file` APIs, structured-result bindings, and the legacy
libmagic cookie API. It preserves MIME encodings when available, supports older
bytes-path bindings, and then uses safe filename and `file(1)` fallbacks. A
broken or conflicting `magic` module cannot suppress the independently available
size and timestamp result. Selection state stays on the extension instance
rather than in a process-global variable. The compatibility parent callback
delegates to Spin FM's existing navigation history instead of replacing the
shared file system model. Automatic loading can be disabled for troubleshooting with:

```sh
SPIN_FM_FILE_INFO=0 spin-fm
```

## Desktop player and Wayland_OSD

When a track is loaded, Spin FM registers `org.mpris.MediaPlayer2.spin_fm` on the user session bus. Multiple instances use a process-specific suffix. Playback status, metadata, position, seeking, and player volume are exposed through the standard MPRIS 2 interface.

```sh
playerctl --list-all | grep spin_fm
playerctl --player=spin_fm status
playerctl --player=spin_fm play-pause
```

This is the integration Wayland_OSD and desktop media controls use to recognize Spin FM as an active player. The existing direct Wayland_OSD socket notifications remain best-effort. A missing session bus, Qt D-Bus module, Wayland_OSD executable, or daemon socket never prevents local playback or closes the application.

Optional Wayland_OSD controls:

```text
SPIN_FM_WAYLAND_OSD=0
SPIN_FM_WAYLAND_OSD_COMMAND=/path/to/wayland-volume-osd
SPIN_FM_WAYLAND_OSD_THEME=dark|blue|grey|wood
```

## Arch Linux dependencies (best effort)

```sh
sudo pacman -S --needed \
  python python-pyqt6 qt6-multimedia qt6-multimedia-ffmpeg python-pyudev \
  python-magic file udisks2 util-linux xdg-utils glib2 adwaita-icon-theme dbus
sudo pacman -S --needed python-pytest   # only for make tests
```

Use `qt6-multimedia-gstreamer` instead of the FFmpeg backend when preferred and available.

## Fedora dependencies (best effort)

```sh
sudo dnf install \
  python3 python3-pyqt6 qt6-qtmultimedia python3-pyudev python3-magic file \
  udisks2 util-linux xdg-utils glib2 adwaita-icon-theme dbus-daemon \
  gstreamer1-plugins-base gstreamer1-plugins-good
sudo dnf install python3-pytest   # only for make tests
```

## Notable improvements

- UI has been designed again to be more informative.
- Trash for removable media + normal SSD deletion.
- Drag and drop now matches cut and paste.
- Integrated music player that works together with my Wayland-OSD project - or any other OSD that sees playerctl
- More shortkeys and UI elements that can be hidden.
- LWM matching themes added (upcoming Wayland compositor based upon Labwc).
- Debian packaging added via Makefile.

<b>Distribution package names and codec backends can vary; use the equivalent PyQt 6 Core/Widgets/D-Bus, Qt Multimedia, pyudev, python-magic, and audio-backend packages when needed.</b>

## Configuration location
Qt stores settings below `~/.config/Spin/` (normally `Spin FM.conf`).

## Release hygiene

All project-controlled launch, test, archive, and Debian paths use `-B`, `PYTHONDONTWRITEBYTECODE=1`, or an early `sys.dont_write_bytecode` assignment. Release gates remove and reject `__pycache__`, `.pyc`, `.pyo`, tool caches, wheel/sdist metadata, retired modules, Debian staging output, patch rejects, and editor backups.

Spin FM is GPL-2.0-or-later. See `LICENSE` and `debian/copyright`.

Author JJ Posti <techtimejourney.net>
