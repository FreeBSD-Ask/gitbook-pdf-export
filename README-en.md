# GitBook Project Universal PDF Export Tool

Original author: safreya

**For English in [README-en.md](./README-en.md)**

A universal PDF export tool for GitBook.

**This project is based on Python3, mistune, and weasyprint**

## File Description

| File/Directory | Description |
|:---:|:---:|
| build | Path for generating PDFs, should not be deleted |
| build/readme.md | File indicating that this directory should not be deleted, but the file itself can be removed |
| end.html | CSS configuration file, should not be deleted |
| mdconv.py | Main program, should not be deleted |
| start.html | Main CSS configuration file, should not be deleted |

All other files not mentioned can be deleted.


## FreeBSD 14.1 RELEASE Instructions

Tested with lang/python311, py311-pip, py311-weasyprint, and py311-mistune.

### Directory Structure:

I created the `abc` directory under the `/` directory and placed the entire GitBook project directory into the `h` directory.

```
/abc/ ①
├── build/
├── end.html
├── Handbook/
├── mdconv.py
└── start.html
```

### Installation and Usage

```
# pkg install python311 py311-pip py311-weasyprint py311-mistune
# cd /abc ①
# python mdconv.py Handbook
```

① Please replace with your own path.

## Windows 10 21H2 Instructions

>**If the required files cannot be found online, please click "releases" on the page to download them.**

Tested with Python 3.12.3, pip 24.1.1, mistune 3.0.2, weasyprint 61.2, and gtk3-runtime 3.24.31.

### Directory Structure

```
C:\Users\ykla\Desktop\h\
├── build/
├── end.html
├── Handbook/
├── mdconv.py
└── start.html
```

### Installation Method

- **Install Python3 and pip3** Go to <https://www.python.org/downloads/>, click "Download Python 3.xx.x" to download. **Be sure to check `Add Python 3.x to PATH` during installation**. Pip will be installed automatically by default.
- **Install gtk3-runtime** Go to <https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases> and download "gtk3-runtime-3.24.31-2022-01-04-ts-win64.exe".
> gtk3-runtime is a runtime dependency for weasyprint on Windows and must be installed.
- **Install mistune and weasyprint**

>```
>C:\Windows\system32>pip install mistune weasyprint
>```

### Usage

```
C:\Windows\system32>cd C:\Users\ykla\Desktop\h ①
C:\Users\ykla\Desktop\h>python mdconv.py Handbook
```

① I placed it in the "h" folder on the user "ykla" desktop and put the GitBook project into the `h` folder.

>**Note**
>
>If you are unsure about the username, you can open Task Manager by pressing the `ctrl` `alt` `del` keys simultaneously, and then click "Users" to see it. If the account name is in Chinese, the consequences are unknown as it has not been tested.

## Linux

Due to the variety of Linux distributions and their different versions, even on the most common Ubuntu, installing the weasyprint module is very complicated. Therefore, this part awaits contributions from those who are willing. PRs are welcome.

## MacOS

This part awaits contributions from those who are willing. PRs are welcome.
