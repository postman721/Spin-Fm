#Empty the trash

#Spin FM v. 2.0 Copyright (c) 2021 JJ Posti <techtimejourney.net> This program comes with ABSOLUTELY NO WARRANTY; for details see: http://www.gnu.org/copyleft/gpl.html.  This is free software, and you are welcome to redistribute it under GPL Version 2, June 1991")
#!/usr/bin/env python3

import os,sys
sys.dont_write_bytecode = True
import sys
import ctypes
import subprocess

def empty_trash():
    """Empty the Trash on Linux using gio command."""
    try:
        # Use gio to empty the trash
        subprocess.run(['gio', 'trash', '--empty'], check=True)
        print("Trash emptied successfully on Linux.")
    except subprocess.CalledProcessError as e:
        print(f"Failed to empty trash on Linux: {e}")

if __name__ == "__main__":
    empty_trash()
