#!/usr/bin/env python3
# empty_trash.py
# Disable the creation of __pycache__ directories
sys.dont_write_bytecode = True
import os
import shutil

def empty_trash():
    """Empties the trash directory."""
    trash_dir = os.path.expanduser("~/.local/share/Trash/files")
    if os.path.exists(trash_dir):
        for filename in os.listdir(trash_dir):
            file_path = os.path.join(trash_dir, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                print(f"Failed to delete {file_path}. Reason: {e}")
        print("Trash emptied successfully.")
    else:
        print("Trash directory not found.")
