
#Css loader class

#Spin FM v. 2.0 Copyright (c) 2021 JJ Posti <techtimejourney.net> This program comes with ABSOLUTELY NO WARRANTY; for details see: http://www.gnu.org/copyleft/gpl.html.  This is free software, and you are welcome to redistribute it under GPL Version 2, June 1991")
#!/usr/bin/env python3

import os,sys
sys.dont_write_bytecode = True
from PyQt5.QtWidgets import QApplication

class ThemeManager:
    def __init__(self, css_folder):
        self.css_folder = css_folder
        self.current_theme = None

    def load_and_apply_theme(self, theme_name):
        css_file_path = os.path.join(self.css_folder, f"{theme_name}.css")
        if os.path.exists(css_file_path):
            with open(css_file_path, 'r') as css_file:
                css_stylesheet = css_file.read()
                QApplication.instance().setStyleSheet(css_stylesheet)
                self.current_theme = theme_name
        else:
            print(f"CSS file for theme '{theme_name}' not found.")

    def get_available_themes(self):
        return [f.split('.')[0] for f in os.listdir(self.css_folder) if f.endswith('.css')]
