import os
import shutil
from weasyprint import HTML
from weasyprint.text.fonts import FontConfiguration
import re
import argparse
import mistune
from pygments import highlight
from pygments.lexers import get_lexer_by_name
from pygments.formatters import html as pygments_html_formatter
from urllib.parse import urlparse

# 获取当前工作目录的绝对路径
BASE_DIR = os.path.abspath(os.getcwd())

# 创建或清空 build 目录
def prepare_build_dir(build_dir):
    if os.path.exists(build_dir):
        shutil.rmtree(build_dir)
    os.makedirs(build_dir)

# 读取 Markdown 文件内容
def read_markdown_file(filename):
    with open(filename, 'r', encoding='utf-8') as file:
        return file.read()

# 转换 Markdown 中的本地图片路径为绝对路径
def convert_local_images(html_content, docdir):
    def replace_src(match):
        img_src = match.group(1)
        parsed_url = urlparse(img_src)

        # 只有当路径不是 http 或 https 时才转换
        if not parsed_url.scheme:
            # 处理相对路径，转换为绝对路径
            abs_path = os.path.abspath(os.path.join(docdir, img_src))
            return f'src="file://{abs_path}"'
        return match.group(0)

    # 处理图片路径 (src="xxx")
    return re.sub(r'src="([^"]+)"', replace_src, html_content)

# 自定义 Markdown 渲染器
class CustomRenderer(mistune.HTMLRenderer):
    def heading(self, text, level, raw=None):
        return f'<h{level + 1}>{text}</h{level + 1}>'

    def block_code(self, code, info=None):
        if info:
            try:
                lexer = get_lexer_by_name(info.strip(), stripall=True)
            except Exception:
                lexer = get_lexer_by_name('text', stripall=True)
        else:
            lexer = get_lexer_by_name('text', stripall=True)
        formatter = pygments_html_formatter.HtmlFormatter()
        return highlight(code, lexer, formatter)

    def strikethrough(self, text):
        return f'<del>{text}</del>'  # 处理删除线标记

# Markdown 转 HTML
def markdown_to_html(markdown_text, docdir):
    renderer = CustomRenderer(escape=False)
    markdown = mistune.create_markdown(renderer=renderer, plugins=['table', 'strikethrough'])  # 启用 strikethrough 插件
    html_output = markdown(markdown_text)
    return convert_local_images(html_output, docdir)

# 组合 Markdown 文件为 HTML
def combine_markdown_to_html(docdir, input_files, output_file):
    combined_html = ''

    for file in input_files:
        if file.startswith('rawchaptertext:'):
            chaptername = file.replace('rawchaptertext:', '')
            html_output = f'<h1>{chaptername}</h1>\n'
        else:
            markdown_text = read_markdown_file(os.path.join(docdir, file))
            print(f'Converting {file}')
            html_output = markdown_to_html(markdown_text, docdir)

        combined_html += html_output + '\n'

    with open(output_file, 'w', encoding='utf-8') as file:
        file.write(combined_html)

    print(f'Combined HTML saved to {output_file}')

# 主函数
def main(docdir):
    build_dir = 'build'
    prepare_build_dir(build_dir)

    with open(os.path.join(docdir, 'SUMMARY.md'), 'r', encoding='utf-8') as file:
        content = file.read()

    summary_content = re.sub(r'## (.+?)$', r'[\1](rawchaptertext:\1)', content, flags=re.MULTILINE)

    with open(f'{build_dir}/summary.md', 'w', encoding='utf-8') as file:
        file.write(summary_content)

    file_paths = re.findall(r'\[.*?\]\((.*?)\)', summary_content)

    output_file = f'{build_dir}/xxx.html'
    combine_markdown_to_html(docdir, file_paths, output_file)

    with open('start.html', 'r', encoding='utf-8') as f1, \
         open(f'{build_dir}/xxx.html', 'r', encoding='utf-8') as f2, \
         open('end.html', 'r', encoding='utf-8') as f3:
        merged_content = f1.read() + '\n' + f2.read() + '\n' + f3.read()

    final_html = f'{build_dir}/final.html'
    with open(final_html, 'w', encoding='utf-8') as f:
        f.write(merged_content)

    print(f'合并文件成功，结果保存在 {final_html}')
    print('转换成 PDF，时间较长，耐心等待')

    font_config = FontConfiguration()
    HTML(final_html).write_pdf(f'{build_dir}/final.pdf')

    print(f'转换完成，最终文件 {build_dir}/final.pdf')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Document root directory')
    parser.add_argument('docdir', type=str, help='Path to the document root directory')
    args = parser.parse_args()
    main(args.docdir)
