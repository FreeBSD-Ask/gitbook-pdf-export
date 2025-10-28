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
import warnings

# 在导入其他模块前过滤警告
warnings.filterwarnings("ignore", category=RuntimeWarning, module="importlib._bootstrap")

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


def init_worker(images_dir):
    """初始化工作进程"""
    global IMAGES_DIR
    IMAGES_DIR = images_dir
    # 在工作进程中过滤警告
    warnings.filterwarnings("ignore", category=RuntimeWarning, module="importlib._bootstrap")


def convert_local_paths_worker(args):
    """处理本地图片路径和链接路径 - 多进程工作函数"""
    html_content, docdir = args
    
    # 收集所有需要复制的图片任务
    copy_tasks = []
    
    def process_src_match(match):
        val = match.group(1)
        decoded = unquote(val)
        parsed = urlparse(decoded)
        
        # 本地资源
        if not parsed.scheme:
            if match.group(0).startswith('src="'):
                abs_path = os.path.abspath(os.path.join(docdir, decoded))
                name, ext = os.path.splitext(os.path.basename(abs_path))
                if not re.match(r'^[A-Za-z0-9]+$', name):
                    md5 = hashlib.md5(name.encode('utf-8')).hexdigest()
                    new_name = md5 + ext
                else:
                    new_name = f"{name}{ext}"
                dst = os.path.join(IMAGES_DIR, new_name)
                
                # 记录需要复制的任务
                copy_tasks.append((abs_path, dst))
                return f'src="images/{new_name}"'
            elif match.group(0).startswith('href="'):
                if decoded.endswith('.md'):
                    anchor = os.path.splitext(decoded)[0]
                    return f'href="#${anchor}"'
                if '.md#' in decoded:
                    return f'href="#${decoded.split("#")[1]}"'
        return match.group(0)

    # 处理所有匹配
    html_content = re.sub(r'src="([^"]+)"', process_src_match, html_content)
    html_content = re.sub(r'href="([^"]+)"', process_src_match, html_content)
    
    return html_content, copy_tasks


class CustomRenderer:
    """自定义 Markdown 渲染器 - 避免在子进程中重复导入"""
    def __init__(self):
        # 延迟导入，避免在子进程中重复导入的开销
        from pygments import highlight
        from pygments.lexers import get_lexer_by_name
        from pygments.formatters import html as pygments_html_formatter
        self.highlight = highlight
        self.get_lexer_by_name = get_lexer_by_name
        self.HtmlFormatter = pygments_html_formatter.HtmlFormatter
    
    def heading(self, text, level, raw=None):
        anchor = re.sub(r'[^\w]+', '-', text.lower()).strip('-')
        return f'<h{level+1} id="{anchor}">{text}</h{level+1}>'

    def block_code(self, code, info=None):
        if info:
            try:
                lexer = self.get_lexer_by_name(info.strip(), stripall=True)
            except Exception:
                lexer = self.get_lexer_by_name('text', stripall=True)
        else:
            lexer = self.get_lexer_by_name('text', stripall=True)
        fmt = self.HtmlFormatter()
        return self.highlight(code, lexer, fmt)

    def strikethrough(self, text):
        return f'<del>{text}</del>'

    def list_item(self, text):
        m = re.match(r'^\s*\[([ xX])\]\s+', text)
        if m:
            chk = 'checked' if m.group(1).lower()=='x' else ''
            content = text[m.end():]
            return f'<li><input type="checkbox" disabled {chk}> {content}</li>'
        return f'<li>{text}</li>'


def markdown_to_html_worker(args):
    """将单个 Markdown 转换为 HTML - 多进程工作函数"""
    md_text, docdir = args
    
    # 在工作进程中创建渲染器和处理器
    renderer = CustomRenderer()
    
    # 使用简单的正则替换实现基本 Markdown 解析
    # 这样可以避免在子进程中导入 mistune
    html = md_text
    
    # 标题
    html = re.sub(r'^# (.+)$', lambda m: renderer.heading(m.group(1), 0), html, flags=re.MULTILINE)
    html = re.sub(r'^## (.+)$', lambda m: renderer.heading(m.group(1), 1), html, flags=re.MULTILINE)
    html = re.sub(r'^### (.+)$', lambda m: renderer.heading(m.group(1), 2), html, flags=re.MULTILINE)
    
    # 代码块
    html = re.sub(r'```(\w+)?\n(.*?)\n```', 
                 lambda m: renderer.block_code(m.group(2), m.group(1)), 
                 html, flags=re.DOTALL)
    
    # 删除线
    html = re.sub(r'~~(.*?)~~', lambda m: renderer.strikethrough(m.group(1)), html)
    
    # 列表项
    html = re.sub(r'^\s*-\s+(.+)$', lambda m: renderer.list_item(m.group(1)), html, flags=re.MULTILINE)
    
    # 段落（简单处理）
    html = re.sub(r'^(?!<[hli])(.+)$', r'<p>\1</p>', html, flags=re.MULTILINE)
    
    return html


def process_single_markdown_file(args):
    """处理单个 Markdown 文件 - 用于多进程处理"""
    file_info, docdir = args
    
    if file_info.startswith('rawchaptertext:'):
        title = file_info.split(':', 1)[1]
        aid = re.sub(r'[^\w]+', '-', title.lower()).strip('-')
        return f'<a id="{aid}"></a>\n<h1>{title}</h1>\n', []
    
    path = os.path.join(docdir, file_info)
    if not os.path.exists(path):
        return f'<!-- Warning: {path} 不存在，已跳过 -->\n', []
    
    anchor = os.path.splitext(file_info)[0]
    md_content = read_markdown_file(path)
    
    # 转换 Markdown 到 HTML
    html_content = markdown_to_html_worker((md_content, os.path.dirname(path)))
    
    # 转换本地路径并收集图片任务
    html_content, copy_tasks = convert_local_paths_worker((html_content, os.path.dirname(path)))
    
    return f'<a id="{anchor}"></a>\n{html_content}\n', copy_tasks


def combine_markdown_to_html_parallel(docdir: str, files: list, out_html: str, max_workers=None):
    """合并多个 Markdown 为单个 HTML - 多进程版本"""
    if max_workers is None:
        max_workers = min(8, multiprocessing.cpu_count())  # 减少进程数以降低内存使用
    
    print(f"开始并行处理 {len(files)} 个 Markdown 文件...")
    
    # 准备任务
    tasks = [(file_info, docdir) for file_info in files]
    
    combined_parts = [None] * len(files)
    all_copy_tasks = []
    
    with ProcessPoolExecutor(
        max_workers=max_workers,
        initializer=init_worker,
        initargs=(IMAGES_DIR,)
    ) as executor:
        # 提交所有任务
        future_to_index = {
            executor.submit(process_single_markdown_file, task): i 
            for i, task in enumerate(tasks)
        }
        
        # 收集结果
        completed_count = 0
        for future in as_completed(future_to_index):
            index = future_to_index[future]
            try:
                html_content, copy_tasks = future.result()
                combined_parts[index] = html_content
                all_copy_tasks.extend(copy_tasks)
                
                completed_count += 1
                file_info = files[index]
                if file_info.startswith('rawchaptertext:'):
                    title = file_info.split(':', 1)[1]
                    print(f"[{completed_count}/{len(files)}] 已处理章节: {title}")
                else:
                    print(f"[{completed_count}/{len(files)}] 已处理文件: {file_info}")
            except Exception as exc:
                completed_count += 1
                file_info = files[index]
                print(f"[{completed_count}/{len(files)}] 处理文件 {file_info} 时出错: {exc}")
                combined_parts[index] = f'<!-- Error processing {file_info}: {exc} -->\n'
    
    # 并行复制图片
    if all_copy_tasks:
        # 去重复制任务
        unique_copy_tasks = list(set(all_copy_tasks))
        print(f"开始并行复制 {len(unique_copy_tasks)} 个图片文件...")
        
        # 使用更少的进程数来复制图片（通常是 I/O 密集型）
        copy_workers = min(4, multiprocessing.cpu_count())
        
        with ProcessPoolExecutor(max_workers=copy_workers) as executor:
            futures = {executor.submit(copy_single_image, task): task for task in unique_copy_tasks}
            
            success_count = 0
            for i, future in enumerate(as_completed(futures)):
                success, result = future.result()
                if success:
                    success_count += 1
                else:
                    print(f"复制失败: {result}")
                if (i + 1) % 10 == 0:  # 每10个文件报告一次进度
                    print(f"[{i + 1}/{len(unique_copy_tasks)}] 图片复制进度")
            
            print(f"图片复制完成: {success_count}/{len(unique_copy_tasks)} 成功")
    
    # 按原始顺序组合结果
    combined = ''.join(combined_parts)
    
    with open(out_html, 'w', encoding='utf-8') as wf:
        wf.write(combined)
    print(f'Combined HTML saved to {out_html}')


def generate_epub_with_ebooklib(html_file: str, start_html: str, output_epub: str):
    """使用 EbookLib 从 HTML 生成 EPUB，包含 start.html 和 CSS"""
    # 延迟导入，避免在子进程中导入
    from ebooklib import epub
    from bs4 import BeautifulSoup
    
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
    # 延迟导入 weasyprint，避免在子进程中导入
    from weasyprint import HTML
    from weasyprint.text.fonts import FontConfiguration
    
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
