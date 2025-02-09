#!/usr/bin/env python3
# main.py
import sys
# Disable the creation of __pycache__ directories
sys.dont_write_bytecode = True

#Spin FM v. 2.0 Copyright (c) 2021 JJ Posti <techtimejourney.net> This program comes with ABSOLUTELY NO WARRANTY; for details see: http://www.gnu.org/copyleft/gpl.html.  This is free software, and you are welcome to redistribute it under GPL Version 2, June 1991")


import sys
from PyQt5.QtWidgets import QApplication
from main_window import MainWindow

def main():
    app = QApplication(sys.argv)
    main_window = MainWindow()
    main_window.show()
    print("[main] Application started.")
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
