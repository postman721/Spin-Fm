# SpinFm File Manager

Spin FM RC4 is a lightweight file manager built with PyQt5 that offers USB device monitoring, a tabbed file browser with back/forward navigation, multiple file/folder selection, and clipboard operations (cut/copy/paste). The application is designed with modularity in mind and is split into multiple Python modules for ease of maintenance and extension.

> **License:** This project is distributed under the GNU GPL v2 (June 1991).
![Image](https://github.com/user-attachments/assets/4b1c67bc-d949-443d-b1dc-7adabf85faf2)
## Features

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
