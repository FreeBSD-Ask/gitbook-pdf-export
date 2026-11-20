# GitBook PDF/EPUB 导出工具（GitBook PDF/EPUB Export Tool）

作者为：[safreya](https://github.com/safreya)

GitBook 通用 PDF/EPUB 导出工具。支持代码高亮。

**本项目基于 Python3、mistune、EbookLib 及 weasyprint。CSS 样式模仿 GitBook PDF**

## 文件说明

|文件/目录|说明|
|:---:|:---:|
|build|用于生成 PDF 的路径，默认不存在，会自动生成|
|mdconv.py|主程序，不可删除|
|start.html|主 CSS 配置文件，不可删除|

其他未说明文件均可删除。

## FreeBSD 14.3 RELEASE 使用说明

在 lang/python3.15、py315-pip、py315-mistune、py315-pygments 下测试通过。

### 目录结构：

我在 `/` 目录下创建了 `gitbook-pdf-export-main` 目录，并将 gitbook 项目目录整体放入了目录 `h` 中。

```sh
/gitbook-pdf-export-main/ ①
├── Handbook/ 
├── mdconv.py
└── start.html
```

### 安装及使用方法

```sh
# pkg install python3.15 py315-pip py315-mistune py315-pygments py315-beautifulsoup py315-weasyprint py315-pillow
$ pip install EbookLib
$ cd /gitbook-pdf-export-main ①
$ python mdconv.py Handbook
```

① 请换成你的自己的路径


## Windows 11 24H2 使用说明

>**如果所需文中所需文件在网络上找不到，请点击页面的“releases”，进行下载。**


### 目录结构

```batch
C:\Users\ykla\Desktop\gitbook-pdf-export-main\
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
>C:\Windows\system32>pip install mistune weasyprint pygments EbookLib beautifulsoup4
>```

### 使用方法

```batch
C:\Windows\system32>cd C:\Users\ykla\Desktop\gitbook-pdf-export-main ①
C:\Users\ykla\Desktop\gitbook-pdf-export-main>python mdconv.py Handbook
```

① 我将其放在了用户 “ykla” 桌面的“gitbook-pdf-export-main”文件夹中，并将 gitbook 项目放入了文件夹 `gitbook-pdf-export-main` 中。

>**注意**
>
>如果不知道用户名是什么，可以打开同时按快捷键 `ctrl` + `alt` + `del` 来打开任务管理器，点击“用户”，就能看到了，如果账户名是中文，后果将不可知，因为未经测试。


## 命令行参数

```text
python mdconv.py <docdir> [选项]
```

|参数|说明|
|:---|:---|
|`docdir`|文档根目录（含 SUMMARY.md）|
|`-o, --output`|输出目录，默认 `build`|
|`--no-pdf`|跳过 PDF 生成|
|`--no-epub`|跳过 EPUB 生成|
|`--no-docx`|跳过 Word 文档生成|
|`--no-formula`|跳过 LaTeX 公式渲染|
|`-j, --workers`|并行进程数，默认 CPU 核数（上限 16）|
|`--title`|书籍标题，默认读取 start.html 的 `<title>`|
|`--author`|作者，默认读取 start.html 的 `meta author`|
|`--language`|书籍语言，默认 `zh-CN`|
|`--bookmark-depth`|PDF 书签与目录的标题深度，按 Markdown 标题级别计，默认 `2`（即到二级标题 `##`，取值 1–6）|

PDF 在封面之后生成一页由正文标题构建的目录（点线引导 + 页码），页码由 CSS `target-counter` 在排版时计算，与页脚页码同源；封面与目录本身不计入页序，正文第一章从第 1 页开始。源目录文件（`mu-lu.md`、`SUMMARY.md`）不再排版成页。EPUB 由阅读器目录（`nav`）导航，Word 插入 TOC 域（打开文档后按 F9 更新）。

## PDF 标准与校验

PDF 基于 **PDF 2.0（ISO 32000-2）** 输出，声明为 **PDF/A-4（ISO 19005-4:2020）** 基础级：XMP 含 `pdfaid:part="4"` 与 `pdfaid:rev="2020"`，基础级不带 `pdfaid:conformance`（该属性只属于 4e/4f）。WeasyPrint 70 与标准之间还有两处差异，mdconv 同样在渲染阶段补齐：部分 SVG（如 shields.io 徽章）会让上游写出 NaN 坐标，序列化为未定义操作符 `nan`（6.2.2 禁止），现折算为 0；位图的 `Interpolate` 上游默认写 true（6.2.7.1 要求 false），现统一关闭——该标志只影响阅读器缩放时的平滑方式，不改动图像像素数据。

CI 除单元测试外，还会构建最小样本并用 [veraPDF](https://verapdf.org) 实测校验（flavour 4）：

```sh
python tests/build_pdfa_sample.py pdfa-sample
python tests/verapdf_cli.py pdfa-sample/final.pdf
```

`tests/verapdf_cli.py` 首次运行会从 software.verapdf.org 下载固定版本（1.30.4）的安装包，提取 CLI 后缓存在 `VERAPDF_CLI_CACHE`（默认系统临时目录）中复用；校验不通过时以非零码退出。

## 字体说明

本项目默认全量嵌入**霞鹜文楷 GB 版屏幕阅读版**（正文，`fonts/LXGWWenKaiGBScreen.ttf`）与**霞鹜文楷 GB 版等宽屏幕版**（代码块，含英文，`fonts/LXGWWenKaiMonoGBScreen.ttf`）。GB 版采用国标字形，与 [FreeBSD 中文社区文档站](https://docs.bsdcn.org) 的 VitePress 字体一致。字体采用 SIL OFL 1.1 授权，可自由嵌入与分发。

PDF 通过 WeasyPrint 子集化嵌入（不显著增大体积）；EPUB 将 `fonts/` 下的字体文件全部打包进书籍；Word 文档声明 `LXGW WenKai GB Screen` / `LXGW WenKai Mono GB Screen` 字体名（未安装该字体的机器会回退到系统字体）。

如需在系统层面安装（非必需，仅方便本地预览）：

```sh
# Ubuntu / Debian（deb 包，仅提供非 GB 字形版）
sudo apt install fonts-lxgw-wenkai fonts-lxgw-wenkai-mono

# macOS
brew install --cask font-lxgw-wenkai

# Arch Linux (AUR)
yay -S ttf-lxgw-wenkai-screen
```

最新 GB 版字体可从 [霞鹜文楷屏幕阅读版 Releases](https://github.com/lxgw/LxgwWenKai-Screen/releases) 下载 `LXGWWenKaiGBScreen.ttf` 与 `LXGWWenKaiMonoGBScreen.ttf`，放入 `fonts/` 目录即可（`fonts/` 内的所有 `.ttf`/`.otf` 都会被 EPUB 打包）。

## Linux/GitHub Action
 
参见 https://github.com/ykla/FreeBSD-Ask/actions

## MacOS

待有缘人对该部分内容进行补充。欢迎 PR。
