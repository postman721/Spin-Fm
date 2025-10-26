#!/usr/bin/env python3
#Spin FM v. 2.0 Copyright (c) 2021 JJ Posti <techtimejourney.net> This program comes with ABSOLUTELY NO WARRANTY; for details see: http://www.gnu.org/copyleft/gpl.html.  This is free software, and you are welcome to redistribute it under GPL Version 2, June 1991")

import sys
sys.dont_write_bytecode = True

# Use the compatibility layer so it prints which backend is used
from qt_compat import QApplication

def main():
    # 1) Create QApplication FIRST
    app = QApplication(sys.argv)

    # 2) Only now import modules that might create widgets at import time
    from main_window import MainWindow

    # 3) Start UI
    main_window = MainWindow()
    main_window.show()
    print("[main] Application started.")
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
