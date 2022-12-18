#Spin FM v. 2.0 Copyright (c) 2021 JJ Posti <techtimejourney.net> This program comes with ABSOLUTELY NO WARRANTY; for details see: http://www.gnu.org/copyleft/gpl.html.  This is free software, and you are welcome to redistribute it under GPL Version 2, June 1991")
#!/usr/bin/env python3
import os, sys, subprocess, getpass,copy, shutil, time, urllib,magic
from PySide2 import QtCore, QtGui, QtWidgets
from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *
from copy import deepcopy 
from theme import * 
from add_tabs import *

class App(QMainWindow):

    def __init__(self):
        super().__init__()
#Window Definitions		
        self.title= ("Spin FM")
        self.initUI()
    def initUI(self):
        self.setWindowTitle(self.title)
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
        if theme == "green":
            with open("/usr/share/sthemes/green.css","r") as style:
                self.setStyleSheet(style.read())                 
    
class Tabs(QWidget):
    
    def __init__(self, parent):
        super(Tabs, self).__init__(parent)
        self.theme()
        self.layout = QVBoxLayout(self)

#Previous
        self.prev_button = QPushButton('<-', self)
        self.prev_button.setToolTip('<-')
        self.prev_button.clicked.connect(self.changed)
        self.prev_button.clicked.connect(self.changed3) 
        self.prev_button.clicked.connect(self.changed5)         
        self.prev_button.clicked.connect(self.changed7)         

#Next
        self.next_button = QPushButton('->', self)
        self.next_button.setToolTip('->')
        self.next_button.clicked.connect(self.changed2) 
        self.next_button.clicked.connect(self.changed4) 
        self.next_button.clicked.connect(self.changed6) 
        self.next_button.clicked.connect(self.changed8)         
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
        
#Add and close tabs
        self.close_button = QPushButton('Close tabs', self)
        self.close_button.setToolTip('Close tabs.')
        self.close_button.clicked.connect(self.close_tab) 


#Toolbars        
        self.toolbar=QToolBar()
        self.toolbar.addWidget(self.prev_button)
        self.toolbar.addWidget(self.address)
        self.toolbar.addWidget(self.next_button)
        self.toolbar.addWidget(self.close_button)
                     
#Initialize tab screen
        self.tabs = QTabWidget()
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.tabBarDoubleClicked.connect(self.tab_open_doubleclick)
        self.setStyleSheet('''
        QTabWidget::tab-bar {
            alignment: center;
        }''')
#First tab
        self.tab0 = QListView()      
        self.tab0.model = QFileSystemModel()
        self.tab0.model.setFilter(QDir.AllDirs | QDir.Files | QDir.NoDotAndDotDot)
        self.name=getpass.getuser()
        self.home="/home/"
        self.path=  self.home + self.name
        self.tab0.model.setRootPath(self.path)
        self.tab0.setModel(self.tab0.model)
        self.tab0.setRootIndex(self.tab0.model.index(self.path))
        self.tab0.setSelectionMode(QAbstractItemView.ExtendedSelection)
#Into icon mode and standard aligment
        self.tab0.setFlow(QListView.LeftToRight)
        self.tab0.setResizeMode(QListView.Adjust)
        self.tab0.setViewMode(QListView.IconMode)
        self.tab0.setGridSize(QtCore.QSize(84, 84))		  
        ix = self.tabs.addTab(self.tab0, "Tab")
        self.tabs.setCurrentIndex(ix)
        currentIndex=self.tabs.currentIndex()
        currentWidget=self.tabs.currentWidget()
        print(currentIndex)
        self.tabs.setTabText(currentIndex, str("Tab "+str(currentIndex)))
        self.tab0.clicked.connect(self.on_treeview2_clicked)
        
        self.tab0.doubleClicked.connect(self.doubles)
                
#Create Layouts
        self.tab0.layout = QHBoxLayout(self)
        self.tab0.setLayout(self.tab0.layout)
        
        self.tab0.vertical = QVBoxLayout(self)
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
        if theme == "green":
            with open("/usr/share/sthemes/green.css","r") as style:
                self.setStyleSheet(style.read())                    
#Button connectors
    def open_with_clicked(self):
        try:
            self.opens_me()
        except Exception as e:
            print (e)	

##########################
#Index 0 back & Forward
###########################
#Going back button function        
    def changed(self,current):
        if self.tabs.currentIndex() == 0:
            try:
                self.prev_button.clicked.connect(self.changed)				                      
                for lines in self.pathme:
                    x=lines.encode('utf-8')
                    y=x.decode('unicode-escape')
                    self.baseline=os.path.abspath(os.path.join(y, os.pardir))
                    print ("Going back to me: " +  self.baseline)    
                    self.tab0.model.setRootPath(self.baseline)
                    self.tab0.setRootIndex(self.tab0.model.index(self.baseline))
                    self.tab0.model.setRootPath(self.baseline)
                    self.tab0.setRootIndex(self.tab0.model.index(self.baseline))
                    self.status.showMessage(self.baseline)
                    self.basic=os.path.basename(self.baseline)
                    self.address.setText(self.path)
            except Exception as e:
                print (e) 
#Going forward button function        
    def changed2(self,current):
        if self.tabs.currentIndex() == 0:
            try:
                self.next_button.clicked.connect(self.changed2) 
                for lines in self.pathme2:
                    x2=lines.encode('utf-8')
                    y2=x2.decode('unicode-escape')
                    self.baseline2=y2
                    print ("Forward to me: " +  self.baseline2)
            
                    self.tab0.model.setRootPath(self.baseline2)
                    self.tab0.setRootIndex(self.tab0.model.index(self.baseline2))
                    self.tab0.model.setRootPath(self.baseline2)
                    self.tab0.setRootIndex(self.tab0.model.index(self.baseline2))
                    self.status.showMessage(self.baseline2)
                    self.basic=os.path.dirname(self.baseline2)
                    self.address.setText(self.baseline2)            
            except Exception as e:
                print (e)

##########################
#Index 1 back & Forward
###########################
#Going back button function        
    def changed3(self,current):
        if self.tabs.currentIndex() == 1:                                             			
            try:  
                self.prev_button.clicked.connect(self.changed3)                			                    
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
                    self.address.setText(self.baseline)
            except Exception as e:
                print (e) 
#Going forward button function        
    def changed4(self,current):
        if self.tabs.currentIndex() == 1:
            try:
                self.next_button.clicked.connect(self.changed4)                  				
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

##########################
#Index 2 back & Forward
###########################
#Going back button function        
    def changed5(self,current):
        if self.tabs.currentIndex() == 2:                                             			
            try:  
                self.prev_button.clicked.connect(self.changed5)                			                    
                for lines in self.pathme:
                    x=lines.encode('utf-8')
                    y=x.decode('unicode-escape')
                    self.baseline=os.path.abspath(os.path.join(y, os.pardir))
                    print ("Going back to me: " +  self.baseline)    
                    self.tab2.model.setRootPath(self.baseline)
                    self.tab2.setRootIndex(self.tab2.model.index(self.baseline))
                    self.tab2.model.setRootPath(self.baseline)
                    self.tab2.setRootIndex(self.tab2.model.index(self.baseline))
                    self.status.showMessage(self.baseline)
                    self.basic=os.path.basename(self.baseline)
                    self.address.setText(self.baseline)
            except Exception as e:
                print (e) 
#Going forward button function        
    def changed6(self,current):
        if self.tabs.currentIndex() == 2:
            try:
                self.next_button.clicked.connect(self.changed6)                  				
                for lines in self.pathme2:
                    x2=lines.encode('utf-8')
                    y2=x2.decode('unicode-escape')
                    self.baseline2=y2
                    print ("Forward to me: " +  self.baseline2)            
                    self.tab2.model.setRootPath(self.baseline2)
                    self.tab2.setRootIndex(self.tab2.model.index(self.baseline2))
                    self.tab2.model.setRootPath(self.baseline2)
                    self.tab2.setRootIndex(self.tab2.model.index(self.baseline2))
                    self.status.showMessage(self.baseline2)
                    self.basic=os.path.dirname(self.baseline2)
                    self.address.setText(self.baseline2)            
            except Exception as e:
                print (e)

##########################
#Index 3 back & Forward
###########################
#Going back button function        
    def changed7(self,current):
        if self.tabs.currentIndex() == 3:                                             			
            try:  
                self.prev_button.clicked.connect(self.changed7)                			                    
                for lines in self.pathme:
                    x=lines.encode('utf-8')
                    y=x.decode('unicode-escape')
                    self.baseline=os.path.abspath(os.path.join(y, os.pardir))
                    print ("Going back to me: " +  self.baseline)    
                    self.tab3.model.setRootPath(self.baseline)
                    self.tab3.setRootIndex(self.tab3.model.index(self.baseline))
                    self.tab3.model.setRootPath(self.baseline)
                    self.tab3.setRootIndex(self.tab3.model.index(self.baseline))
                    self.status.showMessage(self.baseline)
                    self.basic=os.path.basename(self.baseline)
                    self.address.setText(self.baseline)
            except Exception as e:
                print (e) 
#Going forward button function        
    def changed8(self,current):
        if self.tabs.currentIndex() == 3:
            try:
                self.next_button.clicked.connect(self.changed8)                  				
                for lines in self.pathme2:
                    x2=lines.encode('utf-8')
                    y2=x2.decode('unicode-escape')
                    self.baseline2=y2
                    print ("Forward to me: " +  self.baseline2)            
                    self.tab3.model.setRootPath(self.baseline2)
                    self.tab3.setRootIndex(self.tab3.model.index(self.baseline2))
                    self.tab3.model.setRootPath(self.baseline2)
                    self.tab3.setRootIndex(self.tab3.model.index(self.baseline2))
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


#About messagebox
    def about(self):
        buttonReply = QMessageBox.question(self, 'Spin FM v.2.0 RC1 Copyright(c)2021 JJ Posti <techtimejourney.net>', "Spin FM is a spinoff of Sequence FM filemanager.The program comes with ABSOLUTELY NO WARRANTY  for details see: http://www.gnu.org/copyleft/gpl.html. This is free software, and you are welcome to redistribute it under GPL Version 2, June 1991. \n\nUsing Tabs: Create Tab 1 from Tab 0. Tab 0 cannot be removed.\n\nTabs can be created by double-clicking an existing selected Tab.\n\nRemove Tabs by clicking Close tabs button while being on the latest created Tab. This button will remove the latest Tab first and then remove the next in line - if clicked again.", QMessageBox.Ok )
        if buttonReply == QMessageBox.Ok:
            print('Ok clicked, messagebox closed.')        

#####################
#QListView on Tabs
##################### 
       	                           
#Remove tabs unless only 1 available.
    def close_tab(self, number_of_tabs):   
        if self.tabs.currentIndex() == 0:
            self.status.showMessage("Cannot remove Tab 0.")			  
            return
        if self.tabs.currentIndex() == 1 and self.tabs.count() == 2:
            self.tabs.removeTab(int(self.tabs.currentIndex()))			  
            return
        if self.tabs.currentIndex() == 2 and self.tabs.count() == 3:
            self.tabs.removeTab(int(self.tabs.currentIndex()))			  
            return
        if self.tabs.currentIndex() == 3 and self.tabs.count() == 4:
            self.tabs.removeTab(int(self.tabs.currentIndex()))			  
            return                    	                                                                                                                                                      		    
        else:      
            print ("Tabs available: "+str(self.tabs.count()))
                     
    def tab_open_doubleclick(self):        
        if self.tabs.count() <= 3:
            print(self.tabs.count())						 
            new_tabs(self)              
        else:
            print("Tab number at max")
            self.status.showMessage("Tab number at max.")
################################
#Navigation tabs 0-3
################################
    def navigate(self):
        if self.tabs.currentIndex() == 0:
            print("Current index is 0.")
            try:
                self.path=self.address.text()
                if os.path.isdir(self.path):           
                    self.tab0.model.setRootPath(self.path)
                    self.tab0.setRootIndex(self.tab0.model.index(self.path))
                    self.tab0.model.setRootPath(self.path)
                    self.tab0.setRootIndex(self.tab0.model.index(self.path))
                    self.status.showMessage(self.path)
                    self.basic=os.path.basename(self.path)
            except Exception as e:
                print (e)	                     
        if self.tabs.currentIndex() == 1:
            print("Current index is 1.")					
            try:
                self.path=self.address.text()
                if os.path.isdir(self.path):           
                    self.tab1.model.setRootPath(self.path)
                    self.tab1.setRootIndex(self.tab1.model.index(self.path))
                    self.tab1.model.setRootPath(self.path)
                    self.tab1.setRootIndex(self.tab1.model.index(self.path))
                    self.status.showMessage(self.path)
                    self.basic=os.path.basename(self.path)
            except Exception as e:
                print (e)	                       
        if self.tabs.currentIndex() == 2:
            print("Current index is 2.")					
            try:
                self.path=self.address.text()
                if os.path.isdir(self.path):           
                    self.tab2.model.setRootPath(self.path)
                    self.tab2.setRootIndex(self.tab2.model.index(self.path))
                    self.tab2.model.setRootPath(self.path)
                    self.tab2.setRootIndex(self.tab2.model.index(self.path))
                    self.status.showMessage(self.path)
                    self.basic=os.path.basename(self.path)
            except Exception as e:
                print (e)	                      
        if self.tabs.currentIndex() == 3:
            print("Current index is 3.")					
            try:
                self.path=self.address.text()
                if os.path.isdir(self.path):           
                    self.tab3.model.setRootPath(self.path)
                    self.tab3.setRootIndex(self.tab3.model.index(self.path))
                    self.tab3.model.setRootPath(self.path)
                    self.tab3.setRootIndex(self.tab3.model.index(self.path))
                    self.status.showMessage(self.path)
                    self.basic=os.path.basename(self.path)                                                         
                else:    	
                    self.status.showMessage("Not a folder path.")
                return self.path
            except Exception as e:
                print (e)	
                        
##########################
#Supporting for tabs 0-3
##########################
#Open location double-click comes & Go back/Go forward
    def doubles(self, index):
#Tab0
        if self.tabs.currentIndex() == 0:
            indexItem = self.tab0.model.index(index.row(), 0, index.parent())
            filepath = self.tab0.model.filePath(indexItem)
            print(filepath)
            self.address.setText(filepath)
            if os.path.isdir(filepath):
                self.tab0.model.setRootPath(filepath)
                self.tab0.setRootIndex(self.tab0.model.index(filepath))
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
#Tab1
        if self.tabs.currentIndex() == 1:
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

#Tab2
        if self.tabs.currentIndex() == 2:
            indexItem = self.tab2.model.index(index.row(), 0, index.parent())
            filepath = self.tab2.model.filePath(indexItem)
            print(filepath)
            self.address.setText(filepath)
            if os.path.isdir(filepath):
                self.tab2.model.setRootPath(filepath)
                self.tab2.setRootIndex(self.tab2.model.index(filepath))
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
#Tab3
        if self.tabs.currentIndex() == 3:
            indexItem = self.tab3.model.index(index.row(), 0, index.parent())
            filepath = self.tab3.model.filePath(indexItem)
            print(filepath)
            self.address.setText(filepath)
            if os.path.isdir(filepath):
                self.tab3.model.setRootPath(filepath)
                self.tab3.setRootIndex(self.tab3.model.index(filepath))
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

#Object Size data from selection - supporting 0-3 tabs
######################################################
#Tab0
    def on_treeview2_clicked(self, index):
        try:		
            indexItem = self.tab0.model.index(index.row(), 0, index.parent())
            global filepath
            filepath = self.tab0.model.filePath(indexItem)
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
#Tab1            
    def on_treeview2_clicked2(self, index):
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
#Tab2
    def on_treeview2_clicked3(self, index):
        try:		
            indexItem = self.tab2.model.index(index.row(), 0, index.parent())
            global filepath
            filepath = self.tab2.model.filePath(indexItem)
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
#Tab3
    def on_treeview2_clicked4(self, index):
        try:		
            indexItem = self.tab3.model.index(index.row(), 0, index.parent())
            global filepath
            filepath = self.tab3.model.filePath(indexItem)
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
    def actionlist0(self):
        if len(self.actions) != 0:
            del self.actions[:]    		
        try:
            if self.tabs.currentIndex() == 0:			
                print("Tab0 list.")			
                text=(self.tab0.selectedIndexes())
                print(text)
                for lines in text:
                    text2 = lines.data(Qt.DisplayRole)
                    dir_path = os.path.dirname(os.path.realpath(filepath))
                    line='/' 
                    final=dir_path + line + text2
                    print(final)
                    self.actions.append(final)
                    self.status.showMessage(str( "Added for actions. Select your destination. "))
                
            if self.tabs.currentIndex() == 1:
                print("Tab1 list.")			
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
                    
            if self.tabs.currentIndex() == 2:
                print("Tab2 list.")			
                text=(self.tab2.selectedIndexes())
                print(text)
                for lines in text:
                    text2 = lines.data(Qt.DisplayRole)
                    dir_path = os.path.dirname(os.path.realpath(filepath))
                    line='/' 
                    final=dir_path + line + text2
                    print(final)
                    self.actions.append(final)
                    self.status.showMessage(str( "Added for actions. Select your destination. "))
                    
            if self.tabs.currentIndex() == 3:
                print("Tab3 list.")			
                text=(self.tab3.selectedIndexes())
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
                if self.tabs.currentIndex() != 0:
                    self.status.showMessage(str( "Permenant delete only available on Tab 0. "))
                    print("Perment delete blocked. Only available on Tab0")
                    				
                if self.tabs.currentIndex() == 0:
                    self.status.showMessage(str( "Permenant delete on Tab0. "))
                    print("Perment delete on Tab0")	    
                    list_string=(self.tab0.selectedIndexes())
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
            
#Delete objects 
    def delete_objects(self):
        self.maketrash()			
        buttonReply = QMessageBox.question(self, 'Move objects to trash?',  ' \nObject with same name will be overwritten, if existing in trash folder. Press No now if you are not sure. ')
        if buttonReply == QMessageBox.Yes:
            try:
                if self.tabs.currentIndex() == 0:					
                    list_string=(self.tab0.selectedIndexes())
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

                if self.tabs.currentIndex() == 1:					
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

                if self.tabs.currentIndex() == 2:					
                    list_string=(self.tab2.selectedIndexes())
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

                if self.tabs.currentIndex() == 3:					
                    list_string=(self.tab3.selectedIndexes())
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
                        
    def pasteto(self):
        if not self.actions:
            print ("Nothing to do.")
        else:        		
            try:            			
                self.listme=(self.actions)                
                buttonReply = QMessageBox.question(self, 'Proceed?', "Object with same name will be overwritten. If unsure press Cancel now.", QMessageBox.Cancel | QMessageBox.Ok  )
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
                buttonReply = QMessageBox.question(self, 'Proceed?', "Object with same name will be overwritten. If unsure press Cancel now.", QMessageBox.Cancel | QMessageBox.Ok  )
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
