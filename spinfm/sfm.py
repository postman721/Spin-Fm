#Spin FM v. 2.0 Copyright (c) 2021 JJ Posti <techtimejourney.net> This program comes with ABSOLUTELY NO WARRANTY; for details see: http://www.gnu.org/copyleft/gpl.html.  This is free software, and you are welcome to redistribute it under GPL Version 2, June 1991")
#!/usr/bin/env python3
import sys
from PyQt5.QtWidgets import QMainWindow, QApplication, QPushButton, QWidget, QAction, QTabWidget,QVBoxLayout
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import pyqtSlot
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
import os, sys, subprocess, getpass,copy, shutil, time, urllib
from copy import deepcopy
import magic
from theme import * 
class App(QMainWindow):

    def __init__(self):
        super().__init__()
#Window Definitions		
        self.title= ("Spin FM")
        self.initUI()
    def initUI(self):
        self.setWindowTitle(self.title)
        self.move(QApplication.desktop().screen().rect().center()- self.rect().center())
        self.resize(900,600)
        self.tabs_widget = Tabs(self)
        self.setCentralWidget(self.tabs_widget)
        self.theme()
        self.show()

#Theme from theme.py
    def theme(self):
        if theme == "dark":
            with open("/usr/share/sthemes/dark.css","r") as style:
                self.setStyleSheet(style.read())
        if theme == "blue":
            with open("/usr/share/sthemes/blue.css","r") as style:
                self.setStyleSheet(style.read()) 

    
class Tabs(QWidget):
    
    def __init__(self, parent):
        super(QWidget, self).__init__(parent)
        self.theme()
        self.layout = QVBoxLayout(self)
#Next
        self.next_button = QPushButton('<-', self)
        self.next_button.setToolTip('->')
        self.next_button.clicked.connect(self.changed) 

#Previous
        self.prev_button = QPushButton('->', self)
        self.prev_button.setToolTip('->')
        self.prev_button.clicked.connect(self.changed2) 


#Address bar
        self.address=QLineEdit()
        self.name=getpass.getuser()
        self.home="/home/"
        self.combine=self.home + self.name 
        self.address.setText(self.combine)
        self.address.setAlignment(Qt.AlignCenter)
        self.address.returnPressed.connect(self.navigate)         
#Statusbar
        self.status=QStatusBar()

#Toolbars        
        self.toolbar=QToolBar()
        self.toolbar.addWidget(self.next_button)
        self.toolbar.addWidget(self.address)
        self.toolbar.addWidget(self.prev_button)
                     
#Initialize tab screen
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.addTab(self.new_tabs(), "Tab")
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.tabBarDoubleClicked.connect(self.new_tabs)
        
#Create Layouts
        self.tab1.layout = QHBoxLayout(self)
        self.tab1.setLayout(self.tab1.layout)
        
        self.tab1.vertical = QVBoxLayout(self)
        self.layout.addWidget(self.toolbar)
        self.layout.addWidget(self.tabs)

        self.layout.addWidget(self.status)
        self.setLayout(self.layout)

#Action list for copy, move etc.
        self.actions=[]                    

#Go back list
        self.pathme=[]   
        
#Go forward list
        self.pathme2=[]   
        
#Read files
        self.read = QTextEdit()
        self.read.resize(640, 480)
        self.read.setReadOnly(True)
                      
#################################
#Functions begin.
#################################

#Theme from theme.py
    def theme(self):
        if theme == "dark":
            with open("/usr/share/sthemes/dark.css","r") as style:
                self.setStyleSheet(style.read())
        if theme == "blue":
            with open("/usr/share/sthemes/blue.css","r") as style:
                self.setStyleSheet(style.read()) 
#Button connectors
    @pyqtSlot()
    def open_with_clicked(self):
        try:
            self.opens_me()
        except Exception as e:
            print (e)	
 
#Going back button function        
    def changed(self,current):
        if not current:
            current = self.address.text()
            try:                      
                for lines in self.pathme:
                    x=lines.encode('utf-8')
                    y=x.decode('unicode-escape')
                    self.baseline=os.path.abspath(os.path.join(y, os.pardir))
                    print ("Going back to me: " +  self.baseline)    
                    self.tab1.model.setRootPath(self.baseline)
                    self.tab1.setRootIndex(self.tab1.model.index(self.baseline))
                    self.tab1.model.setRootPath(self.baseline)
                    self.tab1.setRootIndex(self.tab1.model.index(self.baseline))
                    self.status.showMessage(self.baseline)
                    self.basic=os.path.basename(self.baseline)
                    self.address.setText(self.path)
            except Exception as e:
                print (e) 
                
#Going forward button function        
    def changed2(self,current):
        if not current:
            try:
                current = self.address.text()                      
                for lines in self.pathme2:
                    x2=lines.encode('utf-8')
                    y2=x2.decode('unicode-escape')
                    self.baseline2=y2
                    print ("Forward to me: " +  self.baseline2)
            
                    self.tab1.model.setRootPath(self.baseline2)
                    self.tab1.setRootIndex(self.tab1.model.index(self.baseline2))
                    self.tab1.model.setRootPath(self.baseline2)
                    self.tab1.setRootIndex(self.tab1.model.index(self.baseline2))
                    self.status.showMessage(self.baseline2)
                    self.basic=os.path.dirname(self.baseline2)
                    self.address.setText(self.baseline2)            
            except Exception as e:
                print (e)

################################
#Right-Click menu
################################
    def contextMenuEvent(self, event):
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
        self.action1.triggered.connect(self.actionlist)
                        
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


#About messagebox

    def about(self):
        buttonReply = QMessageBox.question(self, 'Spin FM v.2.0 beta Copyright(c)2021 JJ Posti <techtimejourney.net>', "Spin FM is a spinoff of Sequence FM filemanager.The program comes with ABSOLUTELY NO WARRANTY  for details see: http://www.gnu.org/copyleft/gpl.html. This is free software, and you are welcome to redistribute it under GPL Version 2, June 1991.", QMessageBox.Ok )
        if buttonReply == QMessageBox.Ok:
            print('Ok clicked, messagebox closed.')        

#####################
#QListView on Tabs
##################### 

#Remove tabs unless only 1 available.
    def close_tab(self, number_of_tabs):   
        if self.tabs.count() < 2:  
            return
        else:      
            self.tabs.removeTab(number_of_tabs)

#Add new tabs
    def new_tabs(self,  label ="Blank"):
        self.tab1 = QListView()      
        self.tab1.model = QFileSystemModel()
        self.tab1.model.setFilter(QDir.AllDirs | QDir.Files | QDir.NoDotAndDotDot)
        self.name=getpass.getuser()
        self.home="/home/"
        self.path=self.home + self.name
        self.tab1.model.setRootPath(self.path)
        self.tab1.setModel(self.tab1.model)
        self.tab1.setRootIndex(self.tab1.model.index(self.path))
        self.tab1.clicked.connect(self.on_treeview2_clicked)
        self.tab1.doubleClicked.connect(self.doubles)
        self.tab1.setSelectionMode(QAbstractItemView.ExtendedSelection)
#Into icon mode and standard aligment
        self.tab1.setFlow(QListView.LeftToRight)
        self.tab1.setResizeMode(QListView.Adjust)
        self.tab1.setViewMode(QListView.IconMode)
        self.tab1.setGridSize(QtCore.QSize(84, 84))		  
        ix = self.tabs.addTab(self.tab1, "Tab")
        self.tabs.setCurrentIndex(ix)
        currentIndex=self.tabs.currentIndex()
        currentWidget=self.tabs.currentWidget()
        print(currentIndex)
        self.tabs.setTabText(currentIndex, str(currentIndex))
         
    def tab_open_doubleclick(self, i):        
        if i == -1: 
            self.new_tabs()  

################################
#Navigation
################################
    def navigate(self):
        try:
            self.path=self.address.text()
            if os.path.isdir(self.path):           
                self.tab1.model.setRootPath(self.path)
                self.tab1.setRootIndex(self.tab1.model.index(self.path))
                self.tab1.model.setRootPath(self.path)
                self.tab1.setRootIndex(self.tab1.model.index(self.path))
                self.status.showMessage(self.path)
                self.basic=os.path.basename(self.path)
            else:    	
                self.status.showMessage("Not a folder path.")
            return self.path
        except Exception as e:
            print (e)	

#Open location double-click comes & Go back/Go forward
    def doubles(self, index):
        indexItem = self.tab1.model.index(index.row(), 0, index.parent())
        filepath = self.tab1.model.filePath(indexItem)
        print(filepath)
        self.address.setText(filepath)
        if os.path.isdir(filepath):
            self.tab1.model.setRootPath(filepath)
            self.tab1.setRootIndex(self.tab1.model.index(filepath))
            self.basic=os.path.basename(self.path)
#Paths: Go back  
        self.pathme.append(filepath)
        try:
            for lines in self.pathme:
                x=lines.encode('utf-8')
                y=x.decode('unicode-escape')
                self.baseline=os.path.abspath(os.path.join(y, os.pardir))
                print ("Back to me: " +  self.baseline)
        except Exception as e:
            print (e)	    
#Go Forward 
        self.pathme2.append(filepath)
        try:
            for lines in self.pathme2:
                x2=lines.encode('utf-8')
                y2=x2.decode('unicode-escape')
                self.baseline2=os.path.dirname(y2)
                print ("Forward to me: " +  y2)            
        except Exception as e:
            print (e)	                   

#Object Size data from selection
    def on_treeview2_clicked(self, index):
        try:		
            indexItem = self.tab1.model.index(index.row(), 0, index.parent())
            global filepath
            filepath = self.tab1.model.filePath(indexItem)
            print(filepath)
            self.address.setText(filepath)
            #File info
            self.info = os.stat(filepath) 
            size_mb=(str(self.info.st_size / (1024 * 1024)))
            size_kb=(str("%.2f" % round(self.info.st_size / (1024.0))))
            modified=(os.path.getmtime(filepath))
            local_time=(str(time.ctime(modified)))
            filetype = magic.open(magic.MAGIC_MIME)
            filetype.load()
            x=str(filetype.file(filepath))
            self.status.showMessage(str( filepath + "  Size on mb: " + size_mb + "  Size on kb:  " + size_kb + "  Last modifed:  " + local_time + " Filetype: " + x))
            self.basic=os.path.basename(self.path)        
        except Exception as e:
            print (e)
            
            
###################
#Object handling
###################
#Rename an object             
    def rename_object(self):
        text, ok = QInputDialog.getText(self, 'Rename an object', ' \n Remember to include the extension as well - if not a folder - if in any doubt CANCEL NOW. ')
        if ok:
            try:			
                print (text)
                print ("Now:", filepath)
                renamepath=os.path.dirname(filepath)
                print ("Rename pathway:", renamepath)
                new_entry= renamepath + '/' + text
                print ("New object location after renaming is:", new_entry)
                subprocess.Popen(['mv', filepath , new_entry])
            except Exception as e:
                print("Error occured.")   
#Make new directory
    def newdir(self,widget):
        try:
            self.path=self.address.text()
            if os.path.isdir(self.path):
                os.chdir(self.path)
                makefolder=os.makedirs('Newfolder')
                print (os.getcwd())
                makefolder		           
        except Exception as e:
            print (e)                    			
#Make new empty text file
    def newfile(self,widget):
        try:
            self.path=self.address.text()
            if os.path.isdir(self.path):
                os.chdir(self.path)
                newtext=os.mknod('Newtext.txt')
                print (os.getcwd())
                newtext
        except Exception as e:
            print (e)        

#Open With program
    def opens_me(self):        
        openme=filepath
        text, ok = QInputDialog.getText(self, 'Open with a program', ' \n Type the name of the program, which you want to use. ')
        if ok:
            try:
                print (text)
                if os.path.isdir(openme):
                    print("This is a folder. Not opening")
                else:
                    subprocess.Popen([text,  openme])
            except Exception as e:
                print (e)                
                
#Read text files            
    def readme(self):
        try:
            self.read.setHidden(not self.read.isHidden())
            read=open(self.address.text()).read()            
        except Exception as e:
            print ("Nothing to read.")
            self.read.hide()
        else:
            self.read.setPlainText(read)
            self.read.setPlainText(read)
            self.status.showMessage("Press Read a text file again to hide the reader.")  

####################
#Make trash folder
####################
    def maketrash(self):
        name=getpass.getuser()
        uhome="/home/"
        trash="/trash"
        combine1=uhome + name
        os.chdir(combine1)
        if os.path.exists("trash"):
            pass
        else:                
            makefolder=os.makedirs('trash') 

##############################
#Copying/Deleting/Moving etc.
##############################

#Append to actionlist
    def actionlist(self):
        if len(self.actions) != 0:
            print ("Clearing old.")
            del self.actions[:]    		
        try:
            text=(self.tab1.selectedIndexes())
            print(text)
            for lines in text:
                text2 = lines.data(Qt.DisplayRole)
                dir_path = os.path.dirname(os.path.realpath(filepath))
                line='/' 
                final=dir_path + line + text2
                print(final)
                self.actions.append(final)
                self.status.showMessage(str( "Added for actions. Select your destination. "))
        except Exception as e:
            print (self.status.showMessage(" Operation failed."))


#Permanent delete 
    def permanent_delete_objects(self):
        self.maketrash()	        			
        buttonReply = QMessageBox.question(self, 'Permanently delete  objects?', ' \n Press No now if you are not sure. ')
        if buttonReply == QMessageBox.Yes:
            try:
                list_string=(self.tab1.selectedIndexes())
                for lines in list_string:
                    text = lines.data(Qt.DisplayRole)
                    dir_path = os.path.dirname(os.path.realpath(filepath))
                    line='/' 
                    final=dir_path + line + text
                    subprocess.Popen(["rm" , "-r" , final])
                    self.status.showMessage("Objects permanently deleted.")                                                                        			
            except Exception as e:
                print (e)
        if buttonReply == QMessageBox.No:
            pass

    def pasteto(self):
        if not self.actions:
            print ("Nothing to do.")
        else:        		
            try:            			
                self.listme=(self.actions)                
                buttonReply = QMessageBox.question(None, 'Proceed?', "Object with same name will be overwritten. If unsure press Cancel now.", QMessageBox.Cancel | QMessageBox.Ok  )
                if buttonReply == QMessageBox.Ok:
                    print('Ok clicked, messagebox closed.')
                    for lines in self.listme:
                        x=lines.encode('utf-8')
                        y=x.decode('unicode-escape')
                        print (y)
                        subprocess.Popen(["cp", "-r" , y, self.address.text()])
                        self.status.showMessage(str( " Copied to: " + self.address.text()))
                if buttonReply == QMessageBox.Cancel:
                    print ("Do not proceed. --> Going back to the program.")
                    del self.actions[:]                            
            except Exception as e:
                print ( self.status.showMessage("Copying failed."))   

#Move an object 
    def move_final(self):
        if not self.actions:
            print ("Nothing to do.")
        else:        		
            try:            			
                self.listme=(self.actions)                
                buttonReply = QMessageBox.question(None, 'Proceed?', "Object with same name will be overwritten. If unsure press Cancel now.", QMessageBox.Cancel | QMessageBox.Ok  )
                if buttonReply == QMessageBox.Ok:
                    print('Ok clicked, messagebox closed.')
                    for lines in self.listme:
                        x=lines.encode('utf-8')
                        y=x.decode('unicode-escape')
                        print (y)
                        subprocess.Popen(["mv" , y, self.address.text()])
                        self.status.showMessage(str( " Moved to: " + self.address.text()))
                if buttonReply == QMessageBox.Cancel:
                    print ("Do not proceed. --> Going back to the program.")
                    del self.actions[:]                            
            except Exception as e:
                print ( self.status.showMessage("Moving failed."))       

#Delete objects 
    def delete_objects(self):
        self.maketrash()			
        buttonReply = QMessageBox.question(self, 'Move objects to trash?',  ' \nObject with same name will be overwritten, if existing in trash folder. Press No now if you are not sure. ')
        if buttonReply == QMessageBox.Yes:
            try:
                list_string=(self.tab1.selectedIndexes())
                for lines in list_string:
                    text = lines.data(Qt.DisplayRole)
                    dir_path = os.path.dirname(os.path.realpath(filepath))
                    line='/' 
                    final=dir_path + line + text
                    name=getpass.getuser()
                    uhome="/home/"
                    trash="/trash"
                    combine1=uhome + name + trash
                    subprocess.Popen(["mv" , final , combine1])
                    self.status.showMessage("Objects trashed.")
            except Exception as e:
                print (e)
        if buttonReply == QMessageBox.No:
             pass  

#Keypress events
    def keyPressEvent(self, event):
        try:
            if event.key()==Qt.Key_Delete:
                self.delete_objects()                              			                 			               
            else:
                pass
        except Exception as e:
            print ("Nothing is selected.")
            	
if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = App()
    sys.exit(app.exec_())
