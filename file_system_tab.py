#file_system_tab.py: Contains the file system related functions and the createFileSystemTab function: Meaning creates the model for file system.

#Spin FM v. 2.0 Copyright (c) 2021 JJ Posti <techtimejourney.net> This program comes with ABSOLUTELY NO WARRANTY; for details see: http://www.gnu.org/copyleft/gpl.html.  This is free software, and you are welcome to redistribute it under GPL Version 2, June 1991")
#!/usr/bin/env python3

import os,sys
sys.dont_write_bytecode = True
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from empty_trash import empty_trash

def createFileSystemTab(initial_path, parent):
    widget = QWidget()
    layout = QVBoxLayout(widget)
      # Set spacing and margins for padding
    layout.setSpacing(30)  # Space between items
    layout.setContentsMargins(20, 20, 20, 20)  # Margins around the layout

    list_view = QListView()
    model = QFileSystemModel()
    model.setRootPath(initial_path)
    list_view.setModel(model)
    list_view.setRootIndex(model.index(initial_path))
   
    layout.addWidget(list_view)

    # Handle double-click event
    list_view.doubleClicked.connect(lambda index: handleDoubleClick(index, model, parent))

    # Connect right-click action
    list_view.setContextMenuPolicy(Qt.CustomContextMenu)
    list_view.customContextMenuRequested.connect(lambda pos: parent.openFileContextMenu(pos, list_view))

    # Update current directory status
    parent.updateStatusBar(initial_path)

    widget.setLayout(layout)
    return widget

def handleDoubleClick(index, model, parent):
    path = model.filePath(index)
    if os.path.isdir(path):
        parent.updateTabHistory(path)
        parent.updateCurrentTab(path)



