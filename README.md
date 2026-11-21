# GitBook PDF/EPUB 导出工具

作者：[safreya](https://github.com/safreya)

把 GitBook 风格的 Markdown 文档导出为 **PDF、EPUB、Word**。一条命令、一个源，三种格式保持一致。

支持代码高亮、LaTeX 公式、目录页与书签、自动图号、脚注，PDF 默认符合 PDF/A-4 归档标准。

## 快速开始

```sh
pip install -r requirements.txt
python mdconv.py 文档目录
```

`文档目录` 需包含 `SUMMARY.md`。结果在 `build/`：

| 文件 | 内容 |
|:---|:---|
| `final.pdf` | PDF/A-4，带目录页与侧边栏书签 |
| `final.epub` | EPUB 3，阅读器目录导航 |
| `final.docx` | Word，含目录域（打开后按 F9 更新） |
| `final-ua.pdf` | 无障碍版，仅加 `--pdf-ua` 时生成 |

运行时需要系统库：Linux 装 `libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0`，Windows 装 [GTK3 Runtime](https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases)。FreeBSD 15.1 的第三方包只有 py312 系列：`pkg install py312-weasyprint py312-mistune py312-pygments py312-beautifulsoup4 py312-python-docx py312-pillow`，再 `pip install --break-system-packages EbookLib`。

## 预编译二进制

[Releases](https://github.com/FreeBSD-Ask/gitbook-pdf-export/releases) 提供 Ubuntu（x64/arm64）、Windows（x64/arm64）与 FreeBSD 单文件二进制，另附 `SHA-256SUMS` 与 `BUILD-INFO.txt`。

下载后把 `start.html`、`highlight.css`、`fonts/` 放在可执行文件旁，即可运行：

```sh
./mdconv-ubuntu-x64 文档目录
sha256sum -c SHA-256SUMS   # 校验下载
```

Windows arm64 没有可用的 GTK，只能导出 HTML、EPUB 与 Word。

## 命令行参数

| 参数 | 说明 |
|:---|:---|
| `docdir` | 文档根目录（含 `SUMMARY.md`） |
| `-o, --output` | 输出目录，默认 `build` |
| `--no-pdf` / `--no-epub` / `--no-docx` | 跳过对应格式 |
| `--pdf-ua` | 额外生成无障碍 PDF（PDF/UA-1），默认关闭 |
| `--bookmark-depth` | PDF 书签与目录深度，按 Markdown 标题级别计，默认 2（到 `##`） |
| `--title` / `--author` / `--language` | 元数据，默认从 `start.html` 读取，语言默认 `zh-CN` |
| `--no-formula` | 跳过公式渲染 |
| `--formula-engine` | 公式后端：`auto`（默认）、`latex`、`mathjax` |
| `-j, --workers` | 并行进程数，默认 CPU 核数（上限 16） |

## 排版说明

- **目录与页码**：PDF 封面后生成目录页，页码与正文页脚同源；封面和目录不计入页序，正文从第 1 页开始。源目录文件（如 `mu-lu.md`）不会重复排版。
- **书签**：深度由 `--bookmark-depth` 控制，默认到二级标题。
- **图号与脚注**：图片自动编号为 `图 N：alt`，`[^1]` 脚注在三种格式中都会呈现。
- **中文排版**：严格避头尾（`line-break: strict`）、中西文自动间距、词组级断行。
- **字体**：默认全量嵌入霞鹜文楷 GB 版屏幕阅读版（正文与代码，SIL OFL 1.1）。Word 使用字体名，未安装时回退系统字体。

## 公式（可选）

默认 `--formula-engine auto`：有 LaTeX 就用 LaTeX，没有 LaTeX 时不带中文的公式改用 MathJax，含中文的公式保留原文。

- **LaTeX**（推荐，保真度最高）：安装 xelatex 即可，Ubuntu 为 `texlive-xetex texlive-lang-chinese`。
- **MathJax + Bun**（无需 TeX）：

  ```sh
  cd tools/mathjax && bun install
  ```

  需自行安装 [Bun](https://bun.sh)。预编译二进制不含此目录，仍用系统 LaTeX。含中文的公式只能由 LaTeX 渲染。

## 开发与发布

```sh
pip install -r requirements-dev.txt
python -m unittest discover -s tests
```

CI 会跑单元测试，并用 veraPDF 校验 PDF/A-4 与 PDF/UA-1、EPUBCheck 校验 EPUB。推送 `[0-9]*` 形式的 tag 后，所有平台构建并实测通过才会自动发布。更详细的设计说明见 [`docs/改进建议书.md`](docs/改进建议书.md)。
