# gitbook-pdf-export

Powered by safreya

gitbook universal PDF export tool

**This project is based on Python3, mistune and weasyprint**

## File Description

| File/Directory  | Description                                                                                   |
| ----------------- | ----------------------------------------------------------------------------------------------- |
| build           | Path for generating PDF, cannot be deleted                                                    |
| build/readme.md | Indicates files in this directory that cannot be deleted, the directory itself can be deleted |
| end.html        | CSS configuration file, cannot be deleted                                                     |
| [mdconv.py](http://mdconv.py)                | Main program, not to be deleted                                                               |
| start.html      | Main CSS configuration file, not to be deleted                                                |

 Other unspecified files can be deleted.

## Function Description

## FreeBSD 14.1 RELEASE User Guide

Tested under lang/python311, py311-pip, py311-weasyprint, py311-mistune.

### Directory Structure:

I created a directory / under which I placed the gitbook project directory as a whole into directory h .

```
/abc/ ①
├── build/
├── end.html
├── Handbook/ # ②
├── mdconv.py
└── start.html
```

### Installation and Usage Methods

```
# pkg install python311 py311-pip py311-weasyprint py311-mistune
# cd /abc ①
# python mdconv.py Handbook
```

 ① Please replace with your own path

## Windows 10 21H2 User Guide

Tested under Python 3.12.3, pip 24.1.1, mistune 3.0.2, weasyprint 61.2, gtk3-runtime 3.24.31.

### Directory Structure

```
C:\Users\ykla\Desktop\h\
├── build/
├── end.html
├── Handbook/ # 
├── mdconv.py
└── start.html
```

### Installation Method

* Install Python3 and pip3 by visiting https://www.python.org/downloads/, click on "Download Python 3.xx.x" to download. Be sure to check Add Python 3.x to PATH during installation. By default, pip will be installed automatically.
* To install gtk3-runtime, visit https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases and download "gtk3-runtime-3.24.31-2022-01-04-ts-win64.exe" for installation.

> gtk3-runtime is a runtime dependency of weasyprint on Windows, and must be installed.

* **Install mistune and weasyprint**

> ```
> C:\Windows\system32>pip install mistune weasyprint
> ```

### How to use

```
C:\Windows\system32>cd C:\Users\ykla\Desktop\h ①
C:\Users\ykla\Desktop\h>python mdconv.py Handbook
```

① I placed it in the "h" folder on user "ykla" desktop, and placed the gitbook project in the folder h .

> **Note**
>
> If you do not know what the user name is, you can open the task manager by pressing the shortcut keys simultaneously ctrl alt del , click "Users", and you will see it. If the account name is in Chinese, the consequences will be unknown because it has not been tested.

## Linux

Due to the wide variety of Linux distributions and their different versions, even installing the weasyprint module on the most common Ubuntu is very complex. Therefore, this part of the content is left for interested parties to supplement. Contributions are welcome.

## MacOS

 For the fate of the person concerned with this part of the content to supplement. Welcome PR.
