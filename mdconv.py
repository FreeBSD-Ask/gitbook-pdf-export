#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import shutil
import re
import argparse
import hashlib
from urllib.parse import urlparse, unquote
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing
from multiprocessing import Manager

# WeasyPrint 在导入阶段就会 dlopen 系统的 pango/cairo；只做 HTML/EPUB/Word
# 或仅运行 -h 的环境（例如没有 GTK 的 Windows arm64）不需要它，故延迟导入

import mistune
from pygments import highlight
from pygments.lexers import get_lexer_by_name
from pygments.lexers.shell import BashLexer
from pygments.formatters import html as pygments_html_formatter
from pygments.token import Generic, Name, Text, Whitespace
from pygments.lexer import bygroups

from ebooklib import epub
from bs4 import BeautifulSoup, NavigableString, Tag

# 新增 imports
import urllib.request
import mimetypes
import io
import subprocess
import tempfile
import uuid
from html import escape as html_escape, unescape as html_unescape
from concurrent.futures import ThreadPoolExecutor

# 常量定义
BUILD_DIR = 'build'
SUMMARY_FILE = 'SUMMARY.md'
DEFAULT_TOC_FILE = 'mu-lu.md'
START_HTML = 'start.html'
FINAL_HTML = 'final.html'
# 供 PDF 排版使用的 HTML（含封面页与目录页，EPUB/Word 不读它）
PDF_HTML = 'pdf.html'
FINAL_PDF = 'final.pdf'
FINAL_EPUB = 'final.epub'
FINAL_DOCX = 'final.docx'
CSS_DIR = 'css'

# PDF 书签与目录的默认深度（Markdown 标题级别：1 = 章标题，2 = 节标题）
DEFAULT_BOOKMARK_DEPTH = 2
TOC_PAGE_TITLE = '目录'

# 公式 SVG 的持久缓存目录（独立于 build，重复构建无需重新渲染）
# 优先读取环境变量（多进程 worker 通过它继承主进程的设置）
FORMULA_CACHE_DIR = os.environ.get('MDCONV_FORMULA_CACHE') or os.path.join(
    os.path.expanduser('~'), '.cache', 'mdconv', 'formulas'
)

# 全局变量，会在每个子进程中重新初始化
IMAGES_DIR = None

LATEX_ENGINE = None

# BSD（FreeBSD/OpenBSD/NetBSD 等）专有及常用命令词表，
# 用于 shell 代码块高亮：行首 # 或 $ 提示符后接这些命令词时，命令名高亮为命令色
BSD_COMMANDS = frozenset({
    # 包管理与系统更新
    'pkg', 'pkg-install', 'pkg-search', 'pkg-delete', 'pkg-remove', 'pkg-info',
    'pkg-update', 'pkg-upgrade', 'pkg-clean', 'pkg-which', 'pkg-query',
    'pkg-check', 'pkg-lock', 'pkg-repo', 'pkg-version', 'pkg-audit',
    'portsnap', 'freebsd-update', 'portmaster', 'portupgrade',
    # 权限与用户
    'doas', 'sudo', 'su', 'pw', 'chpass', 'adduser', 'deluser', 'groups',
    # 服务与系统控制
    'service', 'sysrc', 'sysctl', 'kldload', 'kldunload', 'kldstat', 'rcorder',
    'dmesg', 'kenv', 'jail', 'jls', 'jexec', 'jailhouse', 'rctl', 'procctl',
    'capsicumctl', 'setfib', 'chroot', 'watch', 'dump', 'restore', 'dumpfs',
    'snapinfo', 'camcontrol', 'atacontrol', 'smartctl', 'diskinfo',
    # 文件系统与存储
    'zfs', 'zpool', 'zdb', 'zinject', 'ztest', 'arcstat', 'arc_summary',
    'gpart', 'glabel', 'gmirror', 'gstripe', 'gconcat', 'graid', 'geli',
    'gvirstor', 'mdconfig', 'mdmfs', 'newfs', 'newfs_msdos', 'tunefs',
    'growfs', 'fsck', 'fsck_ffs', 'mount', 'umount', 'swapctl', 'swapon',
    'swapoff', 'quotacheck', 'repquota', 'edquota', 'rwhod', 'nfsstat',
    'nfsiod', 'showmount', 'mountd', 'autounmountd', 'automount',
    # 网络与防火墙
    'ifconfig', 'netstat', 'route', 'dhclient', 'resolvconf', 'wpa_cli',
    'wpa_supplicant', 'ppp', 'pfctl', 'pflogd', 'ipfw', 'ipf', 'tcpdump',
    'ping', 'ping6', 'traceroute', 'traceroute6', 'mtr', 'dig', 'host',
    'nslookup', 'ssh', 'scp', 'sftp', 'rsync', 'curl', 'wget', 'fetch',
    'sockstat', 'lsof', 'ss', 'arp', 'ndp', 'mcast', 'tcpdrop',
    # 虚拟化与容器
    'bhyve', 'bhyvectl', 'bhyveload', 'vm', 'vm-bhyve', 'cbmd', 'qemu-system-x86_64',
    'podman', 'docker', 'pot', 'iocage', 'ezjail-admin', 'qjail',
    # 引导与基础
    'gptboot', 'efibootmgr', 'bootcontrol', 'boot0cfg', 'fdisk', 'bsdinstall',
    'bsdconfig', 'nextboot', 'loadfont', 'kbdmap', 'vidfont',
    # 常用 Unix 工具（提示符场景高频）
    'git', 'make', 'cmake', 'meson', 'ninja', 'clang', 'cc', 'gcc', 'gdb', 'lldb',
    'python', 'python3', 'pip', 'perl', 'awk', 'sed', 'grep', 'rg', 'find', 'tar',
    'cp', 'mv', 'rm', 'ln', 'mkdir', 'rmdir', 'chmod', 'chown', 'chflags',
    'ls', 'cat', 'head', 'tail', 'less', 'more', 'nano', 'vi', 'vim', 'ee',
    'ps', 'top', 'htop', 'kill', 'killall', 'pkill', 'pgrep', 'nice', 'time',
    'dd', 'tee', 'xargs', 'sort', 'uniq', 'wc', 'diff', 'patch', 'du', 'df',
    'stat', 'readlink', 'realpath', 'basename', 'dirname', 'env', 'export',
    'history', 'tmux', 'screen', 'crontab', 'at', 'logger', 'news', 'man',
    'apropos', 'which', 'whereis', 'whois', 'unzip', 'zip', 'gzip', 'bzip2',
    'xz', 'zstd', 'sha256', 'sha512', 'md5', 'openssl', 'ssh-keygen',
    'systemd-analyze', 'apt', 'apt-get', 'dpkg', 'dnf', 'brew',
})


def _bsd_command_token(lexer, match, ctx):
    """提示符后的首词：命中 BSD 命令词表则按命令名高亮，否则按普通文本处理"""
    word = match.group(0)
    base = word.rstrip('/:').rsplit('/', 1)[-1].lower()
    if base in BSD_COMMANDS:
        yield match.start(), Name.Function, word
    else:
        yield match.start(), Text, word


class BsdShellLexer(BashLexer):
    """面向 BSD 文档的 shell 词法分析器

    在 Bash 词法基础上增加提示符规则：行首 "# " 或 "$ " 后接空格与命令词，
    且该词命中 BSD_COMMANDS 词表时，将命令名高亮为命令色；
    "#" 后接非命令词时仍按 Bash 注释处理。
    """
    name = 'BSD Shell'
    aliases = ['bsd-shell', 'freebsd-shell', 'freebsd']
    filenames = []

    tokens = {
        'root': [
            # 行首 #/$ 提示符 + 空格 + 首个命令词
            (r'(?m)^([#$])([ \t]+)([^\s;&|]+)',
             bygroups(Generic.Prompt, Whitespace, _bsd_command_token)),
            # 行首 #/$ 提示符 + 空格（后续内容按 Bash 规则处理）
            (r'(?m)^([#$])([ \t]+)', bygroups(Generic.Prompt, Whitespace)),
        ] + BashLexer.tokens['root'],
    }


def find_latex_engine():
    """查找可用的 LaTeX 引擎（优先 xelatex > lualatex > pdflatex）"""
    global LATEX_ENGINE
    if LATEX_ENGINE is not None:
        return LATEX_ENGINE if LATEX_ENGINE else None
    # 子进程通过环境变量继承主进程的检测结果，避免每个 worker 重复检测
    env_engine = os.environ.get('MDCONV_LATEX_ENGINE')
    if env_engine is not None:
        LATEX_ENGINE = env_engine
        return env_engine if env_engine else None
    creation_flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    for engine in ['xelatex', 'lualatex', 'pdflatex']:
        try:
            result = subprocess.run(
                [engine, '--version'],
                capture_output=True, timeout=10,
                creationflags=creation_flags
            )
            if result.returncode == 0:
                LATEX_ENGINE = engine
                os.environ['MDCONV_LATEX_ENGINE'] = engine
                return engine
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            continue
    LATEX_ENGINE = ''
    os.environ['MDCONV_LATEX_ENGINE'] = ''
    return None


def find_dvisvgm():
    """查找 dvisvgm 工具"""
    # 子进程通过环境变量继承主进程的检测结果
    env_dvisvgm = os.environ.get('MDCONV_DVISVGM')
    if env_dvisvgm is not None:
        return env_dvisvgm == '1'
    creation_flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    try:
        result = subprocess.run(
            ['dvisvgm', '--version'],
            capture_output=True, timeout=10,
            creationflags=creation_flags
        )
        if result.returncode == 0:
            os.environ['MDCONV_DVISVGM'] = '1'
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    os.environ['MDCONV_DVISVGM'] = '0'
    return False


def render_latex_to_svg(latex_code, output_path):
    """将 LaTeX 公式渲染为 SVG 图片（通过 xelatex → XDV → dvisvgm）

    通过先写临时文件再原子替换（os.replace），保证多进程并发渲染同一公式时
    不会产生读到半成品的竞态问题。
    """
    engine = find_latex_engine()
    if engine is None:
        raise RuntimeError("未找到 LaTeX 引擎，请安装 MiKTeX 或 TeX Live")

    if not find_dvisvgm():
        raise RuntimeError("未找到 dvisvgm，请确认 TeX 发行版完整安装")

    has_cjk = any('\u4e00' <= c <= '\u9fff' for c in latex_code)
    if has_cjk and engine == 'pdflatex':
        raise RuntimeError("公式包含中文字符，但 xelatex/lualatex 不可用")

    # 仅在公式包含中文时加载 ctex，缩短无中文公式的编译时间
    packages = r'\usepackage{amsmath,amssymb,amsfonts}' + '\n'
    if engine in ('xelatex', 'lualatex'):
        if has_cjk:
            packages += r'\usepackage{ctex}' + '\n'
        template = (
            r'\documentclass[12pt]{article}' '\n'
            + packages +
            r'\begin{document}' '\n'
            r'\thispagestyle{empty}' '\n'
            r'\[' '\n'
            '%s' '\n'
            r'\]' '\n'
            r'\end{document}'
        )
    else:
        template = (
            r'\documentclass[12pt]{article}' '\n'
            + packages +
            r'\usepackage[T1]{fontenc}' '\n'
            r'\usepackage[utf8]{inputenc}' '\n'
            r'\begin{document}' '\n'
            r'\thispagestyle{empty}' '\n'
            r'\[' '\n'
            '%s' '\n'
            r'\]' '\n'
            r'\end{document}'
        )

    creation_flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    # dvisvgm 先输出到临时文件，成功后原子替换，避免并发读到半成品
    tmp_output = f'{output_path}.tmp{os.getpid()}'
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            tex_path = os.path.join(tmpdir, 'formula.tex')

            with open(tex_path, 'w', encoding='utf-8') as f:
                f.write(template % latex_code)

            if engine in ('xelatex', 'lualatex'):
                # xelatex/lualatex: 编译为 XDV（不生成 PDF），再由 dvisvgm 转 SVG
                xdv_path = os.path.join(tmpdir, 'formula.xdv')
                result = subprocess.run(
                    [engine, '-no-pdf', '-interaction=nonstopmode',
                     '-output-directory', tmpdir, tex_path],
                    capture_output=True, timeout=120,
                    cwd=tmpdir,
                    creationflags=creation_flags
                )
                if not os.path.exists(xdv_path):
                    stdout = result.stdout.decode('utf-8', errors='replace')
                    raise RuntimeError(f"{engine} 编译失败: {stdout[:500]}")

                svg_result = subprocess.run(
                    ['dvisvgm', '--no-fonts', '--exact', '-o', tmp_output, xdv_path],
                    capture_output=True, timeout=60,
                    creationflags=creation_flags
                )
                if not os.path.exists(tmp_output):
                    stderr = svg_result.stderr.decode('utf-8', errors='replace')
                    raise RuntimeError(f"dvisvgm 转换失败: {stderr[:500]}")
            else:
                # pdflatex: 先编译为 DVI，再由 dvisvgm 转 SVG
                dvi_path = os.path.join(tmpdir, 'formula.dvi')
                result = subprocess.run(
                    ['latex', '-interaction=nonstopmode',
                     '-output-directory', tmpdir, tex_path],
                    capture_output=True, timeout=120,
                    cwd=tmpdir,
                    creationflags=creation_flags
                )
                if not os.path.exists(dvi_path):
                    stdout = result.stdout.decode('utf-8', errors='replace')
                    raise RuntimeError(f"latex 编译失败: {stdout[:500]}")

                svg_result = subprocess.run(
                    ['dvisvgm', '--no-fonts', '--exact', '-o', tmp_output, dvi_path],
                    capture_output=True, timeout=60,
                    creationflags=creation_flags
                )
                if not os.path.exists(tmp_output):
                    stderr = svg_result.stderr.decode('utf-8', errors='replace')
                    raise RuntimeError(f"dvisvgm 转换失败: {stderr[:500]}")

        os.replace(tmp_output, output_path)
    finally:
        if os.path.exists(tmp_output):
            try:
                os.remove(tmp_output)
            except OSError:
                pass


def ensure_formula_svg(formula, images_dir):
    """渲染单个公式为 SVG（带持久缓存），成功返回文件名，失败返回 None

    缓存位于 FORMULA_CACHE_DIR（独立于 build 目录），重复构建无需重新渲染。
    """
    h = hashlib.md5(formula.encode('utf-8')).hexdigest()[:12]
    svg_name = f'formula_{h}.svg'
    svg_path = os.path.join(images_dir, svg_name)

    if os.path.exists(svg_path):
        return svg_name

    # 命中持久缓存则直接复用
    os.makedirs(FORMULA_CACHE_DIR, exist_ok=True)
    cached_path = os.path.join(FORMULA_CACHE_DIR, svg_name)
    if os.path.exists(cached_path):
        try:
            shutil.copy(cached_path, svg_path)
            return svg_name
        except OSError:
            pass

    try:
        render_latex_to_svg(formula, svg_path)
        try:
            shutil.copy(svg_path, cached_path)
        except OSError:
            pass
        return svg_name
    except Exception as e:
        print(f"  公式渲染失败: {formula[:50]}... : {e}")
        return None


def preprocess_formulas(md_text, images_dir):
    """将 Markdown 中的 LaTeX 公式替换为 SVG 图片引用

    单个 Markdown 文件内的全部公式并发渲染（LaTeX 编译为子进程，线程池即可加速）。
    """
    if find_latex_engine() is None:
        return md_text

    code_blocks = []

    def save_code_block(match):
        code_blocks.append(match.group(0))
        return f'\x00CODEBLOCK{len(code_blocks) - 1}\x00'

    md_text = re.sub(r'```[\s\S]*?```', save_code_block, md_text)
    md_text = re.sub(r'`[^`]+`', save_code_block, md_text)

    # 先扫描收集全部唯一公式
    formulas = {}

    def collect_display(match):
        formula = match.group(1).strip()
        if formula:
            formulas.setdefault(formula, 'display')
        return match.group(0)

    def collect_inline(match):
        formula = match.group(1).strip()
        if formula and ('\\' in formula or '_' in formula or '^' in formula):
            formulas.setdefault(formula, 'inline')
        return match.group(0)

    md_text = re.sub(r'\$\$([\s\S]*?)\$\$', collect_display, md_text)
    md_text = re.sub(r'(?<!\$)\$(?!\$)([^\$\n]+?)\$(?!\$)', collect_inline, md_text)

    # 并发渲染（LaTeX 编译是子进程调用，线程池即可并行）
    if formulas:
        print(f"  开始渲染 {len(formulas)} 个公式（含缓存复用）...")
        with ThreadPoolExecutor(max_workers=min(4, len(formulas))) as executor:
            list(executor.map(
                lambda f: ensure_formula_svg(f, images_dir),
                formulas.keys()
            ))

    def replace_display(match):
        formula = match.group(1).strip()
        if not formula:
            return match.group(0)
        svg_name = ensure_formula_svg(formula, images_dir)
        if svg_name is None:
            return match.group(0)
        return f'\n<img src="images/{svg_name}" alt="formula" class="formula-display">\n'

    def replace_inline(match):
        formula = match.group(1).strip()
        if not formula:
            return match.group(0)
        if '\\' not in formula and '_' not in formula and '^' not in formula:
            return match.group(0)
        svg_name = ensure_formula_svg(formula, images_dir)
        if svg_name is None:
            return match.group(0)
        return f'<img src="images/{svg_name}" alt="formula" class="formula-inline">'

    md_text = re.sub(r'\$\$([\s\S]*?)\$\$', replace_display, md_text)
    md_text = re.sub(r'(?<!\$)\$(?!\$)([^\$\n]+?)\$(?!\$)', replace_inline, md_text)

    for i, code_block in enumerate(code_blocks):
        md_text = md_text.replace(f'\x00CODEBLOCK{i}\x00', code_block)

    return md_text


def prepare_build_dir(build_dir: str) -> None:
    """准备构建目录，清理旧文件"""
    if os.path.exists(build_dir):
        shutil.rmtree(build_dir)
    os.makedirs(build_dir, exist_ok=True)
    global IMAGES_DIR
    IMAGES_DIR = os.path.join(build_dir, 'images')
    os.makedirs(IMAGES_DIR, exist_ok=True)


def read_markdown_file(filename: str) -> str:
    """读取 Markdown 文件内容"""
    with open(filename, 'r', encoding='utf-8') as f:
        return f.read()


def copy_single_image(args):
    """复制单个图片 - 用于多进程处理"""
    src_path, dst_path = args
    try:
        shutil.copy(src_path, dst_path)
        return True, src_path
    except Exception as e:
        return False, f"{src_path}: {e}"


def _guess_ext_from_content_type(content_type: str):
    """从 Content-Type 推断文件扩展名（带点），若失败返回空字符串"""
    if not content_type:
        return ''
    ctype = content_type.split(';', 1)[0].strip().lower()
    # 使用 mimetypes.guess_extension，某些 image/jpeg 会返回 '.jpe'，还可接受
    ext = mimetypes.guess_extension(ctype)
    if ext:
        return ext
    # 简单映射常见类型作为后备
    mapping = {
        'image/jpeg': '.jpg',
        'image/jpg': '.jpg',
        'image/png': '.png',
        'image/gif': '.gif',
        'image/svg+xml': '.svg',
        'image/webp': '.webp',
    }
    return mapping.get(ctype, '')


def convert_local_paths_worker(args):
    """处理本地图片路径和在线链接的图片 - 多进程工作函数
    该函数会：
      - 将本地资源的 src 调整为 images/<name> 并返回复制任务（主进程负责实际复制）
      - 对于 http/https 或 // 的在线图片，直接在此 worker 中下载到 images_dir，并将 src 修改为 images/<name>
    args: (html_content, docdir, images_dir[, rootdir])
      - docdir 为当前 Markdown 文件所在目录；
      - rootdir 为文档根目录（可选，缺省为 docdir），用于将 .md 链接规范化为全书一致的锚点。
    返回：(html_content, copy_tasks)
    copy_tasks 中仅包含需要由主进程复制的本地文件对 (abs_path, dst_path)
    """
    html_content, docdir, images_dir, *rest = args
    rootdir = rest[0] if rest else docdir

    # 收集所有需要复制的图片任务（本地）
    copy_tasks = []

    def download_remote_image(url, dst_path):
        try:
            # 支持 protocol-relative URLs like //example.com/img.png
            if url.startswith('//'):
                url = 'https:' + url
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
                content_type = resp.getheader('Content-Type')
                # 若 dst_path 没有扩展名，则尝试从 content_type 推断扩展
                base, ext = os.path.splitext(dst_path)
                if not ext:
                    guessed = _guess_ext_from_content_type(content_type)
                    if guessed:
                        dst_path = base + guessed
                # 确保目录存在
                os.makedirs(os.path.dirname(dst_path), exist_ok=True)
                with open(dst_path, 'wb') as out_f:
                    out_f.write(data)
            return dst_path, None
        except Exception as e:
            return None, f"Download failed {url}: {e}"

    def process_src_match(match):
        original = match.group(0)  # e.g. src="..."/href="..."
        val = match.group(1)
        # 仅反转义 HTML 实体（&amp; 等），保留 percent-encoding：
        # unquote 后含中文的 URL 传给 urllib 会触发 UnicodeEncodeError
        html_val = html_unescape(val)
        parsed = urlparse(html_val)
        decoded = unquote(html_val)

        # 处理 src="..." 的情况（图片）
        if original.startswith('src="'):
            # protocol-relative URL 开头的情况
            if html_val.startswith('//') or parsed.scheme in ('http', 'https'):
                # 在线图片 -> 下载到 images_dir
                url = html_val if not html_val.startswith('//') else 'https:' + html_val
                # 构造文件名：使用 url 的 basename（若不合法则 md5），保留扩展（或根据 content-type 推断）
                path_part = unquote(urlparse(url).path or '')
                base_name = os.path.basename(path_part)
                name, ext = os.path.splitext(base_name)
                if not name:
                    name = hashlib.md5(url.encode('utf-8')).hexdigest()
                # 如果扩展名缺失，暂时用 ''，下载时根据响应 Content-Type 修正
                new_name = (hashlib.md5(url.encode('utf-8')).hexdigest() + ext) if not re.match(r'^[A-Za-z0-9_\-]+$', name) else (name + ext)
                dst = os.path.join(images_dir, new_name)
                # 如果文件已存在就不重复下载
                if not os.path.exists(dst):
                    downloaded_path, err = download_remote_image(url, dst)
                    if err:
                        # 下载失败，保持原始 URL（不替换），并打印错误
                        print(err)
                        return original
                    else:
                        # 如果下载函数根据 content-type 改了扩展名，调整 new_name
                        new_name = os.path.basename(downloaded_path)
                        return f'src="images/{new_name}"'
                else:
                    return f'src="images/{os.path.basename(dst)}"'

            # 本地资源（相对或绝对本地路径）
            if not parsed.scheme:
                # 跳过已存在于 images 目录的公式图片
                if decoded.startswith('images/'):
                    basename = os.path.basename(decoded)
                    if os.path.exists(os.path.join(images_dir, basename)):
                        return original

                abs_path = os.path.abspath(os.path.join(docdir, decoded))
                name, ext = os.path.splitext(os.path.basename(abs_path))
                if not re.match(r'^[A-Za-z0-9]+$', name):
                    name = hashlib.md5(name.encode('utf-8')).hexdigest()
                # 以源文件绝对路径的 md5 前缀命名，避免不同目录同名图片互相覆盖
                prefix = hashlib.md5(abs_path.encode('utf-8')).hexdigest()[:8]
                new_name = f"{prefix}_{name}{ext}"
                dst = os.path.join(images_dir, new_name)

                # 记录需要复制的任务（主进程会并行复制）
                copy_tasks.append((abs_path, dst))
                return f'src="images/{new_name}"'

        # 处理 href="..." 的情况（处理本地 md 链接指向章节）
        if original.startswith('href="'):
            if not parsed.scheme:
                def md_anchor(link_path):
                    """将相对当前文件的 .md 路径规范化为相对文档根的锚点"""
                    target_abs = os.path.abspath(os.path.join(docdir, link_path))
                    rel = os.path.relpath(target_abs, os.path.abspath(rootdir))
                    return os.path.splitext(rel)[0].replace('\\', '/')

                if decoded.endswith('.md'):
                    return f'href="#{md_anchor(decoded)}"'
                if '.md#' in decoded:
                    # 跨文件标题锚点无法保证与标题 slug 一致，统一指向目标文件开头
                    return f'href="#{md_anchor(decoded.split("#")[0])}"'

        return original

    # 处理所有匹配（先 src，再 href）
    # 注意：用 callable 保证 match 对象传入
    html_content = re.sub(r'src="([^"]+)"', process_src_match, html_content)
    html_content = re.sub(r'href="([^"]+)"', process_src_match, html_content)

    return html_content, copy_tasks


class CustomRenderer(mistune.HTMLRenderer):
    """自定义 Markdown 渲染器"""
    def heading(self, text, level, **attrs):
        # text 为内联渲染后的 HTML，先剥离标签再用纯文本生成锚点
        hid = attrs.get('id')
        if not hid:
            plain = re.sub(r'<[^>]+>', '', text)
            hid = re.sub(r'[^\w]+', '-', plain.lower()).strip('-') or 'heading'
        return f'<h{level+1} id="{hid}">{text}</h{level+1}>'

    def block_code(self, code, info=None):
        # shell 类代码块（含无语言标注的代码块）统一使用 BSD Shell 词法，
        # 支持行首 #/$ 提示符后的 BSD 命令词高亮；其他语言按其自身词法
        info = (info or '').strip().lower()
        shell_aliases = {'sh', 'shell', 'bash', 'console', 'terminal',
                         'freebsd', 'root', 'csh', 'tcsh', 'zsh', 'command'}
        if not info or info in shell_aliases:
            lexer = BsdShellLexer(stripall=False)
        else:
            try:
                lexer = get_lexer_by_name(info, stripall=False)
            except Exception:
                lexer = get_lexer_by_name('text', stripall=False)
        fmt = pygments_html_formatter.HtmlFormatter()
        return highlight(code, lexer, fmt)

    def strikethrough(self, text):
        return f'<del>{text}</del>'

    def list_item(self, text):
        m = re.match(r'^\s*\[([ xX])\]\s+', text)
        if m:
            chk = 'checked' if m.group(1).lower()=='x' else ''
            content = text[m.end():]
            return f'<li><input type="checkbox" disabled {chk}> {content}</li>'
        return super().list_item(text)


def process_single_markdown_file(args):
    """处理单个 Markdown 文件 - 用于多进程处理"""
    file_info, docdir, images_dir, formulas_enabled = args

    if file_info.startswith('rawchaptertext:'):
        title = file_info.split(':', 1)[1]
        aid = re.sub(r'[^\w]+', '-', title.lower()).strip('-')
        # 章节标题直接携带 id，便于 PDF/EPUB 中从目录页跳转
        return f'<h1 id="{aid}">{title}</h1>\n', []

    path = os.path.join(docdir, file_info)
    if not os.path.exists(path):
        return f'<!-- Warning: {path} 不存在，已跳过 -->\n', []

    anchor = os.path.splitext(file_info)[0]
    md_content = read_markdown_file(path)

    # 预处理 LaTeX 公式（渲染为 SVG 图片并替换为 <img> 标签）
    if formulas_enabled:
        md_content = preprocess_formulas(md_content, images_dir)

    # 创建独立的渲染器实例
    renderer = CustomRenderer(escape=False)
    md = mistune.create_markdown(renderer=renderer, plugins=['table', 'strikethrough', 'footnotes'])
    html_content = md(md_content)

    # 转换本地路径并收集图片任务（并在 worker 内下载在线图片）
    html_content, copy_tasks = convert_local_paths_worker(
        (html_content, os.path.dirname(path), images_dir, docdir))

    return f'<a id="{anchor}"></a>\n{html_content}\n', copy_tasks


def dedupe_heading_ids(html_text: str) -> str:
    """为重复出现的 id 添加数字后缀（首个保留原名），消除跨文件锚点冲突

    指向原名的内部链接会跳到首次出现处，与浏览器对重复 id 的行为一致。
    """
    soup = BeautifulSoup(html_text, 'html.parser')
    seen = {}
    for el in soup.find_all(attrs={'id': True}):
        old = el.get('id')
        n = seen.get(old, 0)
        seen[old] = n + 1
        if n:
            el['id'] = f'{old}-{n}'
    return str(soup)


def combine_markdown_to_html_parallel(docdir: str, files: list, out_html: str,
                                      max_workers=None, formulas_enabled=True):
    """合并多个 Markdown 为单个 HTML - 多进程版本"""
    if max_workers is None:
        max_workers = min(16, multiprocessing.cpu_count())

    print(f"开始并行处理 {len(files)} 个 Markdown 文件...")

    # 准备任务
    tasks = [(file_info, docdir, IMAGES_DIR, formulas_enabled) for file_info in files]

    combined_parts = [None] * len(files)
    all_copy_tasks = []

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        # 提交所有任务
        future_to_index = {
            executor.submit(process_single_markdown_file, task): i
            for i, task in enumerate(tasks)
        }

        # 收集结果
        for future in as_completed(future_to_index):
            index = future_to_index[future]
            try:
                html_content, copy_tasks = future.result()
                combined_parts[index] = html_content
                all_copy_tasks.extend(copy_tasks)

                file_info = files[index]
                if file_info.startswith('rawchaptertext:'):
                    title = file_info.split(':', 1)[1]
                    print(f"[{len([x for x in combined_parts if x is not None])}/{len(files)}] 已处理章节: {title}")
                else:
                    print(f"[{len([x for x in combined_parts if x is not None])}/{len(files)}] 已处理文件: {file_info}")
            except Exception as exc:
                current_count = len([x for x in combined_parts if x is not None])
                file_info = files[index]
                print(f"{current_count}/{len(files)}] 处理文件 {file_info} 时出错: {exc}")
                combined_parts[index] = f'<!-- Error processing {file_info}: {exc} -->\n'

    # 并行复制本地图片
    if all_copy_tasks:
        # 去重复制任务
        unique_copy_tasks = list(set(all_copy_tasks))
        print(f"开始并行复制 {len(unique_copy_tasks)} 个图片文件...")

        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(copy_single_image, task): task for task in unique_copy_tasks}

            success_count = 0
            for future in as_completed(futures):
                success, result = future.result()
                if success:
                    success_count += 1
                else:
                    print(f"复制失败: {result}")

            print(f"图片复制完成: {success_count}/{len(unique_copy_tasks)} 成功")

    # 按原始顺序组合结果
    combined = ''.join(combined_parts)

    # 全局去重 id，消除跨文件同名标题的锚点冲突
    combined = dedupe_heading_ids(combined)

    with open(out_html, 'w', encoding='utf-8') as wf:
        wf.write(combined)
    print(f'Combined HTML saved to {out_html}')


def generate_epub_with_ebooklib(html_file: str, start_html: str, output_epub: str,
                                title='My Book', author=None, language='zh-CN'):
    """使用 EbookLib 从 HTML 生成 EPUB，包含 start.html 的内嵌样式与 CSS

    - 元数据（标题/作者/语言）由调用方传入；
    - 如果存在 images/book-logo.png，会将其作为封面（EPUB 规范 meta 方式），
      并在目录/顺序中把封面页放在第一位；
    - 目录按 H1 章 / H2 节建立两级层级；
    - 正文中的内部链接（href="#id"）会重映射到目标章节文件，
      保证在 EPUB 阅读器中可以点击跳转。
    """
    # 读取合并后的内容
    with open(html_file, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f, 'html.parser')

    book = epub.EpubBook()
    book.set_identifier(
        'mdconv-' + hashlib.md5(((title or '') + (author or '')).encode('utf-8')).hexdigest()[:16]
    )
    book.set_title(title)
    book.set_language(language)
    if author:
        book.add_author(author)

    # 添加 CSS：start.html 引用的外部样式表 + 内嵌 <style> 规则
    css_items = []
    css_rules = []
    with open(start_html, 'r', encoding='utf-8') as f:
        start_soup = BeautifulSoup(f, 'html.parser')
    for link in start_soup.find_all('link', rel='stylesheet'):
        href = link.get('href')
        css_path = os.path.join(os.path.dirname(start_html), href)
        if os.path.exists(css_path):
            with open(css_path, 'r', encoding='utf-8', errors='replace') as cssf:
                css_rules.append(cssf.read())

    for style_tag in start_soup.find_all('style'):
        if style_tag.string:
            css_rules.append(style_tag.string)

    if css_rules:
        css_item = epub.EpubItem(
            uid='main-css',
            file_name=os.path.join(CSS_DIR, 'main.css'),
            media_type='text/css',
            content='\n\n'.join(css_rules).encode('utf-8')
        )
        book.add_item(css_item)
        css_items.append(css_item)

    # 添加霞鹜文楷 GB 版字体（国标字形的屏幕阅读版 / 等宽屏幕版），供阅读器嵌入渲染
    # start.html 的 @font-face 以 ../fonts/ 引用，与 EPUB 内 css/main.css 的相对路径一致
    fonts_dir = os.path.join(os.path.dirname(start_html), 'fonts')
    if os.path.isdir(fonts_dir):
        for fname in sorted(os.listdir(fonts_dir)):
            if not fname.lower().endswith(('.ttf', '.otf')):
                continue
            with open(os.path.join(fonts_dir, fname), 'rb') as ff:
                font_item = epub.EpubItem(
                    uid='font-' + hashlib.md5(fname.encode('utf-8')).hexdigest()[:10],
                    file_name=f'fonts/{fname}',
                    media_type='font/ttf' if fname.lower().endswith('.ttf') else 'font/otf',
                    content=ff.read()
                )
                book.add_item(font_item)

    # 添加图片资源
    images_dir = os.path.join(os.path.dirname(html_file), 'images')
    cover_img_item = None
    if os.path.exists(images_dir):
        for img_name in os.listdir(images_dir):
            img_path = os.path.join(images_dir, img_name)
            if img_name.lower().endswith('.svg'):
                media_type = 'image/svg+xml'
            elif img_name.lower().endswith(('.png',)):
                media_type = 'image/png'
            elif img_name.lower().endswith(('.jpg', '.jpeg')):
                media_type = 'image/jpeg'
            elif img_name.lower().endswith(('.gif',)):
                media_type = 'image/gif'
            elif img_name.lower().endswith(('.webp',)):
                media_type = 'image/webp'
            else:
                media_type = 'application/octet-stream'
            with open(img_path, 'rb') as img_file:
                img_content = img_file.read()
            # EPUB 的 id 需符合 NCName，使用 md5 生成安全 uid
            img_uid = 'img-' + hashlib.md5(img_name.encode('utf-8')).hexdigest()[:12]
            img_item = epub.EpubItem(
                uid=img_uid,
                file_name=f'images/{img_name}',
                media_type=media_type,
                content=img_content
            )
            book.add_item(img_item)

            # 记录是否为封面（文件名 book-logo.png）
            if img_name.lower() == 'book-logo.png':
                cover_img_item = img_item

    # 按 H1/H2 拆分章节，收集 header 前面的锚点 <a id>（避免文件级锚点丢失）
    headers = soup.find_all(['h1', 'h2'])
    # 文件级锚点 <a id> 应归属其后的章节，先标记避免被上一章重复收集
    pre_anchor_set = set()
    for header in headers:
        for prev in header.previous_siblings:
            if isinstance(prev, NavigableString) and not prev.strip():
                continue
            if getattr(prev, 'name', None) == 'a' and prev.get('id'):
                pre_anchor_set.add(id(prev))
            else:
                break

    chapter_records = []
    for idx, header in enumerate(headers):
        level = 1 if header.name == 'h1' else 2
        chap = epub.EpubHtml(
            title=header.get_text(),
            file_name=f'chap_{idx+1}.xhtml',
            lang=language
        )
        pre_anchors = []
        for prev in header.previous_siblings:
            if isinstance(prev, NavigableString) and not prev.strip():
                continue
            if getattr(prev, 'name', None) == 'a' and prev.get('id'):
                pre_anchors.append(prev)
            else:
                break
        content_nodes = list(reversed(pre_anchors)) + [header]
        for sib in header.next_siblings:
            if getattr(sib, 'name', None) in ['h1', 'h2']:
                break
            if id(sib) in pre_anchor_set:
                continue
            content_nodes.append(sib)
        chapter_records.append([chap, level, content_nodes])

    # 收集每章包含的 id，建立 id -> 章节文件名映射
    # 章节开头的文件级锚点（pre-anchor）优先归属到目标章节
    id_map = {}
    for chap, _, content_nodes in chapter_records:
        for node in content_nodes:
            if isinstance(node, Tag) and node.name == 'a' and node.get('id'):
                id_map[node['id']] = chap.file_name
            else:
                break
        for node in content_nodes:
            if isinstance(node, Tag):
                if node.get('id'):
                    id_map.setdefault(node['id'], chap.file_name)
                for el in node.find_all(attrs={'id': True}):
                    id_map.setdefault(el['id'], chap.file_name)

    # 跨章节链接重映射，使 EPUB 内部链接可点击
    for chap, level, content_nodes in chapter_records:
        for node in content_nodes:
            if not isinstance(node, Tag):
                continue
            anchors = node.find_all('a', attrs={'href': True})
            if node.name == 'a' and node.get('href'):
                anchors.append(node)
            for a in anchors:
                href = a.get('href', '')
                if href.startswith('#'):
                    target = href[1:]
                    dest = id_map.get(target)
                    if dest and dest != chap.file_name:
                        a['href'] = f'{dest}#{target}'
        chap.content = ''.join(str(n) for n in content_nodes)
        for css in css_items:
            chap.add_link(href=css.file_name, rel='stylesheet', type='text/css')
        book.add_item(chap)

    # 封面：通过 EPUB 规范 meta 标记封面图片，并创建独立的封面页章节
    cover_chapter = None
    if cover_img_item is not None:
        book.add_metadata(None, 'meta', '', others={'name': 'cover', 'content': cover_img_item.id})
        cover_chapter = epub.EpubHtml(title='Cover', file_name='cover.xhtml', lang=language)
        cover_chapter.content = '<div class="cover"><img src="images/book-logo.png" alt="Cover"/></div>'
        for css in css_items:
            cover_chapter.add_link(href=css.file_name, rel='stylesheet', type='text/css')
        book.add_item(cover_chapter)

    # 定义目录：封面在前，H1 章为一级、H2 节挂在其下
    toc_list = []
    if cover_chapter is not None:
        toc_list.append(cover_chapter)
    current_h1 = None
    for chap, level, _ in chapter_records:
        if level == 1:
            current_h1 = (chap, [])
            toc_list.append(current_h1)
        elif current_h1 is not None:
            current_h1[1].append(chap)
        else:
            toc_list.append(chap)

    book.toc = tuple(toc_list)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    # spine: 保持 nav 在前，随后封面（如果有）和章节
    spine_list = ['nav']
    if cover_chapter is not None:
        spine_list.append(cover_chapter)
    spine_list.extend(chap for chap, _, _ in chapter_records)
    book.spine = spine_list

    epub.write_epub(output_epub, book, {})
    print(f'EPUB generated via EbookLib: {output_epub}')


def generate_docx_with_pydocx(html_file: str, output_docx: str,
                              title=None, author=None, language='zh-CN'):
    """使用 python-docx 从合并 HTML 生成 Word 文档

    标题映射为 Word 内置样式（便于生成目录域）、代码块统一为等宽底纹段落、
    表格/图片/列表/引用按原文结构转换；正文与标题均声明霞鹜文楷屏幕版字体。
    """
    from docx import Document
    from docx.shared import Pt, Cm, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    DOCX_BODY_FONT = 'LXGW WenKai GB Screen'
    DOCX_MONO_FONT = 'LXGW WenKai Mono GB Screen'

    doc = Document()

    # 页面设置为 A4
    section = doc.sections[0]
    section.page_width, section.page_height = Cm(21.0), Cm(29.7)
    section.top_margin = section.bottom_margin = Cm(2.54)
    section.left_margin = section.right_margin = Cm(2.3)

    def apply_cjk_font(style, font_name):
        """为样式同时设置西文与中文字体（Word 需要 w:eastAsia）"""
        style.font.name = font_name
        rpr = style.element.get_or_add_rPr()
        rfonts = rpr.find(qn('w:rFonts'))
        if rfonts is None:
            rfonts = OxmlElement('w:rFonts')
            rpr.append(rfonts)
        rfonts.set(qn('w:eastAsia'), font_name)

    normal = doc.styles['Normal']
    apply_cjk_font(normal, DOCX_BODY_FONT)
    normal.font.size = Pt(11)
    for i, size in [(1, 20), (2, 16), (3, 13), (4, 12)]:
        hstyle = doc.styles[f'Heading {i}']
        apply_cjk_font(hstyle, DOCX_BODY_FONT)
        hstyle.font.size = Pt(size)
        hstyle.font.color.rgb = RGBColor(0x1A, 0x1A, 0x1A)

    if title:
        doc.core_properties.title = title
    if author:
        doc.core_properties.author = author
    doc.core_properties.language = language

    # 读取合并后的内容
    with open(html_file, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f, 'html.parser')

    images_dir = os.path.join(os.path.dirname(html_file), 'images')

    def set_paragraph_shading(paragraph, fill):
        """为段落添加底纹（用于代码块）"""
        ppr = paragraph._p.get_or_add_pPr()
        shd = OxmlElement('w:shd')
        shd.set(qn('w:val'), 'clear')
        shd.set(qn('w:fill'), fill)
        ppr.append(shd)

    def add_inline_runs(paragraph, node, bold=False, italic=False, mono=False):
        """递归将行内内容写入段落，保留粗体/斜体/行内代码"""
        if isinstance(node, NavigableString):
            run = paragraph.add_run(str(node))
            run.bold, run.italic = bold, italic
            if mono:
                run.font.name = DOCX_MONO_FONT
                rpr = run._element.get_or_add_rPr()
                rfonts = rpr.find(qn('w:rFonts'))
                if rfonts is None:
                    rfonts = OxmlElement('w:rFonts')
                    rpr.append(rfonts)
                rfonts.set(qn('w:eastAsia'), DOCX_MONO_FONT)
            return
        for child in node.children:
            if isinstance(child, NavigableString):
                run = paragraph.add_run(str(child))
                run.bold, run.italic = bold, italic
                if mono:
                    run.font.name = DOCX_MONO_FONT
                    rpr = run._element.get_or_add_rPr()
                    rfonts = rpr.find(qn('w:rFonts'))
                    if rfonts is None:
                        rfonts = OxmlElement('w:rFonts')
                        rpr.append(rfonts)
                    rfonts.set(qn('w:eastAsia'), DOCX_MONO_FONT)
                continue
            name = getattr(child, 'name', None)
            if name in ('strong', 'b'):
                add_inline_runs(paragraph, child, True, italic, mono)
            elif name in ('em', 'i'):
                add_inline_runs(paragraph, child, bold, True, mono)
            elif name == 'code':
                add_inline_runs(paragraph, child, bold, italic, True)
            elif name == 'br':
                paragraph.add_run().add_break()
            elif name == 'img':
                add_docx_image(paragraph, child)
            else:
                add_inline_runs(paragraph, child, bold, italic, mono)

    def add_docx_image(paragraph, img_tag):
        src = img_tag.get('src', '')
        path = os.path.join(images_dir, os.path.basename(src)) if src else ''
        if not os.path.isfile(path):
            return
        run = paragraph.add_run()
        try:
            # 图片宽度限制在正文宽度内（A4 去页边距约 16.4cm）
            run.add_picture(path, width=Cm(12))
        except Exception as e:
            print(f'  Word 导出跳过图片 {src}: {e}')

    # 封面页
    cover = soup.find('div', class_='cover-page')
    if cover is not None:
        img = cover.find('img')
        if img is not None:
            src = img.get('src', '')
            path = os.path.join(images_dir, os.path.basename(src)) if src else ''
            if os.path.isfile(path):
                doc.add_picture(path, width=Cm(12))
                doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
        doc.add_page_break()

    # 目录：插入 Word 目录域（打开文档后按 F9 更新域即可生成可点击目录）；
    # PDF 的目录由侧边栏书签承担、EPUB 由 nav 承担，正文不再排版目录页
    p = doc.add_paragraph()
    fld = OxmlElement('w:fldSimple')
    fld.set(qn('w:instr'), r' TOC \o "1-3" \h \z \u ')
    run = OxmlElement('w:r')
    t = OxmlElement('w:t')
    t.text = '（在 Word 中选中此处后按 F9 更新域，即可生成目录）'
    run.append(t)
    fld.append(run)
    p._p.append(fld)
    doc.add_page_break()

    heading_level = {'h1': 1, 'h2': 2, 'h3': 3, 'h4': 4, 'h5': 5, 'h6': 5}

    def walk(node):
        """遍历 body 子节点，转换为 Word 元素"""
        if not isinstance(node, Tag):
            return
        for child in node.children:
            name = getattr(child, 'name', None)
            if name is None:
                text = str(child).strip()
                if text:
                    doc.add_paragraph(text)
                continue
            if name in heading_level:
                p = doc.add_heading('', level=heading_level[name])
                add_inline_runs(p, child)
            elif name == 'p':
                p = doc.add_paragraph()
                p.paragraph_format.first_line_indent = Cm(0.74)
                add_inline_runs(p, child)
            elif name in ('ul', 'ol'):
                walk_list(child, style='List Bullet' if name == 'ul' else 'List Number', depth=1)
            elif name == 'table':
                walk_table(child)
            elif name == 'pre':
                walk_pre(child)
            elif name == 'blockquote':
                walk_blockquote(child)
            elif name == 'div':
                # figure-container 等：直接递归处理内容
                if child.find('img'):
                    for img in child.find_all('img'):
                        p = doc.add_paragraph()
                        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        add_docx_image(p, img)
                else:
                    walk(child)
            elif name == 'img':
                p = doc.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                add_docx_image(p, child)
            elif name == 'hr':
                continue
            else:
                walk(child)

    def walk_list(list_tag, style, depth):
        for li in list_tag.find_all('li', recursive=False):
            p = doc.add_paragraph(style=style if depth == 1 else f'{style} {depth}')
            inner_list = None
            for child in li.children:
                cname = getattr(child, 'name', None)
                if cname in ('ul', 'ol'):
                    inner_list = child
                else:
                    add_inline_runs(p, child)
            if inner_list is not None:
                walk_list(inner_list, style, depth + 1)

    def walk_table(table_tag):
        rows = table_tag.find_all('tr')
        if not rows:
            return
        ncols = max(len(r.find_all(['td', 'th'])) for r in rows)
        table = doc.add_table(rows=len(rows), cols=ncols)
        table.style = 'Table Grid'
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        for ri, tr in enumerate(rows):
            cells = tr.find_all(['td', 'th'])
            for ci, td in enumerate(cells):
                cell = table.cell(ri, ci)
                cell.paragraphs[0].text = ''
                add_inline_runs(cell.paragraphs[0], td)
                if td.name == 'th':
                    for run in cell.paragraphs[0].runs:
                        run.bold = True

    def walk_pre(pre_tag):
        code_text = pre_tag.get_text()
        for line in code_text.splitlines() or ['']:
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(0)
            set_paragraph_shading(p, 'FAF7F8')
            run = p.add_run(line if line else '')
            run.font.name = DOCX_MONO_FONT
            run.font.size = Pt(9.5)
            rpr = run._element.get_or_add_rPr()
            rfonts = rpr.find(qn('w:rFonts'))
            if rfonts is None:
                rfonts = OxmlElement('w:rFonts')
                rpr.append(rfonts)
            rfonts.set(qn('w:eastAsia'), DOCX_MONO_FONT)
        doc.add_paragraph()

    def walk_blockquote(bq_tag):
        for child in bq_tag.children:
            cname = getattr(child, 'name', None)
            if cname == 'p':
                p = doc.add_paragraph()
                p.paragraph_format.left_indent = Cm(0.74)
                add_inline_runs(p, child)
            elif cname is None:
                text = str(child).strip()
                if text:
                    p = doc.add_paragraph()
                    p.paragraph_format.left_indent = Cm(0.74)
                    p.add_run(text)
            else:
                walk(child)

    body = soup.body if soup.body else soup
    walk(body)

    doc.save(output_docx)
    print(f'DOCX generated via python-docx: {output_docx}')


def _patch_pdfa4_output():
    """补齐 WeasyPrint 的 pdf/a-4u 输出与 ISO 19005-4 的差异。

    1. 6.7.3 规定非 4e/4f 的 PDF/A-4 不得带 pdfaid:conformance，而该变体固定写 "U"；
    2. 6.7.3 要求 XMP 带 pdfaid:rev="2020"，而 WeasyPrint 从不写 rev 属性；
    3. 6.2.2 禁止内容流出现 ISO 32000-2 未定义的操作符，而上游 SVG 渲染在部分
       图形（如 shields.io 徽章）上会写入 nan 坐标，产生非法操作符；
    4. 6.2.7.1 要求图像字典的 Interpolate 为 false，而上游按 image-rendering
       的默认值（auto）写 true，与 PDF/A 冲突。
    四处在渲染阶段修正，避免对已写出的 PDF 字节做改写。
    """
    import math
    import pydyf
    from weasyprint.pdf import metadata as wp_metadata
    from weasyprint.images import RasterImage

    cls = wp_metadata.DocumentMetadata
    if not (hasattr(cls, 'include_in_pdf')
            and hasattr(cls, 'generate_rdf_metadata')):
        # 上游重构了元数据接口时不做修补，由 CI 的 veraPDF 校验暴露问题
        return
    if not getattr(cls.include_in_pdf, '_mdconv_pdfa4', False):
        original_include = cls.include_in_pdf
        original_generate = cls.generate_rdf_metadata

        def include_in_pdf(self, pdf, variant, version, conformance, compress):
            if variant == 'a' and version >= 4:
                conformance = None
            return original_include(
                self, pdf, variant, version, conformance, compress)

        def generate_rdf_metadata(self, variant, version, conformance):
            data = original_generate(self, variant, version, conformance)
            if variant == 'a' and version >= 4:
                data = data.replace(b'pdfaid:part="4"',
                                    b'pdfaid:part="4" pdfaid:rev="2020"')
            return data

        include_in_pdf._mdconv_pdfa4 = True
        cls.include_in_pdf = include_in_pdf
        cls.generate_rdf_metadata = generate_rdf_metadata

    # NaN/Inf 坐标在 PDF 中会序列化为未定义的 nan/inf 操作符；
    # pydyf 所有图元都经 _to_bytes 格式化，在此统一折算为 0
    # （NaN 图形本就不显示，折算后宽度或高度为 0，视觉无变化）
    if not getattr(pydyf._to_bytes, '_mdconv_pdfa4', False):
        original_to_bytes = pydyf._to_bytes

        def _to_bytes(item):
            if isinstance(item, float) and not math.isfinite(item):
                item = 0.0
            return original_to_bytes(item)

        _to_bytes._mdconv_pdfa4 = True
        pydyf._to_bytes = _to_bytes

    # Interpolate 只影响阅读器缩放时的平滑方式，不改变图像像素数据；
    # PDF/A 要求为 false，故对位图统一关闭
    if not getattr(RasterImage.get_x_object, '_mdconv_pdfa4', False):
        original_get_x_object = RasterImage.get_x_object

        def get_x_object(self, interpolate, dpi_ratio):
            return original_get_x_object(self, False, dpi_ratio)

        get_x_object._mdconv_pdfa4 = True
        RasterImage.get_x_object = get_x_object


def build_toc_page(html_text: str, depth: int) -> str:
    """按正文标题生成目录页（替代把源目录文件整篇排版成页）。

    条目复用正文标题的锚点与文本，页码由 start.html 中的
    target-counter 在排版阶段计算，因此目录页码与页脚页码天然一致；
    深度与 PDF 书签相同，以 Markdown 标题级别计（1 为章标题）。
    """
    soup = BeautifulSoup(html_text, 'html.parser')
    entries = []
    for tag in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
        # mdconv 把 Markdown 标题统一下移一级（# → h2），故减 1 还原级别
        level = int(tag.name[1]) - 1
        if level < 1 or level > depth:
            continue
        text = tag.get_text(' ', strip=True)
        hid = tag.get('id')
        if not text or not hid:
            continue
        entries.append((level, hid, text))
    if not entries:
        return ''

    lines = ['<div class="toc-page">',
             f'  <div class="toc-heading">{TOC_PAGE_TITLE}</div>']
    for level, hid, text in entries:
        lines.append(
            f'  <div class="toc-line toc-level-{level}">'
            f'<a href="#{hid}">{html_escape(text)}</a></div>')
    lines.append('</div>\n')
    return '\n'.join(lines)


def build_bookmark_css(depth: int) -> str:
    """生成 PDF 书签层级规则（Markdown 标题级别 → 书签层级）。

    mdconv 把 Markdown 标题统一下移一级（# → h2），故 Markdown 第 N 级
    对应 h{N+1}；超出深度的标题显式关闭书签，覆盖 start.html 的兜底规则。
    """
    rules = []
    for level in range(1, min(depth, 6) + 1):
        rules.append(f'h{level + 1} {{ bookmark-level: {level}; }}')
    for level in range(depth + 1, 6):
        rules.append(f'h{level + 1} {{ bookmark-level: none; }}')
    return '\n'.join(rules)


def absolutize_pdf_assets(html_text: str) -> str:
    """把 PDF 版 HTML 中指向仓库资源的相对 URL 换成 file:// 绝对 URL。

    start.html 用 ../fonts/ 与 ../highlight.css 引用内置字体与高亮样式，
    这对位于仓库根下的 build 目录成立；但输出目录可能在别处（测试用临时
    目录、-o 指定外部路径），相对路径会让 WeasyPrint 找不到字体而回退系统
    字体，中文缺字形时正文会变成不可提取的 CID 编码。
    """
    base = Path(os.path.dirname(os.path.abspath(START_HTML))).as_uri()
    html_text = html_text.replace('url("../fonts/', f'url("{base}/fonts/')
    html_text = html_text.replace(
        'href="../highlight.css"', f'href="{base}/highlight.css"')
    return html_text


def main(docdir: str, build_dir: str = BUILD_DIR, max_workers=None,
         title=None, author=None, language='zh-CN',
         make_pdf=True, make_epub=True, make_docx=True, formulas_enabled=True,
         bookmark_depth=DEFAULT_BOOKMARK_DEPTH):
    # 公式缓存目录通过环境变量传递给多进程 worker（不覆盖调用方的预先设置）
    os.environ.setdefault('MDCONV_FORMULA_CACHE', FORMULA_CACHE_DIR)

    prepare_build_dir(build_dir)

    # 检测 LaTeX 引擎（公式渲染支持）
    engine = find_latex_engine()
    if formulas_enabled:
        if engine:
            print(f"公式渲染支持: 已启用 (引擎: {engine})")
        else:
            print("公式渲染支持: 未启用 (未找到 LaTeX 引擎，如需公式支持请安装 MiKTeX 或 TeX Live)")
    else:
        print("公式渲染支持: 已禁用 (--no-formula)")

    # 若 docdir 下存在 book-logo.png，则复制到 build/images 并在后续生成中作为封面使用
    logo_src = os.path.join(docdir, 'book-logo.png')
    if os.path.exists(logo_src):
        try:
            shutil.copy(logo_src, os.path.join(IMAGES_DIR, 'book-logo.png'))
            print('Found book-logo.png -> copied to build/images and will be used as cover')
        except Exception as e:
            print(f'Failed to copy book-logo.png: {e}')

    # 处理 SUMMARY.md
    summ = os.path.join(docdir, SUMMARY_FILE)
    with open(summ, 'r', encoding='utf-8') as f:
        content = f.read()
    summary_md = re.sub(r'## (.+?)$', r'[\1](rawchaptertext:\1)', content, flags=re.MULTILINE)
    summary_build = os.path.join(build_dir, 'summary.md')
    with open(summary_build, 'w', encoding='utf-8') as f:
        f.write(summary_md)

    # 提取文件列表
    files = re.findall(r'\[.*?\]\((.*?)\)', summary_md)

    # 目录由各格式的原生导航承担（PDF 侧边栏书签 / EPUB nav / Word 目录域），
    # 源目录文件（默认 mu-lu.md）不再单独排版成页，并从正文条目中剔除，
    # 避免把整份目录当普通章节再渲染一遍；
    # PDF 另在正文前生成一页由标题构建的目录（见 build_toc_page），供打印翻阅
    toc_rel_path = DEFAULT_TOC_FILE if os.path.exists(
        os.path.join(docdir, DEFAULT_TOC_FILE)) else None
    if toc_rel_path in files:
        files = [f for f in files if f != toc_rel_path]

    # 生成合并 HTML（使用多进程）
    combined_html = os.path.join(build_dir, FINAL_HTML)
    combine_markdown_to_html_parallel(docdir, files, combined_html,
                                      max_workers=max_workers,
                                      formulas_enabled=formulas_enabled)

    # 合并 start.html + combined.html
    with open(START_HTML, 'r', encoding='utf-8') as f1, \
         open(combined_html, 'r', encoding='utf-8') as f2:
        start_html_content = f1.read()
        combined_content = f2.read()

    # 如果存在封面图片（已被复制到 build/images/book-logo.png），将其插入为第一页面
    cover_html = ''
    possible_cover = os.path.join(IMAGES_DIR, 'book-logo.png')
    if os.path.exists(possible_cover):
        # 插入一个简单的封面 HTML，尽量保证单独占一页（含主色渐变装饰条，
        # 色值与 start.html 的 FreeBSD-Ask VitePress 主题令牌保持一致）
        # 封面不设 page-break-after：章标题自带「前分页」，两边都设会叠出空白页
        cover_html = ('<div class="cover-page" style="display:flex; '
                      'flex-direction:column; align-items:center; justify-content:center; height:100vh;">'
                      '<img src="images/book-logo.png" alt="Cover" style="max-width:85%; max-height:65vh; display:block; margin:auto;"/>'
                      '<div style="width:7cm; height:3px; margin-top:1.4cm; border-radius:2px; '
                      'background:linear-gradient(90deg, #FF0072 0%, #F3714B 55%, #F8C27B 100%);"></div>'
                      '</div>\n')

    # 将封面与正文插入 start.html 的 <body> 内部，
    # 保证 HTML 结构规范（依赖解析容错会丢失 body 外内容，如 Word 导出）
    body_close = start_html_content.find('</body>')

    def _merge(body_html):
        if body_close != -1:
            return (start_html_content[:body_close] + body_html
                    + start_html_content[body_close:])
        return body_html + start_html_content

    merged = _merge(cover_html + '\n' + combined_content + '\n')
    final_html = os.path.join(build_dir, FINAL_HTML)
    with open(final_html, 'w', encoding='utf-8') as f:
        f.write(merged)
    print(f'Merged HTML saved to {final_html}')

    # PDF 专用版本：在封面之后插入目录页，并按 bookmark_depth 注入书签层级；
    # EPUB 的 nav 与 Word 的 TOC 域各有实现，故仍读不含目录页的 final.html
    toc_html = build_toc_page(combined_content, bookmark_depth)
    pdf_merged = _merge(cover_html + '\n' + toc_html
                        + combined_content + '\n')
    bookmark_style = f'<style>\n{build_bookmark_css(bookmark_depth)}\n</style>\n'
    head_close = pdf_merged.find('</head>')
    if head_close != -1:
        pdf_merged = (pdf_merged[:head_close] + bookmark_style
                      + pdf_merged[head_close:])
    pdf_html = os.path.join(build_dir, PDF_HTML)
    with open(pdf_html, 'w', encoding='utf-8') as f:
        f.write(absolutize_pdf_assets(pdf_merged))

    # 默认元数据从 start.html 读取
    if title is None or author is None:
        with open(START_HTML, 'r', encoding='utf-8') as f:
            meta_soup = BeautifulSoup(f, 'html.parser')
        if title is None:
            t = meta_soup.find('title')
            title = t.get_text().strip() if t else 'My Book'
        if author is None:
            m = meta_soup.find('meta', attrs={'name': 'author'})
            author = m.get('content', '').strip() if m else None

    # 生成 PDF（WeasyPrint 在此处才导入，见文件头说明）
    if make_pdf:
        from weasyprint import HTML
        from weasyprint.text.fonts import FontConfiguration

        print('Generating PDF (this may take a while)...')
        _patch_pdfa4_output()
        font_conf = FontConfiguration()
        HTML(pdf_html).write_pdf(
            os.path.join(build_dir, FINAL_PDF),
            font_config=font_conf,
            # PDF/A-4U（ISO 19005-4:2020，基于 PDF 2.0 / ISO 32000-2，U 级）；
            # 变体本身会设 2.0，但显式传值优先于变体默认值，两者须保持一致
            pdf_version="2.0",
            pdf_variant="pdf/a-4u",
            metadata=True,
        )
        print(f'PDF generated: {os.path.join(build_dir, FINAL_PDF)}')
    else:
        print('已跳过 PDF 生成 (--no-pdf)')

    # 生成 EPUB（包含 start.html 的样式、CSS 与字体）
    if make_epub:
        epub_path = os.path.join(build_dir, FINAL_EPUB)
        generate_epub_with_ebooklib(final_html, START_HTML, epub_path,
                                    title=title, author=author, language=language)
    else:
        print('已跳过 EPUB 生成 (--no-epub)')

    # 生成 Word 文档
    if make_docx:
        docx_path = os.path.join(build_dir, FINAL_DOCX)
        generate_docx_with_pydocx(final_html, docx_path,
                                  title=title, author=author, language=language)
    else:
        print('已跳过 Word 生成 (--no-docx)')


if __name__ == '__main__':
    # 确保在 Windows 上多进程能正常工作
    multiprocessing.freeze_support()

    parser = argparse.ArgumentParser(description='从 Markdown 生成 PDF 和 EPUB')
    parser.add_argument('docdir', type=str, help='文档根目录')
    parser.add_argument('-o', '--output', type=str, default=BUILD_DIR,
                        help='输出目录（默认 build）')
    parser.add_argument('--no-pdf', action='store_true',
                        help='跳过 PDF 生成')
    parser.add_argument('--no-epub', action='store_true',
                        help='跳过 EPUB 生成')
    parser.add_argument('--no-docx', action='store_true',
                        help='跳过 Word 文档生成')
    parser.add_argument('--no-formula', action='store_true',
                        help='跳过 LaTeX 公式渲染')
    parser.add_argument('-j', '--workers', type=int, default=None,
                        help='并行进程数（默认 CPU 核数，上限 16）')
    parser.add_argument('--title', type=str, default=None,
                        help='书籍标题（默认读取 start.html 的 <title>）')
    parser.add_argument('--author', type=str, default=None,
                        help='作者（默认读取 start.html 的 meta author）')
    parser.add_argument('--language', type=str, default='zh-CN',
                        help='书籍语言（默认 zh-CN）')
    parser.add_argument('--bookmark-depth', type=int, default=DEFAULT_BOOKMARK_DEPTH,
                        choices=range(1, 7), metavar='{1-6}',
                        help='PDF 书签与目录的标题深度，按 Markdown 标题级别计'
                             '（默认 2，即到二级标题 ##）')
    args = parser.parse_args()
    main(args.docdir, build_dir=args.output, max_workers=args.workers,
         title=args.title, author=args.author, language=args.language,
         make_pdf=not args.no_pdf, make_epub=not args.no_epub,
         make_docx=not args.no_docx, formulas_enabled=not args.no_formula,
         bookmark_depth=args.bookmark_depth)
