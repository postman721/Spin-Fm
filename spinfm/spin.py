#Spin FM v. 1.0 Copyright (c) 2021 JJ Posti <techtimejourney.net> This program comes with ABSOLUTELY NO WARRANTY; for details see: http://www.gnu.org/copyleft/gpl.html.  This is free software, and you are welcome to redistribute it under GPL Version 2, June 1991")
#!/usr/bin/env python3
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
import os, sys, subprocess, getpass,copy, shutil, time, urllib
from copy import deepcopy
import magic
#Needs python-magic

#SFM Modules
from theme import *
class Main(QMainWindow):
    def __init__(self, *args, **kwargs):
        super(Main, self).__init__(*args, **kwargs)        
#Window Definitions		
        self.title= ("Spin FM")
        self.initUI()
    def initUI(self):
        self.setWindowTitle(self.title)
        self.move(QApplication.desktop().screen().rect().center()- self.rect().center())
        self.resize(900,600)
        self.theme()
#List
        self.list = QListWidget()
        self.list.setStyleSheet("QListWidget {border: none;} QListWidget::item { margin-top:14px; margin-bottom:14px  }")
        self.list.addItem("Home")
        self.list.addItem("Trash")
        self.list.addItem("Root")
        self.list.currentItemChanged.connect(self.clicked)
        self.list.setFixedSize(100,600)       
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

#Buttons
        self.image_button = QPushButton('Open an image', self)
        self.image_button.setCheckable(True)
        self.image_button.setToolTip('Open an image')
        self.image_button.clicked.connect(self.images) 
                        
          
#Toolbars        
        self.toolbar=QToolBar()
        self.toolbar.addWidget( self.image_button)
        self.toolbar.addWidget(self.address)
        self.toolbar2=QToolBar()
        self.toolbar2.hide()
                        
#Treeview setup folders/files       
        self.treeview = QListView(self)
        self.treeview.model = QFileSystemModel()
        self.treeview.model.setFilter(QDir.AllDirs | QDir.Files | QDir.NoDotAndDotDot)
        self.path=self.address.text()
        self.name=getpass.getuser()
        self.home="/home/"
        self.path=self.home + self.name
        self.treeview.model.setRootPath(self.path)
        self.treeview.setModel(self.treeview.model)
        self.treeview.setRootIndex(self.treeview.model.index(self.path))
        self.treeview.clicked.connect(self.on_treeview2_clicked)
        self.treeview.doubleClicked.connect(self.doubles)
        self.treeview.setSelectionMode(QAbstractItemView.ExtendedSelection)

#Into icon mode and standard aligment
        self.treeview.setFlow(QListView.LeftToRight)
        self.treeview.setResizeMode(QListView.Adjust)
        self.treeview.setViewMode(QListView.IconMode)
        self.treeview.setGridSize(QtCore.QSize(84, 84))
#Read files
        self.read = QTextEdit()
        self.read.resize(640, 480)
        self.read.setReadOnly(True)                
        
#Action list & image holder
        self.actions=[]                    
        self.image = QLabel(self)
################################
#Layouts
################################          
        self.setCentralWidget(QWidget(self))
        self.vertical = QVBoxLayout()
        self.horizontal = QHBoxLayout()
        self.horizontal.addWidget(self.list)
        self.vertical.addWidget(self.toolbar)
        self.vertical.addWidget(self.toolbar2)
        self.horizontal.addWidget(self.treeview)
        self.vertical.addLayout(self.horizontal)
        self.vertical.addWidget(self.image)
        self.vertical.addWidget(self.status)
        self.centralWidget().setLayout(self.vertical)
        self.status.showMessage("Select objects for actions from the right side.")                             
##############
#List function
###############
    def clicked(self,current,previous):        
        current=self.list.currentItem().text()
        if current == "Home":
            self.name=getpass.getuser()
            self.home="/home/"
            self.path=self.home + self.name
            self.treeview.model.setRootPath(self.path)
            self.treeview.setRootIndex(self.treeview.model.index(self.path))
            self.treeview.model.setRootPath(self.path)
            self.treeview.setRootIndex(self.treeview.model.index(self.path))

            self.address.setText(self.path)
            self.treeview.model.setRootPath(self.path)
            self.treeview.setModel(self.treeview.model)
            self.treeview.setRootIndex(self.treeview.model.index(self.path))
            self.status.showMessage("/home/" + self.name)

        elif current == "Trash":
            self.maketrash()
            self.name=getpass.getuser()
            self.home="/home/"
            self.trash="/trash"
            self.path=self.home + self.name + self.trash
            self.treeview.model.setRootPath(self.path)
            self.treeview.setRootIndex(self.treeview.model.index(self.path))
            self.treeview.model.setRootPath(self.path)
            self.treeview.setRootIndex(self.treeview.model.index(self.path))

            self.address.setText(self.path)
            self.treeview.model.setRootPath(self.path)
            self.treeview.setModel(self.treeview.model)
            self.treeview.setRootIndex(self.treeview.model.index(self.path))
            self.status.showMessage(self.path)
            
        elif current == "Root":
            self.maketrash()
            self.root="/"
            self.treeview.model.setRootPath(self.root)
            self.treeview.setRootIndex(self.treeview.model.index(self.root))
            self.treeview.model.setRootPath(self.path)
            self.treeview.setRootIndex(self.treeview.model.index(self.path))

            self.address.setText(self.root)
            self.treeview.model.setRootPath(self.root)
            self.treeview.setModel(self.treeview.model)
            self.treeview.setRootIndex(self.treeview.model.index(self.root))
            self.status.showMessage("/")
                                                 
#################################
#Button connectors
################################		      		            
    @pyqtSlot()
    def open_with_clicked(self):
        try:
            self.opens_me()
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
#add other required actions
        self.menu.popup(QtGui.QCursor.pos())
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
##################
#Read text files            
##################
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
############
#Open images
#############
    def images(self):
        if self.image_button.isChecked():
            try:
                self.treeview.hide()
                self.list.hide()
                self.image.setPixmap(QPixmap(self.address.text()))
                self.image.show()
                self.toolbar.hide()
                self.toolbar2.addWidget(self.image_button)
                self.toolbar2.show()
                self.status.showMessage("Press Open an image button to hide.")            
            except Exception as e:
                print("No image selected")
                self.image_button.setChecked(False)
        else:
            self.image.hide()
            self.resize(900,600)
            self.toolbar.addWidget(self.image_button)
            self.toolbar.show()
            self.toolbar2.hide()
            self.list.show()
            self.treeview.show()
            self.treeview.show()
            self.status.showMessage("Select objects for actions from the right side.")                                           			                 			                  
################################
#About messagebox
################################
    def about(self):
        buttonReply = QMessageBox.question(self, 'Spin FM v.1.0 beta Copyright(c)2021 JJ Posti <techtimejourney.net>', "Spin FM is a spinoff of Sequence FM filemanager.The program comes with ABSOLUTELY NO WARRANTY  for details see: http://www.gnu.org/copyleft/gpl.html. This is free software, and you are welcome to redistribute it under GPL Version 2, June 1991.", QMessageBox.Ok )
        if buttonReply == QMessageBox.Ok:
            print('Ok clicked, messagebox closed.')                
################################
#View.
################################
    def doubles(self, index):
        indexItem = self.treeview.model.index(index.row(), 0, index.parent())
        filepath = self.treeview.model.filePath(indexItem)
        print(filepath)
        self.address.setText(filepath)
        if os.path.isdir(filepath):
            self.treeview.model.setRootPath(filepath)
            self.treeview.setRootIndex(self.treeview.model.index(filepath))
            self.basic=os.path.basename(self.path)
                            		                                
    def on_treeview2_clicked(self, index):
        indexItem = self.treeview.model.index(index.row(), 0, index.parent())
        global filepath
        filepath = self.treeview.model.filePath(indexItem)
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
################################
#Navigation
################################
    def navigate(self):
        try:
            self.path=self.address.text()
            if os.path.isdir(self.path):           
                self.treeview.model.setRootPath(self.path)
                self.treeview.setRootIndex(self.treeview.model.index(self.path))
                self.treeview.model.setRootPath(self.path)
                self.treeview.setRootIndex(self.treeview.model.index(self.path))
                self.status.showMessage(self.path)
                self.basic=os.path.basename(self.path)
            else:    	
                self.status.showMessage("Not a folder path.")
            return self.path
        except Exception as e:
            print (e)			                                   
################################
#Open With program
################################
    def opens_me(self):        
        openme=self.address.text()
        text, ok = QInputDialog.getText(self, 'Open with a program', ' \n Type the name of the program, which you want to use. ')
        if ok:
            try:
                print (text)
                subprocess.Popen([text,  openme])                                                                        
            except Exception as e:
                print (e)                
             				
################################
#Move an object 
################################            
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
##################
#Append to actions
###################
    def actionlist(self):
        if len(self.actions) != 0:
            print ("Clearing old.")
            del self.actions[:]    		
        try:
            text=(self.treeview.selectedIndexes())
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
            print ( self.status.showMessage(" Operation failed."))
################################
#Paste objects
################################            
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
###################
#Delete objects 
####################            
    def delete_objects(self):
        self.maketrash()			
        buttonReply = QMessageBox.question(self, 'Move objects to trash?', ' \n Press No now if you are not sure. ')
        if buttonReply == QMessageBox.Yes:
            try:
                list_string=(self.treeview.selectedIndexes())
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
################################
#Permanent delete 
################################
    def permanent_delete_objects(self):
        self.maketrash()	        			
        buttonReply = QMessageBox.question(self, 'Permanently delete  objects?', ' \n Press No now if you are not sure. ')
        if buttonReply == QMessageBox.Yes:
            try:
                list_string=(self.treeview.selectedIndexes())
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
###########################            				
#Keypress events
###########################        
    def keyPressEvent(self, event):
        try:
            if event.key()==Qt.Key_Delete:
                self.delete_objects()                              			                 			               
            else:
                pass
        except Exception as e:
            print ("Nothing is selected.")
################################
#Rename functions
################################                
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
                        
#Theme class
class Theme(Main):

#################################
#Theme from theme.py
################################
    def theme(self):
        if theme == "dark":
            with open("./themes/dark.css","r") as style:
                self.setStyleSheet(style.read())
        if theme == "blue":
            with open("./themes/blue.css","r") as style:
                self.setStyleSheet(style.read())                                   			        
if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = Theme()
    window.show() 
    sys.exit(app.exec_())
