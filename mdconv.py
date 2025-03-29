import os
import shutil
import re
import argparse
from concurrent.futures import ThreadPoolExecutor
from weasyprint import HTML
from weasyprint.text.fonts import FontConfiguration
import mistune
from pygments import highlight
from pygments.lexers import get_lexer_by_name
from pygments.formatters import html as pygments_html_formatter
from urllib.parse import urlparse
import threading

# 线程本地存储 mistune 渲染器
thread_local = threading.local()

# 基础目录设置
BASE_DIR = os.path.abspath(os.getcwd())

def prepare_build_dir(build_dir):
    """准备构建目录，清理旧文件"""
    if os.path.exists(build_dir):
        shutil.rmtree(build_dir)
    os.makedirs(build_dir)

def read_markdown_file(filename):
    """读取Markdown文件内容"""
    with open(filename, 'r', encoding='utf-8') as file:
        return file.read()

def convert_local_images(html_content, docdir):
    """将本地图片路径转换为绝对路径"""
    def replace_src(match):
        img_src = match.group(1)
        parsed_url = urlparse(img_src)
        if not parsed_url.scheme:
            abs_path = os.path.abspath(os.path.join(docdir, img_src))
            return f'src="file://{abs_path.replace("\\", "/")}"'
        return match.group(0)
    
    return re.sub(r'src="([^"]+)"', replace_src, html_content)

class CustomRenderer(mistune.HTMLRenderer):
    """自定义Markdown渲染器"""
    
    def heading(self, text, level, raw=None):
        """调整标题层级（+1）"""
        return f'<h{level + 1}>{text}</h{level + 1}>'
    
    def block_code(self, code, info=None):
        """代码块高亮处理"""
        lexer = get_lexer_by_name(info.strip(), stripall=True) if info else get_lexer_by_name('text', stripall=True)
        formatter = pygments_html_formatter.HtmlFormatter()
        return highlight(code, lexer, formatter)
    
    def strikethrough(self, text):
        """删除线语法支持"""
        return f'<del>{text}</del>'
    
    def list_item(self, text):
        """处理任务列表项（[x] 或 [ ]）"""
        checkbox_pattern = re.compile(r'^\s*\[([ xX]?)\]\s+')
        match = checkbox_pattern.match(text)
        if match:
            checked = 'checked' if match.group(1).strip().lower() == 'x' else ''
            text = text[match.end():].lstrip()
            return f'<li><input type="checkbox" disabled {checked}> {text}</li>'
        return super().list_item(text)

def get_markdown_renderer():
    """确保每个线程都有自己的 mistune 渲染器"""
    if not hasattr(thread_local, 'renderer'):
        thread_local.renderer = CustomRenderer(escape=False)
        thread_local.markdown = mistune.create_markdown(
            renderer=thread_local.renderer,
            plugins=['table', 'strikethrough']
        )
    return thread_local.markdown

def markdown_to_html(markdown_text, docdir):
    """将Markdown转换为HTML"""
    markdown = get_markdown_renderer()
    html_output = markdown(markdown_text)
    return convert_local_images(html_output, docdir)

def process_markdown_file(file, docdir):
    """处理单个Markdown文件"""
    if file.startswith('rawchaptertext:'):
        chaptername = file.replace('rawchaptertext:', '')
        return f'<h1>{chaptername}</h1>'
    file_path = os.path.join(docdir, file)
    if not os.path.exists(file_path):
        print(f'Warning: File {file_path} does not exist, skipping')
        return ''
    print(f'Converting {file}')
    markdown_text = read_markdown_file(file_path)
    return markdown_to_html(markdown_text, os.path.dirname(file_path))

def combine_markdown_to_html(docdir, input_files, output_file):
    """合并多个Markdown文件为单个HTML，使用线程池并行处理"""
    with ThreadPoolExecutor() as executor:
        html_parts = list(executor.map(lambda file: process_markdown_file(file, docdir), input_files))
    combined_html = '\n'.join(html_parts)
    with open(output_file, 'w', encoding='utf-8') as file:
        file.write(combined_html)
    print(f'Combined HTML saved to {output_file}')

def main(docdir):
    """主处理流程"""
    build_dir = 'build'
    prepare_build_dir(build_dir)
    
    with open(os.path.join(docdir, 'SUMMARY.md'), 'r', encoding='utf-8') as file:
        content = file.read()
    
    summary_content = re.sub(r'## (.+?)$', r'[\1](rawchaptertext:\1)', content, flags=re.MULTILINE)
    with open(f'{build_dir}/summary.md', 'w', encoding='utf-8') as file:
        file.write(summary_content)
    
    file_paths = re.findall(r'\[.*?\]\((.*?)\)', summary_content)
    output_file = f'{build_dir}/combined.html'
    combine_markdown_to_html(docdir, file_paths, output_file)
    
    with open('start.html', 'r', encoding='utf-8') as f1, \
         open(output_file, 'r', encoding='utf-8') as f2, \
         open('end.html', 'r', encoding='utf-8') as f3:
        merged_content = f1.read() + '\n' + f2.read() + '\n' + f3.read()
    
    final_html = f'{build_dir}/final.html'
    with open(final_html, 'w', encoding='utf-8') as f:
        f.write(merged_content)
    print(f'Merged HTML saved to {final_html}')
    
    print('Generating PDF...')
    font_config = FontConfiguration()
    HTML(final_html).write_pdf(f'{build_dir}/final.pdf', font_config=font_config)
    print(f'PDF generated: {build_dir}/final.pdf')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Generate PDF from Markdown documents')
    parser.add_argument('docdir', type=str, help='Document root directory')
    args = parser.parse_args()
    main(args.docdir)
