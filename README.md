# GitBook PDF 导出工具（GitBook PDF Export Tool）

作者为：[safreya](https://github.com/safreya)

gitbook 通用 PDF 导出工具。支持代码高亮。

**本项目基于 Python3、mistune 及 weasyprint**

## 文件说明

|文件/目录|说明|
|:---:|:---:|
|build|用于生成 PDF 的路径，默认不存在，会自动生成|
|mdconv.py|主程序，不可删除|
|start.html|主 CSS 配置文件，不可删除|

其他未说明文件均可删除。

## FreeBSD 14.1 RELEASE 使用说明

在 lang/python311、py311-pip、py311-weasyprint、py311-mistune py311-pygments 下测试通过。

### 目录结构：

我在 `/` 目录下创建了 `abc` 目录，并将 gitbook 项目目录整体放入了目录 `h` 中。

```sh
/abc/ ①
├── Handbook/ 
├── mdconv.py
└── start.html
```

### 安装及使用方法

```sh
# pkg install python311 py311-pip py311-weasyprint py311-mistune py311-pygments
# cd /abc ①
# python mdconv.py Handbook
```

① 请换成你的自己的路径


## Windows 11 24H2 使用说明

>**如果所需文中所需文件在网络上找不到，请点击页面的“releases”，进行下载。**


在 Python 3.12.3、pip 24.1.1、mistune 3.0.2、weasyprint 61.2、gtk3-runtime 3.24.3、pygments 2.17.2 下测试通过。


### 目录结构

```batch
C:\Users\ykla\Desktop\h\
├── Handbook/ 
├── mdconv.py
└── start.html
```

### 安装方法

- **安装 Python3 和 pip3** 进入 <https://www.python.org/downloads/>，点击“Download Python 3.xx.x”即可下载。**请务必在安装时勾选 `Add Python 3.x to PATH`**。在默认情况下，会自动安装 pip。
- **安装 gtk3-runtime** 进入 <https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases> 下载安装“gtk3-runtime-3.24.31-2022-01-04-ts-win64.exe“即可。
>gtk3-runtime 是 weasyprint 在 Windows 上的运行依赖，必须安装。
- **安装 mistune 和 weasyprint**

>```batch
>C:\Windows\system32>pip install mistune weasyprint  pygments
>```

### 使用方法

```batch
C:\Windows\system32>cd C:\Users\ykla\Desktop\h ①
C:\Users\ykla\Desktop\h>python mdconv.py Handbook
```

① 我将其放在了用户 “ykla” 桌面的“h”文件夹中，并将 gitbook 项目放入了文件夹 `h` 中。

>**注意**
>
>如果不知道用户名是什么，可以打开同时按快捷键 `ctrl` `alt` `del` 来打开任务管理器，点击“用户”，就能看到了，如果账户名是中文，后果将不可知，因为未经测试。


## Linux/GitHub Action
 
参见 https://github.com/ykla/FreeBSD-Ask/actions

## MacOS

待有缘人对该部分内容进行补充。欢迎 PR。
