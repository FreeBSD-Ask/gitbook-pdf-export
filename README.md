# GitBook PDF/EPUB 导出工具（GitBook PDF/EPUB Export Tool）

作者为：[safreya](https://github.com/safreya)

GitBook 通用 PDF/EPUB/Word 导出工具。支持代码高亮、LaTeX 公式、PDF 书签与目录页。

**本项目基于 Python 3、mistune、EbookLib 及 WeasyPrint。CSS 样式模仿 GitBook PDF，并按 FreeBSD 中文社区文档站的 VitePress 主题调整了配色。**

## 预编译二进制

每个版本在 [Releases](https://github.com/FreeBSD-Ask/gitbook-pdf-export/releases) 提供各平台单文件二进制：

| 文件 | 平台 |
|:---|:---|
| `mdconv-ubuntu-x64` | Linux x86_64 |
| `mdconv-ubuntu-arm64` | Linux arm64 |
| `mdconv-windows-x64.exe` | Windows x64 |
| `mdconv-windows-arm64.exe` | Windows arm64 |
| `mdconv-macos-arm64` | macOS（Apple Silicon）|
| `mdconv-freebsd.tar.gz` | FreeBSD amd64，在 15.1 的 ZFS 根分区镜像上构建 |

二进制的发布门槛：每个平台都会在自己的 runner 上实际运行产物（`-h` 加一次真实导出，PDF 断言 `%PDF-2.0`），**任一平台失败则整批不发布**。

使用要点：

- 把 `start.html`、`highlight.css` 与 `fonts/` 与可执行文件放在同一目录（与仓库布局一致），否则找不到样式与字体
- WeasyPrint 需要系统 pango/gdk-pixbuf：Windows x64 需安装 [GTK3 Runtime](https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases)，Linux 装 `libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0`，macOS 用 `brew install pango gdk-pixbuf libffi` 并设置 `DYLD_FALLBACK_LIBRARY_PATH=$(brew --prefix)/lib`
- Windows arm64 目前没有对应的 GTK 构建，该平台产物可完成 Markdown→HTML、EPUB 与 DOCX 导出，PDF 渲染未验证

## 文件说明

|文件/目录|说明|
|:---:|:---|
|`mdconv.py`|主程序，不可删除|
|`start.html`|主 CSS 配置与 HTML 模板，不可删除|
|`highlight.css`|代码高亮配色（BSD 命令自定义高亮），不可删除|
|`fonts/`|霞鹜文楷 GB 版屏幕阅读版与等宽屏幕版，不可删除|
|`tests/`|回归测试、PDF/A 样本构建与 veraPDF 校验脚本|
|`build/`|输出目录，默认不存在，会自动生成；其中的 `pdf.html` 是 PDF 排版专用 HTML|

## 从源码使用

```text
python mdconv.py <docdir> [选项]
```

`docdir` 是文档根目录，需含 `SUMMARY.md`（GitBook 目录文件）。

### Linux

```sh
sudo apt install libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0
pip install -r requirements.txt
python mdconv.py Handbook
```

生成 PDF 中的公式需要 xelatex（可选）：`sudo apt install texlive-xetex texlive-lang-chinese`。

### FreeBSD 15.1

FreeBSD 15.1 的 pkg 仓库只为默认的 Python 3.12 构建第三方端口——源里有 `python315` 解释器，但没有 `py315-weasyprint`、`py315-pyinstaller` 等包，因此依赖装 py312 系列：

```sh
pkg install py312-pip py312-mistune py312-pygments py312-beautifulsoup4 \
            py312-weasyprint py312-pillow py312-python-docx
pip install --break-system-packages EbookLib
cd /gitbook-pdf-export-main ①
python3.12 mdconv.py Handbook
```

① 请换成你自己的路径。ZFS 根分区上无需任何额外配置。

### Windows 11

1. 安装 Python 3 并勾选 **Add Python to PATH**
2. 安装 [GTK3 Runtime](https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases)（WeasyPrint 的运行依赖，必须安装）
3. 安装 Python 依赖并运行：

```batch
C:\Windows\system32>pip install -r requirements.txt
C:\Windows\system32>cd C:\Users\ykla\Desktop\gitbook-pdf-export-main
C:\Users\ykla\Desktop\gitbook-pdf-export-main>python mdconv.py Handbook
```

目录结构约定：

```batch
C:\Users\ykla\Desktop\gitbook-pdf-export-main\
├── Handbook\
├── mdconv.py
├── start.html
├── highlight.css
└── fonts\
```

### macOS

```sh
brew install pango gdk-pixbuf libffi
export DYLD_FALLBACK_LIBRARY_PATH=$(brew --prefix)/lib
pip install -r requirements.txt
python mdconv.py Handbook
```

## 命令行参数

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

## 目录、页码与书签

- PDF 在封面之后生成目录页：条目取自正文标题，点线引导到行尾，页码由 CSS `target-counter` 在排版阶段计算，与页脚页码同源，因此永远不会与正文脱节
- 封面与目录本身不计入页序：正文第一章固定是第 1 页，目录跨多少页都不影响
- 源目录文件（`mu-lu.md`、`SUMMARY.md`）不再整篇排版成页，避免与生成的目录重复
- PDF 侧边栏书签按 `--bookmark-depth` 生成（SUMMARY 的分组标题始终作为章级书签）
- EPUB 由阅读器目录（`nav`）导航；Word 插入 TOC 域，打开文档后按 F9 更新

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

渲染 PDF 时，`start.html` 里的字体与高亮样式路径会被改写为绝对 URL（`file://`），因此 `-o` 指向仓库之外的目录时依然使用内置字体，不会静默回退到系统字体。

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

## CI 与发布

- `tests.yml`：21 项回归测试 + 构建最小样本并跑 veraPDF（PDF/A-4）
- `build-binaries.yml`：Ubuntu x64/arm64、Windows x64/arm64、macOS arm64 上用 PyInstaller 打包，FreeBSD 在 15.1 的 ZFS 镜像内构建；OpenBSD/NetBSD 做冒烟测试（缺预编译依赖时仅作参考，不阻塞发布）
- 每个平台构建后都会在本机运行产物：`-h` 加一次真实导出，PDF 断言 `%PDF-2.0`、EPUB/DOCX 断言 zip 容器；没有 GTK 的平台只验证 CLI 与 HTML
- 推送 `[0-9]*` 形式的 tag 会触发构建并自动把产物发布到对应 Release；任一平台构建或冒烟失败则不发布
