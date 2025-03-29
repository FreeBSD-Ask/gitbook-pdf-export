import os
import shutil
import re
import argparse
from weasyprint import HTML
from weasyprint.text.fonts import FontConfiguration
import mistune
from pygments import highlight
from pygments.lexers import get_lexer_by_name
from pygments.formatters import html as pygments_html_formatter
from urllib.parse import urlparse

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
        if not parsed_url.scheme:  # 处理本地路径
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
        """删除线语法支持"""
        return f'<del>{text}</del>'
    
    def list_item(self, text):
        """处理任务列表项（[x] 或 [ ]）"""
        # 严格匹配以 [x]/[ ] 开头且后跟空格的语法
        checkbox_pattern = re.compile(r'^\s*\[([ xX]?)\]\s+')
        match = checkbox_pattern.match(text)
        if match:
            # 提取复选框状态
            checked = 'checked' if match.group(1).strip().lower() == 'x' else ''
            # 移除复选框标记并保留内容
            text = text[match.end():].lstrip()
            return f'<li><input type="checkbox" disabled {checked}> {text}</li>'
        # 普通列表项使用默认处理
        return super().list_item(text)

def markdown_to_html(markdown_text, docdir):
    """将Markdown转换为HTML"""
    renderer = CustomRenderer(escape=False)
    # 启用表格和删除线插件
    markdown = mistune.create_markdown(
        renderer=renderer,
        plugins=['table', 'strikethrough']
    )
    html_output = markdown(markdown_text)
    return convert_local_images(html_output, docdir)

def combine_markdown_to_html(docdir, input_files, output_file):
    """合并多个Markdown文件为单个HTML"""
    combined_html = ''
    
    for file in input_files:
        if file.startswith('rawchaptertext:'):
            # 处理原始章节文本
            chaptername = file.replace('rawchaptertext:', '')
            combined_html += f'<h1>{chaptername}</h1>\n'
            continue
            
        file_path = os.path.join(docdir, file)
        if not os.path.exists(file_path):
            print(f'Warning: File {file_path} does not exist, skipping')
            continue
            
        # 获取文件所在目录用于图片路径处理
        file_dir = os.path.dirname(file_path)
        markdown_text = read_markdown_file(file_path)
        print(f'Converting {file}')
        html_output = markdown_to_html(markdown_text, file_dir)
        combined_html += html_output + '\n'
    
    with open(output_file, 'w', encoding='utf-8') as file:
        file.write(combined_html)
    print(f'Combined HTML saved to {output_file}')

def main(docdir):
    """主处理流程"""
    build_dir = 'build'
    prepare_build_dir(build_dir)
    
    # 处理SUMMARY.md
    with open(os.path.join(docdir, 'SUMMARY.md'), 'r', encoding='utf-8') as file:
        content = file.read()
    
    # 将二级标题转换为伪章节
    summary_content = re.sub(
        r'## (.+?)$',
        r'[\1](rawchaptertext:\1)',
        content,
        flags=re.MULTILINE
    )
    
    # 生成中间summary.md
    with open(f'{build_dir}/summary.md', 'w', encoding='utf-8') as file:
        file.write(summary_content)
    
    # 提取文件路径列表
    file_paths = re.findall(r'\[.*?\]\((.*?)\)', summary_content)
    
    # 生成中间HTML
    output_file = f'{build_dir}/combined.html'
    combine_markdown_to_html(docdir, file_paths, output_file)
    
    # 合并头尾HTML
    with open('start.html', 'r', encoding='utf-8') as f1, \
         open(output_file, 'r', encoding='utf-8') as f2, \
         open('end.html', 'r', encoding='utf-8') as f3:
        merged_content = f1.read() + '\n' + f2.read() + '\n' + f3.read()
    
    final_html = f'{build_dir}/final.html'
    with open(final_html, 'w', encoding='utf-8') as f:
        f.write(merged_content)
    print(f'Merged HTML saved to {final_html}')
    
    # 生成PDF
    print('Generating PDF (this may take a while)...')
    font_config = FontConfiguration()
    HTML(final_html).write_pdf(
        f'{build_dir}/final.pdf',
        font_config=font_config
    )
    print(f'PDF generated: {build_dir}/final.pdf')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Generate PDF from Markdown documents')
    parser.add_argument('docdir', type=str, help='Document root directory')
    args = parser.parse_args()
    main(args.docdir)
