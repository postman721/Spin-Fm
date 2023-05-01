#Right Click menu.

#Spin FM v. 2.0 Copyright (c) 2021 JJ Posti <techtimejourney.net> This program comes with ABSOLUTELY NO WARRANTY; for details see: http://www.gnu.org/copyleft/gpl.html.  This is free software, and you are welcome to redistribute it under GPL Version 2, June 1991")
#!/usr/bin/env python3
from PySide2 import QtCore, QtGui, QtWidgets
from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *

def menu(self, event):
    
    self.menu = QMenu(self)
        
    self.newdir1 = self.menu.addAction('Make a new directory')
    self.newdir1.triggered.connect(self.newdir)
        
    self.newfile1 = self.menu.addAction('Make a new text file')
    self.newfile1.triggered.connect(self.newfile)

    self.sepa = self.menu.addSeparator()

    self.rename1 = self.menu.addAction('Rename object')
    self.rename1.triggered.connect(self.rename_object)
    self.sep1 = self.menu.addSeparator()

    self.action1 = self.menu.addAction('Select for copying or moving')
    self.action1.triggered.connect(self.actionlist0)
                    
    self.paste = self.menu.addAction('Copy to...')
    self.paste.triggered.connect(self.pasteto)
    self.sep1 = self.menu.addSeparator()

    self.sep2q = self.menu.addSeparator()

    self.move3 = self.menu.addAction('Move to...')
    self.move3.triggered.connect(self.move_final)
        
    self.sep2 = self.menu.addSeparator()
        
    self.for1 = self.menu.addAction('Delete objects')
    self.for1.triggered.connect(self.delete_objects)
        
    self.for2 = self.menu.addAction('Permanently delete objects')
    self.for2.triggered.connect(self.permanent_delete_objects)
                
    self.sepx = self.menu.addSeparator()
        
    self.openwiths = self.menu.addAction('Open with...')
    self.openwiths.triggered.connect(self.open_with_clicked)
        
    self.readmes = self.menu.addAction('Read a text file')
    self.readmes.triggered.connect(self.readme)
        
    self.about1 = self.menu.addAction('About')
    self.about1.triggered.connect(self.about)        
#Add other required actions
    self.menu.popup(QtGui.QCursor.pos())
