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

BASE_DIR = os.path.abspath(os.getcwd())

def prepare_build_dir(build_dir):
    if os.path.exists(build_dir):
        shutil.rmtree(build_dir)
    os.makedirs(build_dir)

def read_markdown_file(filename):
    with open(filename, 'r', encoding='utf-8') as file:
        return file.read()

def convert_local_images(html_content, docdir):
    def replace_src(match):
        img_src = match.group(1)
        parsed_url = urlparse(img_src)
        if not parsed_url.scheme:
            # 处理相对于当前Markdown文件的路径
            abs_path = os.path.abspath(os.path.join(docdir, img_src))
            # 转换Windows路径分隔符为URL格式
            abs_path = abs_path.replace('\\', '/')
            return f'src="file://{abs_path}"'
        return match.group(0)

    return re.sub(r'src="([^"]+)"', replace_src, html_content)

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
        return f'<del>{text}</del>'

def markdown_to_html(markdown_text, docdir):
    renderer = CustomRenderer(escape=False)
    markdown = mistune.create_markdown(renderer=renderer, plugins=['table', 'strikethrough'])
    html_output = markdown(markdown_text)
    return convert_local_images(html_output, docdir)

def combine_markdown_to_html(docdir, input_files, output_file):
    combined_html = ''

    for file in input_files:
        if file.startswith('rawchaptertext:'):
            chaptername = file.replace('rawchaptertext:', '')
            html_output = f'<h1>{chaptername}</h1>\n'
            combined_html += html_output
            continue

        file_path = os.path.join(docdir, file)
        if not os.path.exists(file_path):
            print(f'Warning: File {file_path} does not exist, skipping')
            continue

        # 获取当前Markdown文件的所在目录
        file_dir = os.path.dirname(file_path)
        markdown_text = read_markdown_file(file_path)
        print(f'Converting {file}')
        html_output = markdown_to_html(markdown_text, file_dir)
        combined_html += html_output + '\n'

    with open(output_file, 'w', encoding='utf-8') as file:
        file.write(combined_html)
    print(f'Combined HTML saved to {output_file}')

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
