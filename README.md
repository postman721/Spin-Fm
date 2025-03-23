# SpinFm File Manager

Spin FM RC4 is a lightweight file manager built with PyQt5 that offers USB device monitoring, a tabbed file browser with back/forward navigation, multiple file/folder selection, and clipboard operations (cut/copy/paste). The application is designed with modularity in mind and is split into multiple Python modules for ease of maintenance and extension.

> **License:** This project is distributed under the GNU GPL v2 (June 1991).
![Image](https://github.com/user-attachments/assets/ac66c7b9-c4aa-4351-9928-6f4d6481c7af)

In the picture you see icon theme change and some dragged and dropped songs between Spin FM and Albix music player.

## Features

- **Icon theme changing:**  
  Change icon theme. Added as a new feature on March 23th, 2025.

- **USB Device Monitoring:**  
  Automatically detects USB devices using `pyudev` and displays them in a dedicated left panel. Click or right-click to mount/unmount devices.

- **Tabbed File Browser:**  
  Navigate your filesystem using multiple tabs with back/forward navigation and an address bar.

- **Multiple Selection and Clipboard Operations:**  
  Select multiple files/folders using standard selection techniques (e.g., Ctrl/Shift) and perform bulk operations like delete, cut, copy, and paste.

- **Context Menus:**  
  Right-click on items to access additional file operations.

- **Theming:**  
  Apply custom CSS themes to change the look and feel of the application. Themes are stored in the `themes/` directory.

- **Trash Management:**  
  Easily empty your trash directory via the File menu.

![Image](https://github.com/user-attachments/assets/2830285d-8c6e-4139-ab98-599d02cd7be5)

## Project Structure

The project is organized into multiple modules for clarity.

## How to Use

    Launching the File Manager:
        Run the main script to start the file manager (python3 main.py).
        The interface will launch with one tab open to the user's home directory.

    Managing Tabs:
        Use the "Add Tab" button or double-click on the tab bar to create new tabs.
        Right-click on any tab (except the first) to close it.

    Navigating the File System:
        Use the buttons on the toolbar to navigate to the home directory 
        and to the trash directory, respectively.
        Enter paths directly in the address bar and press Enter to navigate to locations.

    Performing File Operations:
        Right-click on files or folders to access  options.
        Create new folders or text files by right-clicking on empty space in the directory view.
        Empty trash functionality is under the File menu.
        You can now also change themes.

## Debian dependency list

    python3 python3-pyqt5 qttools5-dev-tools xdg-utils libqt5widgets5 libqt5gui5 libqt5core5a python3-pyudev udisks2


## Usb permissions for all users, make a script file.

With the following content.

    echo "Creating udev rule to grant USB devices 0666 permissions for all users..."
    if [ ! -f /etc/udev/rules.d/99-usb.rules ]; then
        echo 'SUBSYSTEM=="usb", MODE="0666"' > /etc/udev/rules.d/99-usb.rules
        echo "Created udev rule at /etc/udev/rules.d/99-usb.rules."
        udevadm control --reload-rules && udevadm trigger
    else
        echo "Udev rule for USB devices already exists."
    fi
