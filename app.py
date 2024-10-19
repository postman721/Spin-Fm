#app.py: Contains the main App class.

#Spin FM v. 2.0 Copyright (c) 2021 JJ Posti <techtimejourney.net> This program comes with ABSOLUTELY NO WARRANTY; for details see: http://www.gnu.org/copyleft/gpl.html.  This is free software, and you are welcome to redistribute it under GPL Version 2, June 1991")
#!/usr/bin/env python3
import sys
sys.dont_write_bytecode = True
from PyQt5.QtWidgets import *
from tabs import Tabs

class App(QMainWindow):

    def __init__(self):
        super().__init__()
        self.title = "Spin FM"
        self.initUI()

    def initUI(self):
        self.setWindowTitle(self.title)
        self.resize(900, 600)
        self.tabs_widget = Tabs(self)
        self.setCentralWidget(self.tabs_widget)
        self.show()
        self.move(QApplication.desktop().availableGeometry().center() - self.frameGeometry().center())
