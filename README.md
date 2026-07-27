# Spin FM

Spin FM is a lightweight, keyboard-friendly Qt file manager for Linux with tabs, removable-device support, asynchronous file operations, an embedded music player, and MPRIS integration.

A single click selects an item and displays its information without changing the current folder shown in the location bar. Double-click or press **Enter** to open files and folders.

---

# What's New (2.6.22 → 2.6.33)

## Performance and Memory

* Reduced memory use during long sessions.
* Better cleanup of closed tabs and completed background tasks.
* Bounded filesystem, icon, and stylesheet caches.
* Lower memory use when selecting large numbers of files.
* Streaming copy, move, Trash, and delete operations instead of building large in-memory lists.
* Faster cleanup of idle worker threads.
* Reduced duplicate path tracking during navigation.
* Improved cleanup of temporary dialogs, callbacks, and background workers.
* More efficient handling of large folders and large selections.

## File Operations

* Improved multi-file and multi-folder copy, move, and delete.
* Selecting a parent folder together with its descendants no longer schedules duplicate work.
* Better handling of large directory trees.
* Copying an item into its current folder automatically creates a unique name.
* Same-name conflicts support:

  * Replace
  * Skip
  * Keep Both
  * Apply to All
* Improved clipboard compatibility between Spin FM windows, separate Spin FM instances, and compatible desktop file managers.
* Improved Trash handling for local drives and removable media.
* Safer permanent deletion.
* Added dedicated **Copy to Folder** and **Move to Folder** actions.
* Open tabs are updated when their directories are moved or deleted.

## User Interface

* Complete file and folder names are always shown.
* Long names wrap instead of being shortened with `...`.
* Clicking a file or folder no longer changes the location bar.
* File information updates independently from navigation.
* The location bar changes only after actual navigation.
* Improved Trash location chooser.
* Better status information for file operations.
* Improved removable-device panel behavior.
* Added toolbar and context-menu actions for:

  * Copy to Folder
  * Move to Folder
* Better feedback during long-running operations.

## Drag and Drop

* Normal drag-and-drop **moves** files and folders.
* Hold the physical **Ctrl key before starting the drag** to enable **Copy mode**.
* The bottom status bar displays:

> **Copy mode enabled**

while Ctrl is held.

Copy mode works between:

* Spin FM tabs
* Multiple Spin FM windows
* Separate Spin FM instances
* Compatible Linux desktop file managers

## Keyboard and Selection

* `Delete` moves selected items to Trash.
* `Shift+Delete` permanently deletes selected items after confirmation.
* Multi-selection works with copy, cut, move, Trash, and permanent delete.
* `Ctrl+C` copies selected items.
* `Ctrl+X` cuts selected items.
* `Ctrl+V` pastes items.
* `Ctrl+Shift+C` copies the current selection to a chosen folder.
* `Ctrl+Shift+M` moves the current selection to a chosen folder.
* Delete-key handling is more reliable when the file view has focus.
* Holding Ctrl displays the copy-mode indicator before a drag begins.

---

<img width="800" height="600" alt="Image" src="https://github.com/user-attachments/assets/6860d9ec-ef6d-4e19-9cac-b7e53890e6a1" />

**Default theme**

<br>

<img width="800" height="600" alt="spin_music" src="https://github.com/user-attachments/assets/e17ba081-97fa-4964-b1b3-4dccfb005f74" />

**Alternative theme with integrated music playback**

---

# Features

* Tabbed file browsing
* Complete filename display
* Fast asynchronous file operations
* Multi-file copy, move, Trash, and deletion
* Native Linux Trash support
* Trash support for removable media
* USB mounting and unmounting
* Cross-instance copy and paste
* Drag-and-drop move and Ctrl-drag copy
* Copy to Folder and Move to Folder
* Recursive folder-size calculation
* File type, size, and modification information
* Embedded music player
* MPRIS and `playerctl` support
* Multiple application themes
* Adwaita and other installed icon themes
* Keyboard shortcuts
* Long-session memory optimizations

---

# Installation

## Debian and Ubuntu

Install the runtime dependencies for PyQt 6:

```sh
sudo apt update
sudo apt install \
  python3 \
  python3-pyqt6 \
  python3-pyqt6.qtmultimedia \
  python3-pyudev \
  python3-magic \
  file \
  udisks2 \
  util-linux \
  xdg-utils \
  libglib2.0-bin \
  adwaita-icon-theme \
  gstreamer1.0-plugins-base \
  gstreamer1.0-plugins-good \
  gstreamer1.0-libav
```

PyQt 5 can be used when PyQt 6 is unavailable:

```sh
sudo apt install \
  python3 \
  python3-pyqt5 \
  python3-pyqt5.qtmultimedia \
  python3-pyudev \
  python3-magic \
  file \
  udisks2 \
  util-linux \
  xdg-utils \
  libglib2.0-bin \
  adwaita-icon-theme \
  gstreamer1.0-plugins-base \
  gstreamer1.0-plugins-good \
  gstreamer1.0-libav
```

Launch Spin FM from the source directory:

```sh
./bin/spin-fm
```

or:

```sh
python3 -B main.py
```

## Install the Debian Package

Install the package produced by the build:

```sh
sudo apt install ../spin-fm_2.6.33_all.deb
```

---

# Arch Linux Dependencies

Install the recommended PyQt 6 dependencies:

```sh
sudo pacman -S --needed \
  python \
  python-pyqt6 \
  qt6-multimedia \
  qt6-multimedia-ffmpeg \
  python-pyudev \
  python-magic \
  file \
  udisks2 \
  util-linux \
  xdg-utils \
  glib2 \
  adwaita-icon-theme \
  dbus
```

Use `qt6-multimedia-gstreamer` instead of the FFmpeg multimedia backend when preferred and available.

Package names can vary between Arch Linux repositories and derivatives.

---

# Fedora Dependencies

Install the recommended dependencies:

```sh
sudo dnf install \
  python3 \
  python3-pyqt6 \
  qt6-qtmultimedia \
  python3-pyudev \
  python3-magic \
  file \
  udisks2 \
  util-linux \
  xdg-utils \
  glib2 \
  adwaita-icon-theme \
  dbus-daemon \
  gstreamer1-plugins-base \
  gstreamer1-plugins-good
```

Additional multimedia codecs may be needed for some audio formats.

---

# Usage

## Navigation

* Single-click selects a file or folder and displays its information.
* Double-click or press **Enter** to open the selected item.
* Single-clicking an item does not change the location bar.
* `Ctrl+L` focuses the location bar.
* `Ctrl+Up` opens the parent folder.
* `Ctrl+T` opens a new tab.
* `Ctrl+W` closes the current tab.
* `F5` or `Ctrl+R` refreshes the current folder.
* `F9` shows or hides the removable-device panel.

## Copy and Move

Use the standard shortcuts:

* `Ctrl+C` — Copy
* `Ctrl+X` — Cut
* `Ctrl+V` — Paste

You can also use:

* **Copy to Folder**
* **Move to Folder**

from the toolbar or context menu.

Their shortcuts are:

* `Ctrl+Shift+C` — Copy to Folder
* `Ctrl+Shift+M` — Move to Folder

When a destination already contains an item with the same name, Spin FM can:

* Replace it
* Skip it
* Keep both items
* Apply the choice to all remaining conflicts

## Drag-and-Drop Copy Mode

> **Important:** Press and hold **Ctrl before you start dragging** when you want to copy instead of move.

While Ctrl is held, the bottom status bar displays:

> **Copy mode enabled**

Normal drag-and-drop moves files.

Holding Ctrl before dragging copies files.

Release Ctrl to return to Move mode.

## Delete

Press:

* `Delete` to move the selected items to Trash
* `Shift+Delete` to permanently delete the selected items after confirmation

Files already inside a recognized Trash folder are permanently removed when deleted.

## Selecting Multiple Items

Multi-selection works with:

* Copy
* Cut
* Paste
* Copy to Folder
* Move to Folder
* Trash
* Permanent deletion

When a selected parent folder already contains another selected item, Spin FM processes the parent only and avoids duplicate work.

---

# Music Player

Spin FM includes an embedded, seekable audio player.

Shortcuts:

* `Alt+P` — Play or pause
* `Alt+M` — Mute or unmute

When a track is loaded, Spin FM exposes an MPRIS interface. This allows playback control through:

* `playerctl`
* Desktop media keys
* Compatible desktop media controls
* Compatible on-screen display services

Example commands:

```sh
playerctl --list-all | grep spin_fm
playerctl --player=spin_fm status
playerctl --player=spin_fm play-pause
```

A missing MPRIS session bus or external OSD service does not prevent local playback.

---

# Trash and Removable Devices

Spin FM supports the normal desktop Trash and recognized Trash locations on mounted devices.

Supported mounted-device layouts include:

```text
.Trash-UID/files
.Trash/UID/files
```

Spin FM does not create Trash folders while browsing.

When more than one Trash location is available, the Trash button opens a chooser showing clear location names and complete paths.

Use **File → Empty Trash** to empty the desktop Trash through GIO.

---

# Themes

Spin FM includes multiple application themes.

Available themes include:

* LWM Dark
* LWM Graphite

Change the application theme through:

**Appearance → Application Theme**

Installed icon themes are available through:

**Appearance → Icon Theme**

Adwaita is used as the first-run icon theme when installed.

---

# Build Commands

Install the Debian build tools:

```sh
sudo apt update
sudo apt install make debhelper dpkg-dev python3
```

Available build commands:

```sh
make check
```

Checks required packaging commands and Debian build dependencies.

```sh
make verify
```

Runs syntax, shell, permissions, archive, cache, and release-hygiene checks.

```sh
make deb
```

Builds and inspects the unsigned Debian package.

```sh
make all
```

Runs `check`, `verify`, and `deb` in sequence.

Runtime tests and pytest are intentionally not included in the 2.6.33 release.

---

# Configuration

Qt stores Spin FM settings below:

```text
~/.config/Spin/
```

The normal settings file is:

```text
~/.config/Spin/Spin FM.conf
```

---

# Troubleshooting

Disable the independent file-information module temporarily with:

```sh
SPIN_FM_FILE_INFO=0 spin-fm
```

Disable Wayland OSD integration with:

```sh
SPIN_FM_WAYLAND_OSD=0 spin-fm
```

Optional Wayland OSD settings:

```text
SPIN_FM_WAYLAND_OSD_COMMAND=/path/to/wayland-volume-osd
SPIN_FM_WAYLAND_OSD_THEME=dark|blue|grey|wood
```

Distribution package names and multimedia backends can vary. Install the equivalent Qt Widgets, Qt D-Bus, Qt Multimedia, `pyudev`, `python-magic`, GIO, and audio-codec packages for your distribution.

---

# License

Spin FM is GPL-2.0-or-later

See:

- `LICENSE`
- `debian/copyright`

Author: **JJ Posti**  
Website: https://techtimejourney.net


