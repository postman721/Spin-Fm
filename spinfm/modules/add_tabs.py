#Spin FM v. 2.0 Copyright (c) 2021 JJ Posti <techtimejourney.net> This program comes with ABSOLUTELY NO WARRANTY; for details see: http://www.gnu.org/copyleft/gpl.html.  This is free software, and you are welcome to redistribute it under GPL Version 2, June 1991")
#!/usr/bin/env python3
from PySide2 import QtCore, QtGui, QtWidgets
from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *
import os, sys, subprocess, getpass,copy, shutil, time, urllib
import magic

tab1= False
tab2= False
tab3= False
tab4= False
#Add new tabs
def new_tabs(self,  label ="Blank"):

    nextIndex=self.tabs.currentIndex() +1
    print ("Next is: " + "self.tab"+str(nextIndex))
    tabme=("self.tab"+str(nextIndex))
    
    if tabme == "self.tab1":
        self.tab1 = QListView()
        print(tabme)
        self.tab1.model = QFileSystemModel()
        self.tab1.model.setFilter(QDir.AllDirs | QDir.Files | QDir.NoDotAndDotDot)
        self.name=getpass.getuser()
        self.home="/home/"
        self.path=  self.home + self.name
        self.tab1.model.setRootPath(self.path)
        self.tab1.setModel(self.tab1.model)
        self.tab1.setRootIndex(self.tab1.model.index(self.path))
#Into icon mode and standard aligment
        self.tab1.setFlow(QListView.LeftToRight)
        self.tab1.setResizeMode(QListView.Adjust)
        self.tab1.setViewMode(QListView.IconMode)
        self.tab1.setGridSize(QtCore.QSize(84, 84))
        ix = self.tabs.addTab(self.tab1, "Tab")
        self.tabs.setCurrentIndex(ix)
        currentIndex=self.tabs.currentIndex()
        print(currentIndex)
        self.tabs.setTabText(currentIndex, str("Tab "+str(currentIndex)))
        self.tab1.clicked.connect(self.on_treeview2_clicked2)
        self.tab1.doubleClicked.connect(self.doubles)
        self.address.returnPressed.connect(self.navigate)
        tab1= True
        if tab1 == True:
            print ("Index 1 is reserved")

    if tabme == "self.tab2":
        self.tab2 = QListView()
        print(tabme) 
        self.tab2.model = QFileSystemModel()
        self.tab2.model.setFilter(QDir.AllDirs | QDir.Files | QDir.NoDotAndDotDot)
        self.name=getpass.getuser()
        self.home="/home/"
        self.path=  self.home + self.name
        self.tab2.model.setRootPath(self.path)
        self.tab2.setModel(self.tab2.model)
        self.tab2.setRootIndex(self.tab2.model.index(self.path))
#Into icon mode and standard aligment
        self.tab2.setFlow(QListView.LeftToRight)
        self.tab2.setResizeMode(QListView.Adjust)
        self.tab2.setViewMode(QListView.IconMode)
        self.tab2.setGridSize(QtCore.QSize(84, 84))
        ix = self.tabs.addTab(self.tab2, "Tab")
        self.tabs.setCurrentIndex(ix)
        currentIndex=self.tabs.currentIndex()
        print(currentIndex)
        self.tabs.setTabText(currentIndex, str("Tab "+str(currentIndex)))
        self.tab2.clicked.connect(self.on_treeview2_clicked3)
        self.tab2.doubleClicked.connect(self.doubles)
        self.address.returnPressed.connect(self.navigate)
        tab2= True
        if tab2 == True:
            print ("Index 2 is reserved")

    if tabme == "self.tab3":
        self.tab3 = QListView()
        print(tabme)
        self.tab3.model = QFileSystemModel()
        self.tab3.model.setFilter(QDir.AllDirs | QDir.Files | QDir.NoDotAndDotDot)
        self.name=getpass.getuser()
        self.home="/home/"
        self.path=  self.home + self.name
        self.tab3.model.setRootPath(self.path)
        self.tab3.setModel(self.tab3.model)
        self.tab3.setRootIndex(self.tab3.model.index(self.path))
#Into icon mode and standard aligment
        self.tab3.setFlow(QListView.LeftToRight)
        self.tab3.setResizeMode(QListView.Adjust)
        self.tab3.setViewMode(QListView.IconMode)
        self.tab3.setGridSize(QtCore.QSize(84, 84))
        ix = self.tabs.addTab(self.tab3, "Tab")
        self.tabs.setCurrentIndex(ix)
        currentIndex=self.tabs.currentIndex()
        print(currentIndex)
        self.tabs.setTabText(currentIndex, str("Tab "+str(currentIndex)))
        self.tab3.clicked.connect(self.on_treeview2_clicked4)
        self.tab3.doubleClicked.connect(self.doubles)
        self.address.returnPressed.connect(self.navigate)
        tab3= True
        if self.tab3 == True:
            print ("Index 3 is reserved")
            
    if tabme == "self.tab4":
        self.tab4 = QListView()
        print(tabme)
        self.tab4.model = QFileSystemModel()
        self.tab4.model.setFilter(QDir.AllDirs | QDir.Files | QDir.NoDotAndDotDot)
        self.name=getpass.getuser()
        self.home="/home/"
        self.path=  self.home + self.name
        self.tab4.model.setRootPath(self.path)
        self.tab4.setModel(self.tab4.model)
        self.tab4.setRootIndex(self.tab4.model.index(self.path))
#Into icon mode and standard aligment
        self.tab4.setFlow(QListView.LeftToRight)
        self.tab4.setResizeMode(QListView.Adjust)
        self.tab4.setViewMode(QListView.IconMode)
        self.tab4.setGridSize(QtCore.QSize(84, 84))
        ix = self.tabs.addTab(self.tab4, "Tab")
        self.tabs.setCurrentIndex(ix)
        currentIndex=self.tabs.currentIndex()
        print(currentIndex)
        self.tabs.setTabText(currentIndex, str("Tab "+str(currentIndex)))
        self.tab4.clicked.connect(self.on_treeview2_clicked5)
        self.tab4.doubleClicked.connect(self.doubles)
        self.address.returnPressed.connect(self.navigate)
        tab3= True
        if self.tab3 == True:
            print ("Index 3 is reserved")            
