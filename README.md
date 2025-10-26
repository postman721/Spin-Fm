# SpinFM File Manager

**Spin FM RC5** is a lightweight, modular file manager now fully compatible with **PyQt6** (while maintaining PyQt5 fallback support). It features a tabbed interface, USB device monitoring, custom theming, and modern UI enhancements like larger toolbar icons, visible close buttons on tabs, and improved hidden-file toggling.

> **License:** This project is distributed under the **GNU GPL v2 (June 1991)**.  
<img width="1194" height="832" alt="Image" src="https://github.com/user-attachments/assets/51f1a25f-e1c9-4e3b-a75d-7cefaf6a7cbe" />

---

## ✨ New in RC5 (May 2025)

###  PyQt6 Compatibility
- Works on **PyQt6** with automatic **PyQt5 fallback** via the new `qt_compat.py` compatibility shim.
- Fixes all `QAction`, `QDir`, `QFileSystemModel`, `QTableWidget`, and `exec_/exec` API changes in Qt6.
- Prints which backend (PyQt6 or PyQt5) is active at startup.

###  UI Improvements
- **Larger icons** in toolbar and file view for better visibility and touch-screen use.  
- **Visible navigation arrows** (thanks to the new dark theme tweaks).  
- **Show Hidden Files toggle** now works across all open tabs.  
- **Cleaner, flatter dark mode** and brighter hover/pressed states for buttons.  

---

## Features

- **Icon Theme Changing:**  
  Switch icon themes dynamically from the “Icon Themes” menu.  
  *(Added March 23, 2025)*

- **USB Device Monitoring:**  
  Automatically detects and lists removable drives using `pyudev`.  
  Right-click to mount/unmount devices via the left panel.

- **Tabbed File Browser:**  
  Browse multiple directories simultaneously with tabbed navigation, including **Back**, **Forward**, **Home**, and **Trash** buttons.

- **Multiple Selection & Clipboard Operations:**  
  Perform batch **Cut**, **Copy**, **Paste**, **Delete**, and **Rename** actions.

- **Context Menus:**  
  Right-click on items or empty space for file/folder operations or quick creation of new folders and files.

- **Theming:**  
  Supports **custom CSS themes** for full color and layout control. Themes live in the `themes/` directory.

- **Trash Management:**  
  “Empty Trash” option under the **File** menu for quick cleanup.

---

## Project Structure

| File | Purpose |
|------|----------|
| `main.py` | Entry point; creates the QApplication before any UI. |
| `main_window.py` | Defines the main window, menus, and USB/device tabs splitter. |
| `tabs.py` | Manages the tabbed file browser (navigation, context menus, file operations). |
| `mounted_devices_widget.py` | Lists and manages USB drives (mount/unmount). |
| `theme_manager.py` | Loads and applies visual themes (light/dark/custom). |
| `icon_theme_manager.py` | Loads and applies icon themes. |
| `qt_compat.py` | **NEW:** Compatibility shim between PyQt6 and PyQt5. |
| `empty_trash.py` | Implements “Empty Trash” behavior. |
| `disk_space.py` / `device_monitor.py` | Handle disk usage queries and udev monitoring. |

---

## How to Use

**Launch the File Manager:**
```bash
python3 main.py
```
- The file manager opens with your **Home** directory in the first tab.  
- To open new tabs: Right-click an existing tab. 

**Navigating the File System:**
- Use the toolbar buttons for **Back**, **Forward**, **Home**, and **Trash**.  
- Type a path into the address bar and press **Enter** to navigate directly.

**File Operations:**
- Right-click items for options like **Open**, **Rename**, **Delete**, **Cut**, **Copy**, and **Paste**.  
- Right-click empty space to **create new folders** or **text files**.  
- To empty the trash, go to **File → Empty Trash**.

**Hidden Files:**
- Toggle hidden files (dotfiles) visibility from the **View → Show Hidden Files** menu.

**Themes:**
- Use **Themes** and **Icon Themes** menus to customize the look and feel.

---

## Debian / Ubuntu Dependencies

Install all required packages for both PyQt5 and PyQt6 compatibility:

```bash
sudo apt install \
  python3  python3-pyqt6 python3-pyudev xdg-utils udisks2 \
  qttools5-dev-tools libqt5widgets5 libqt5gui5 libqt5core5a
```

*(You can safely install both PyQt5 and PyQt6 — SpinFM automatically uses PyQt6 if available.)* For PyQT5 install: python3-pyqt5 or equivalent.

---

## USB Permissions for All Users - Might not be needed anymore

Create a script file (e.g., `usb_perms.sh`) with the following:

```bash
#!/bin/bash
echo "Creating udev rule to grant USB devices 0666 permissions for all users..."
if [ ! -f /etc/udev/rules.d/99-usb.rules ]; then
    echo 'SUBSYSTEM=="usb", MODE="0666"' | sudo tee /etc/udev/rules.d/99-usb.rules
    echo "Created udev rule at /etc/udev/rules.d/99-usb.rules."
    sudo udevadm control --reload-rules && sudo udevadm trigger
else
    echo "Udev rule for USB devices already exists."
fi
```

Make it executable and run it once:
```bash
chmod +x usb_perms.sh
sudo ./usb_perms.sh
```

---

## Summary

**SpinFM RC5** is a modernized, stable, PyQt6-ready file manager with:  
- USB monitoring  
- Tabbed browsing  
- Clipboard file operations  
- Theme and icon customization  
- Dark/light theme support  
- Hidden file toggle  
- Full PyQt6/PyQt5 compatibility via `qt_compat.py`  

> © 2025 JJ Posti — [GPL v2](http://www.gnu.org/copyleft/gpl.html)
