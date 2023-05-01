#Keypress events

#Spin FM v. 2.0 Copyright (c) 2021 JJ Posti <techtimejourney.net> This program comes with ABSOLUTELY NO WARRANTY; for details see: http://www.gnu.org/copyleft/gpl.html.  This is free software, and you are welcome to redistribute it under GPL Version 2, June 1991")
#!/usr/bin/env python3
from PySide2 import QtCore, QtGui, QtWidgets
from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *

def keybindings(self, event):
    try:
        if event.key()==Qt.Key_Delete:
            self.delete_objects()
        if event.key()==Qt.Key_Control:
            self.actionlist0()
            print (len(self.actions))
        if event.key()==Qt.Key_Escape:           
            del self.actions[:]
            self.status.showMessage("Buffer cleared")
            print ("Buffer cleared")   				                                        			                 			               
        else:
            pass
    except Exception as e:
        print ("Nothing is selected.")
