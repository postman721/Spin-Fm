# SpinFm File Manager

Spin FM v. 2.0 Copyright (c) 2021 JJ Posti <techtimejourney.net> This program comes with ABSOLUTELY NO WARRANTY; for details see: http://www.gnu.org/copyleft/gpl.html.  This is free software, and you are welcome to redistribute it under GPL Version 2, June 1991")

This is RC3 October 2024. 

#### How to fix: User cannot create/copy/paste anything to usb devices. 
Make sure the user actually owns its media content: sudo chown -hR $USER:$USER /media/$USER


![full](https://github.com/user-attachments/assets/e815ef34-c6f5-446d-9308-ad2beafb4959)

A lightweight file manager built using PyQt5, designed fot file management tasks. This file manager provides a tabbed interface for browsing the file system, creating, deleting, copying, and pasting files or folders. It also supports context menus for file operations and provides a dedicated tab for accessing the system trash.


## Features
1. Tabbed Interface

    CSS theme support with changable themes.
    Multiple directories can be opened at once in different tabs.
    New tabs can be added by:
        Double-clicking on an empty space in the tab bar.
    Each tab displays a separate directory, allowing users to browse different locations simultaneously.
    Tabs (except the first tab) can be closed by:
        Right-clicking on a tab and selecting "Close Tab" from the context menu.
    The first tab cannot be closed to ensure a fallback browsing location.

2. Navigation

    Home Button: Navigates the current tab to the user's home directory.
    Trash Button: Opens the system's trash directory in a new tab, where deleted items can be accessed.

3. File Operations

    Right-click on files or directories to access common file operations such as:
        Delete: Moves the selected file or folder to the system's trash.
        Cut: Cuts the selected file or folder for later pasting.
        Copy: Copies the selected file or folder.
        Paste: Pastes the cut or copied item into the current directory.
    Supports pasting of files and folders across different tabs.

4. Context Menus

    Right-clicking on a blank space in a tab allows users to:
        Create New Folder: Prompts the user to create a new folder in the current directory.
        Create New Text File: Prompts the user to create a new empty text file in the current directory.
        Paste: Pastes the previously cut/copied item in the current directory.

5. File System Browsing

    Each tab provides a list-view of the contents of a directory.
    Double-click on a folder to navigate into it.
    Files are opened using the system's default application.

6. Address Bar

    A text-based address bar is provided for direct navigation to a directory.
    Enter a valid file path and press Enter to navigate to that directory in the current tab.

7. Status Bar

    The status bar at the bottom of the window displays the current directory path for the active tab.

8. Trash Management

    Users can open the system's trash directory to view and manage files that were deleted.
    Trash is accessible via the "Trash" button on the toolbar or by creating a new tab with the trash path.

9. Usb Mounting

![mounted](https://github.com/user-attachments/assets/4c87c0e1-c828-44ec-a8f8-75f562fd9c86)

    Mount the usb device within the file manager. Double-click its name to the device and its content.

10. Showing available space to overall disk space within the second statusbar. 


## How to Use

    Launching the File Manager:
        Run the main script to start the file manager (python3 main.py).
        The interface will launch with one tab open to the user's home directory.

    Managing Tabs:
        Use the "Add Tab" button or double-click on the tab bar to create new tabs.
        Right-click on any tab (except the first) to close it.

    Navigating the File System:
        Use the home and trash buttons on the toolbar to navigate to the home directory 
        and to the trash directory, respectively.
        Enter paths directly in the address bar and press Enter to navigate to locations.

    Performing File Operations:
        Right-click on files or folders to access delete, cut, copy, and paste options.
        Create new folders or text files by right-clicking on empty space in the directory view.
        Empty trash functionality is under the File menu.

## Requirements

    Python 3.x
    PyQt5

## Debian dependency list

    python3 python3-pyqt5 qttools5-dev-tools xdg-utils libqt5widgets5 libqt5gui5 libqt5core python3-pyudev udisks2


## Making it a binary for Linux

I already did this at: https://github.com/postman721/Spin-Fm/tree/main/binary folder. But if you need to do it again for your system:

    pyinstaller --onefile --add-data "themes/default.css:styles" main.py
