
Spin FM filemanager v 2.0 Beta Copyright JJ Posti <techtimejourney.net> 2021

2.0 RC1 new features - Sunday 18th of December 2022

Moving to Pyside2:

sudo apt install pyside2-*

- Close tabs button added: This will always close the latest opened tab.

- Copy, paste, move to functionalities improved.

- More tabs added.

- Green theme added.


<br>
<br>

2.0 Beta new features - Sunday 20th of March 2022:
- Tab support added.
- Plenty of code fixes.
- Theme fixes.

- <b>Known issues to be fixed in a near future: Tab focus does not work as expected. If new tab is created, then the filemanager has issues when trying to focus back on the previous tab's file content. </b>

<b> Please notice that this is still a beta release. There might be issues on the code of this release. Be cautious when using.</b>


Quick installation. 

- Place sfm.py and theme.py under same folder.

- Copy: sthemes folder to /usr/share/sthemes:  <b> sudo cp -R themes /usr/share/sthemes </b>
- Make sure permissions are correct: <b>sudo chmod +x /usr/share/sthemes/</b>


- Go into the folder containing sfm.py and theme.py, make those files executable: <b> chmod +x sfm.py theme.py </b>

- Run Spin-FM from the folder: <b> python3 sfm.py </b>

![sfm2](https://user-images.githubusercontent.com/29865797/208311074-e4d040ed-0c51-4df0-8b53-623b37ba97fd.jpg)

![Alternative theme1](https://user-images.githubusercontent.com/29865797/208311079-bb9a26e1-0895-46a9-aca9-aec86d013139.png)
![sfm2](https://user-images.githubusercontent.com/29865797/208311080-bffd7e0f-2278-


![Alternative_theme2](https://user-images.githubusercontent.com/29865797/159177060-9da1b347-e5e0-4762-ba51-8bd0873c0b0f.jpg)

Features. 

- Single pane filemanager
- Copy, paste, move delete, permanent deletion.
- Trash.

- Open with, Open an external program.
- Addressbar navigation.
- Built-ins: Imageviewer, text reader.
- CSS theme support with changable themes.

1.1 Additions:
   - Fixes: open with... function.
   - Adds: back and forward buttons.

<b> About copying and moving: You are better off clicking an object and then pressing and holding Ctrl while selecting all your objects. On some occasions, Experienced issues while selecting purely with a mouse.</b>


                                                                                                                                                
To use Sequence FM you should have, at least, these installed (Debian base as an example):

sudo apt-get install python-pyqt5 python python3 python3-magic



### Planned features for future releases:


- Better integrations with Linux system default applications.
- More themes.
