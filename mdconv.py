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

from weasyprint import HTML
from weasyprint.text.fonts import FontConfiguration

import mistune
from pygments import highlight
from pygments.lexers import get_lexer_by_name
from pygments.formatters import html as pygments_html_formatter

from ebooklib import epub
from bs4 import BeautifulSoup

# 新增 imports
import urllib.request
import mimetypes
import io

# 常量定义
BUILD_DIR = 'build'
SUMMARY_FILE = 'SUMMARY.md'
START_HTML = 'start.html'
FINAL_HTML = 'final.html'
FINAL_PDF = 'final.pdf'
FINAL_EPUB = 'final.epub'
CSS_DIR = 'css'

# 全局变量，会在每个子进程中重新初始化
IMAGES_DIR = None


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
    返回：(html_content, copy_tasks)
    copy_tasks 中仅包含需要由主进程复制的本地文件对 (abs_path, dst_path)
    """
    html_content, docdir, images_dir = args

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
        decoded = unquote(val)
        parsed = urlparse(decoded)

        # 处理 src="..." 的情况（图片）
        if original.startswith('src="'):
            # protocol-relative URL 开头的情况
            if decoded.startswith('//') or parsed.scheme in ('http', 'https'):
                # 在线图片 -> 下载到 images_dir
                url = decoded if not decoded.startswith('//') else 'https:' + decoded
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
                abs_path = os.path.abspath(os.path.join(docdir, decoded))
                name, ext = os.path.splitext(os.path.basename(abs_path))
                if not re.match(r'^[A-Za-z0-9]+$', name):
                    md5 = hashlib.md5(name.encode('utf-8')).hexdigest()
                    new_name = md5 + ext
                else:
                    new_name = f"{name}{ext}"
                dst = os.path.join(images_dir, new_name)

                # 记录需要复制的任务（主进程会并行复制）
                copy_tasks.append((abs_path, dst))
                return f'src="images/{new_name}"'

        # 处理 href="..." 的情况（处理本地 md 链接指向章节）
        if original.startswith('href="'):
            if not parsed.scheme:
                if decoded.endswith('.md'):
                    anchor = os.path.splitext(decoded)[0]
                    return f'href="#${anchor}"'
                if '.md#' in decoded:
                    return f'href="#${decoded.split("#")[1]}"'

        return original

    # 处理所有匹配（先 src，再 href）
    # 注意：用 callable 保证 match 对象传入
    html_content = re.sub(r'src="([^"]+)"', process_src_match, html_content)
    html_content = re.sub(r'href="([^"]+)"', process_src_match, html_content)

    return html_content, copy_tasks


def convert_local_paths_parallel(html_contents, docdirs, images_dir, max_workers=None):
    """并行处理多个 HTML 内容的本地路径转换"""
    if max_workers is None:
        max_workers = min(16, multiprocessing.cpu_count())

    print(f"开始并行处理 {len(html_contents)} 个 HTML 文件的本地路径...")

    # 准备任务
    tasks = [(html_content, docdir, images_dir)
             for html_content, docdir in zip(html_contents, docdirs)]

    all_copy_tasks = []
    processed_htmls = []

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        # 提交所有任务
        future_to_index = {
            executor.submit(convert_local_paths_worker, task): i
            for i, task in enumerate(tasks)
        }

        # 收集结果
        for future in as_completed(future_to_index):
            index = future_to_index[future]
            try:
                html_content, copy_tasks = future.result()
                processed_htmls.append((index, html_content))
                all_copy_tasks.extend(copy_tasks)
                print(f"[{len(processed_htmls)}/{len(tasks)}] 已处理 HTML 文件")
            except Exception as exc:
                print(f"处理 HTML 文件时出错: {exc}")
                # 保持原始内容作为后备
                processed_htmls.append((index, html_contents[index]))

    # 按原始顺序排序
    processed_htmls.sort(key=lambda x: x[0])
    final_htmls = [html for _, html in processed_htmls]

    # 去重复制任务（避免重复复制同一图片）
    unique_copy_tasks = list(set(all_copy_tasks))

    return final_htmls, unique_copy_tasks


class CustomRenderer(mistune.HTMLRenderer):
    """自定义 Markdown 渲染器"""
    def heading(self, text, level, raw=None):
        anchor = re.sub(r'[^\w]+', '-', text.lower()).strip('-')
        return f'<h{level+1} id="{anchor}">{text}</h{level+1}>'

    def block_code(self, code, info=None):
        if info:
            try:
                lexer = get_lexer_by_name(info.strip(), stripall=True)
            except Exception:
                lexer = get_lexer_by_name('text', stripall=True)
        else:
            lexer = get_lexer_by_name('text', stripall=True)
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


def markdown_to_html_worker(args):
    """将单个 Markdown 转换为 HTML - 多进程工作函数"""
    md_text, docdir = args

    renderer = CustomRenderer(escape=False)
    # 启用脚注插件
    md = mistune.create_markdown(renderer=renderer, plugins=['table', 'strikethrough', 'footnotes'])
    html = md(md_text)

    return html


def markdown_to_html_parallel(md_texts, docdirs, max_workers=None):
    """并行将多个 Markdown 转换为 HTML"""
    if max_workers is None:
        max_workers = min(16, multiprocessing.cpu_count())

    print(f"开始并行处理 {len(md_texts)} 个 Markdown 文件...")

    # 准备任务
    tasks = [(md_text, docdir) for md_text, docdir in zip(md_texts, docdirs)]

    processed_htmls = []

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        # 提交所有任务
        future_to_index = {
            executor.submit(markdown_to_html_worker, task): i
            for i, task in enumerate(tasks)
        }

        # 收集结果
        for future in as_completed(future_to_index):
            index = future_to_index[future]
            try:
                html_content = future.result()
                processed_htmls.append((index, html_content))
                print(f"[{len(processed_htmls)}/{len(tasks)}] 已转换 Markdown 文件")
            except Exception as exc:
                print(f"转换 Markdown 文件时出错: {exc}")
                # 返回原始文本作为后备
                processed_htmls.append((index, f"<pre>{md_texts[index]}</pre>"))

    # 按原始顺序排序
    processed_htmls.sort(key=lambda x: x[0])
    return [html for _, html in processed_htmls]


def process_single_markdown_file(args):
    """处理单个 Markdown 文件 - 用于多进程处理"""
    file_info, docdir, images_dir = args

    if file_info.startswith('rawchaptertext:'):
        title = file_info.split(':', 1)[1]
        aid = re.sub(r'[^\w]+', '-', title.lower()).strip('-')
        return f'<a id="{aid}"></a>\n<h1>{title}</h1>\n', []

    path = os.path.join(docdir, file_info)
    if not os.path.exists(path):
        return f'<!-- Warning: {path} 不存在，已跳过 -->\n', []

    anchor = os.path.splitext(file_info)[0]
    md_content = read_markdown_file(path)

    # 创建独立的渲染器实例
    renderer = CustomRenderer(escape=False)
    md = mistune.create_markdown(renderer=renderer, plugins=['table', 'strikethrough', 'footnotes'])
    html_content = md(md_content)

    # 转换本地路径并收集图片任务（并在 worker 内下载在线图片）
    html_content, copy_tasks = convert_local_paths_worker((html_content, os.path.dirname(path), images_dir))

    return f'<a id="{anchor}"></a>\n{html_content}\n', copy_tasks


def combine_markdown_to_html_parallel(docdir: str, files: list, out_html: str, max_workers=None):
    """合并多个 Markdown 为单个 HTML - 多进程版本"""
    if max_workers is None:
        max_workers = min(16, multiprocessing.cpu_count())

    print(f"开始并行处理 {len(files)} 个 Markdown 文件...")

    # 准备任务
    tasks = [(file_info, docdir, IMAGES_DIR) for file_info in files]

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
                print(f"[{current_count}/{len(files)}] 处理文件 {file_info} 时出错: {exc}")
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

    with open(out_html, 'w', encoding='utf-8') as wf:
        wf.write(combined)
    print(f'Combined HTML saved to {out_html}')


def generate_epub_with_ebooklib(html_file: str, start_html: str, output_epub: str):
    """使用 EbookLib 从 HTML 生成 EPUB，包含 start.html 和 CSS"""
    # 读取合并后的内容
    with open(html_file, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f, 'html.parser')

    book = epub.EpubBook()
    book.set_identifier('id123456')
    book.set_title('My Book')
    book.set_language('zh')

    # 添加 CSS
    css_items = []
    with open(start_html, 'r', encoding='utf-8') as f:
        start_soup = BeautifulSoup(f, 'html.parser')
    for link in start_soup.find_all('link', rel='stylesheet'):
        href = link.get('href')
        css_path = os.path.join(os.path.dirname(start_html), href)
        if os.path.exists(css_path):
            with open(css_path, 'rb') as cssf:
                css_content = cssf.read()
            css_item = epub.EpubItem(
                uid=os.path.basename(href),
                file_name=os.path.join(CSS_DIR, os.path.basename(href)),
                media_type='text/css',
                content=css_content
            )
            book.add_item(css_item)
            css_items.append(css_item)

    # 添加图片资源
    images_dir = os.path.join(os.path.dirname(html_file), 'images')
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
            img_item = epub.EpubItem(
                uid=img_name,
                file_name=f'images/{img_name}',
                media_type=media_type,
                content=img_content
            )
            book.add_item(img_item)

    # 按 H1/H2 拆分章节
    chapters = []
    for idx, header in enumerate(soup.find_all(['h1', 'h2'])):
        chap = epub.EpubHtml(
            title=header.get_text(),
            file_name=f'chap_{idx+1}.xhtml',
            lang='zh'
        )
        content = [header]
        for sib in header.next_siblings:
            if sib.name in ['h1', 'h2']:
                break
            content.append(sib)
        chap.content = ''.join(str(tag) for tag in content)
        for css in css_items:
            chap.add_link(href=css.file_name, rel='stylesheet', type='text/css')
        book.add_item(chap)
        chapters.append(chap)

    # 定义目录和 spine
    book.toc = tuple(chapters)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ['nav'] + chapters

    epub.write_epub(output_epub, book, {})
    print(f'EPUB generated via EbookLib: {output_epub}')


def main(docdir: str):
    prepare_build_dir(BUILD_DIR)

    # 处理 SUMMARY.md
    summ = os.path.join(docdir, SUMMARY_FILE)
    with open(summ, 'r', encoding='utf-8') as f:
        content = f.read()
    summary_md = re.sub(r'## (.+?)$', r'[\1](rawchaptertext:\1)', content, flags=re.MULTILINE)
    summary_build = os.path.join(BUILD_DIR, 'summary.md')
    with open(summary_build, 'w', encoding='utf-8') as f:
        f.write(summary_md)

    # 提取文件列表
    files = re.findall(r'\[.*?\]\((.*?)\)', summary_md)

    # 生成合并 HTML（使用多进程）
    combined_html = os.path.join(BUILD_DIR, FINAL_HTML)
    combine_markdown_to_html_parallel(docdir, files, combined_html)

    # 合并 start.html + combined.html
    with open(START_HTML, 'r', encoding='utf-8') as f1, \
         open(combined_html, 'r', encoding='utf-8') as f2:
        merged = f1.read() + '\n' + f2.read()
    final_html = os.path.join(BUILD_DIR, FINAL_HTML)
    with open(final_html, 'w', encoding='utf-8') as f:
        f.write(merged)
    print(f'Merged HTML saved to {final_html}')

    # 生成 PDF
    print('Generating PDF (this may take a while)...')
    font_conf = FontConfiguration()
    HTML(final_html).write_pdf(
        os.path.join(BUILD_DIR, FINAL_PDF),
        font_config=font_conf,
        pdf_version="1.7",
        pdf_variant="pdf/a-3u",
        metadata=True,
    )
    print(f'PDF generated: {os.path.join(BUILD_DIR, FINAL_PDF)}')

    # 生成 EPUB（包含 start.html 和 CSS）
    epub_path = os.path.join(BUILD_DIR, FINAL_EPUB)
    generate_epub_with_ebooklib(final_html, START_HTML, epub_path)


if __name__ == '__main__':
    # 确保在 Windows 上多进程能正常工作
    multiprocessing.freeze_support()

    parser = argparse.ArgumentParser(description='从 Markdown 生成 PDF 和 EPUB')
    parser.add_argument('docdir', type=str, help='文档根目录')
    args = parser.parse_args()
    main(args.docdir)
