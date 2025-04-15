import os
import shutil
import re
import argparse
import hashlib
from urllib.parse import urlparse, unquote
from pathlib import Path
from weasyprint import HTML
from weasyprint.text.fonts import FontConfiguration
import mistune
from pygments import highlight
from pygments.lexers import get_lexer_by_name
from pygments.formatters import html as pygments_html_formatter

# 常量定义
BUILD_DIR = 'build'
SUMMARY_FILE = 'SUMMARY.md'
START_HTML = 'start.html'
FINAL_HTML = 'final.html'
FINAL_PDF = 'final.pdf'
IMAGES_DIR = os.path.join(BUILD_DIR, 'images')

def prepare_build_dir(build_dir: str) -> None:
    """准备构建目录，清理旧文件"""
    if os.path.exists(build_dir):
        shutil.rmtree(build_dir)
    os.makedirs(build_dir)
    # 创建 images 目录用于存放转换文件名后的图片
    os.makedirs(IMAGES_DIR, exist_ok=True)

def read_markdown_file(filename: str) -> str:
    """读取Markdown文件内容"""
    with open(filename, 'r', encoding='utf-8') as file:
        return file.read()

def convert_local_paths(html_content: str, docdir: str) -> str:
    """处理本地图片路径和链接路径
       当图片文件名（不含扩展名）包含非英文和非数字字符时，
       转换为哈希值，并复制到构建目录下的 images 文件夹中。
       对传入的路径先进行 URL 解码，从而避免因编码问题找不到文件
    """
    def replace_src(match):
        attr_value = match.group(1)
        # 先对路径进行 URL 解码
        decoded_attr_value = unquote(attr_value)
        parsed_url = urlparse(decoded_attr_value)
        # 仅处理本地路径（无 scheme）
        if not parsed_url.scheme:
            # 处理图片路径
            if match.group(0).startswith('src="'):
                abs_path = os.path.abspath(os.path.join(docdir, decoded_attr_value))
                base_name = os.path.basename(abs_path)
                name, ext = os.path.splitext(base_name)
                # 判断文件名（不含扩展名）是否仅包含英文字母和数字
                if not re.match(r'^[A-Za-z0-9]+$', name):
                    # 转换为 MD5 哈希值作为新的文件名
                    hash_val = hashlib.md5(name.encode('utf-8')).hexdigest()
                    new_file_name = hash_val + ext
                    new_file_path = os.path.join(IMAGES_DIR, new_file_name)
                    try:
                        shutil.copy(abs_path, new_file_path)
                    except Exception as e:
                        print(f'Error copying {abs_path} to {new_file_path}: {e}')
                    file_url = Path(new_file_path).resolve().as_uri()
                    return f'src="{file_url}"'
                # 如果文件名仅包含英文字母和数字，直接生成文件 URL
                file_url = Path(abs_path).resolve().as_uri()
                return f'src="{file_url}"'
            # 处理文档链接
            elif match.group(0).startswith('href="'):
                if decoded_attr_value.endswith('.md'):
                    anchor = os.path.splitext(decoded_attr_value)[0]
                    return f'href="#{anchor}"'
                elif '.md#' in decoded_attr_value:
                    return f'href="#{decoded_attr_value.split("#")[1]}"'
        return match.group(0)
    
    html_content = re.sub(r'src="([^"]+)"', replace_src, html_content)
    html_content = re.sub(r'href="([^"]+)"', replace_src, html_content)
    return html_content

class CustomRenderer(mistune.HTMLRenderer):
    """自定义Markdown渲染器"""
    
    def heading(self, text: str, level: int, raw: str = None) -> str:
        """为标题添加锚点"""
        anchor_id = re.sub(r'[^\w]+', '-', text.lower()).strip('-')
        return f'<h{level + 1} id="{anchor_id}">{text}</h{level + 1}>'
    
    def block_code(self, code: str, info: str = None) -> str:
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
    
    def strikethrough(self, text: str) -> str:
        """删除线语法支持"""
        return f'<del>{text}</del>'
    
    def list_item(self, text: str) -> str:
        """处理任务列表项（[x] 或 [ ]）"""
        checkbox_pattern = re.compile(r'^\s*\[([ xX?]?)\]\s+')
        match = checkbox_pattern.match(text)
        if match:
            checked = 'checked' if match.group(1).strip().lower() == 'x' else ''
            text = text[match.end():].lstrip()
            return f'<li><input type="checkbox" disabled {checked}> {text}</li>'
        return super().list_item(text)

def markdown_to_html(markdown_text: str, docdir: str) -> str:
    """将Markdown转换为HTML"""
    renderer = CustomRenderer(escape=False)
    markdown = mistune.create_markdown(
        renderer=renderer,
        plugins=['table', 'strikethrough']
    )
    html_output = markdown(markdown_text)
    return convert_local_paths(html_output, docdir)

def combine_markdown_to_html(docdir: str, input_files: list, output_file: str) -> None:
    """合并多个Markdown文件为单个HTML"""
    combined_html = ''
    
    for file in input_files:
        if file.startswith('rawchaptertext:'):
            chaptername = file.replace('rawchaptertext:', '')
            anchor_id = re.sub(r'[^\w]+', '-', chaptername.lower()).strip('-')
            combined_html += f'<a id="{anchor_id}"></a>\n<h1>{chaptername}</h1>\n'
            continue
            
        file_path = os.path.join(docdir, file)
        if not os.path.exists(file_path):
            print(f'Warning: File {file_path} does not exist, skipping')
            continue

        # 添加基于文件名的锚点
        anchor_id = os.path.splitext(file)[0]
        combined_html += f'<a id="{anchor_id}"></a>\n'
            
        file_dir = os.path.dirname(file_path)
        markdown_text = read_markdown_file(file_path)
        html_output = markdown_to_html(markdown_text, file_dir)
        combined_html += html_output + '\n'
    
    with open(output_file, 'w', encoding='utf-8') as file:
        file.write(combined_html)
    print(f'Combined HTML saved to {output_file}')

def main(docdir: str) -> None:
    """主处理流程"""
    prepare_build_dir(BUILD_DIR)
    
    # 处理 SUMMARY.md
    summary_path = os.path.join(docdir, SUMMARY_FILE)
    with open(summary_path, 'r', encoding='utf-8') as file:
        content = file.read()
    
    # 将二级标题转换为伪章节
    summary_content = re.sub(
        r'## (.+?)$',
        r'[\1](rawchaptertext:\1)',
        content,
        flags=re.MULTILINE
    )
    
    # 生成中间 summary.md
    summary_build_path = os.path.join(BUILD_DIR, 'summary.md')
    with open(summary_build_path, 'w', encoding='utf-8') as file:
        file.write(summary_content)
    
    # 提取文件路径列表
    file_paths = re.findall(r'\[.*?\]\((.*?)\)', summary_content)
    
    # 生成中间 HTML
    output_file = os.path.join(BUILD_DIR, 'combined.html')
    combine_markdown_to_html(docdir, file_paths, output_file)
    
    # 合并 start.html 和 combined.html
    with open(START_HTML, 'r', encoding='utf-8') as f1, \
         open(output_file, 'r', encoding='utf-8') as f2:
        merged_content = f1.read() + '\n' + f2.read()
    
    final_html_path = os.path.join(BUILD_DIR, FINAL_HTML)
    with open(final_html_path, 'w', encoding='utf-8') as f:
        f.write(merged_content)
    print(f'Merged HTML saved to {final_html_path}')
    
    # 生成 PDF 2.0
    print('Generating PDF (this may take a while)...')
    font_config = FontConfiguration()
    HTML(final_html_path).write_pdf(
        os.path.join(BUILD_DIR, FINAL_PDF),
        font_config=font_config,
        full_fonts=True,
        pdf_version="2.0",     # 指定PDF版本为2.0
        pdf_variant="pdf/a-4u", # 测试 pdf/a-4u
        metadata=True,
    )
    print(f'PDF generated: {os.path.join(BUILD_DIR, FINAL_PDF)}')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Generate PDF from Markdown documents')
    parser.add_argument('docdir', type=str, help='Document root directory')
    args = parser.parse_args()
    main(args.docdir)
