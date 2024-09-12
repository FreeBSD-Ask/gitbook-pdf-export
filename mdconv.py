from weasyprint import HTML
from weasyprint.text.fonts import FontConfiguration
import re
import argparse
import mistune
import os


# 读取 Markdown 文件内容
def read_markdown_file(filename):
    try:
        with open(filename, 'r', encoding='utf-8') as file:
            return file.read()
    except FileNotFoundError:
        print(f"File not found: {filename}")
        return ""
    except Exception as e:
        print(f"Error reading file {filename}: {e}")
        return ""


# 自定义渲染器，将标题级别降一级
class CustomRenderer(mistune.HTMLRenderer):
    def heading(self, text, level, raw=None):
        # 将所有标题级别降一级
        new_level = level + 1
        return f'<h{new_level}>{text}</h{new_level}>'


# Markdown 转 HTML，标题级别降一级
def markdown_to_html(markdown_text):
    renderer = CustomRenderer(escape=False)
    markdown = mistune.create_markdown(renderer=renderer, plugins=['table'])
    return markdown(markdown_text)


# 原始 Markdown 转 HTML
def markdown_to_html_origin(markdown_text):
    return mistune.html(markdown_text)


# 合并多个 Markdown 文件并转换为 HTML
def combine_markdown_to_html(docdir, input_files, output_file):
    combined_html = []
    raw_pattern = re.compile(r'rawchaptertext:')

    for file in input_files:
        if raw_pattern.search(file):
            chaptername = raw_pattern.sub('', file)
            print(f'Processing chapter name: {chaptername}')
            html_output = f'<h1>{chaptername}</h1>'
        else:
            markdown_text = read_markdown_file(os.path.join(docdir, file))
            if markdown_text:
                print(f'Converting {file}')
                if '/' in file:
                    html_output = markdown_to_html(markdown_text)
                else:
                    html_output = markdown_to_html_origin(markdown_text)
            else:
                html_output = ''
        combined_html.append(html_output)

    # 写入合并后的 HTML 到输出文件
    try:
        with open(output_file, 'w', encoding='utf-8') as file:
            file.write('\n'.join(combined_html))
        print(f'合并的 HTML 已经存储 {output_file}')
    except Exception as e:
        print(f"合并时发生错误 HTML: {e}")


# 主函数
def main(docdir):
    # 读取并处理 SUMMARY.md 文件内容
    summary_file = os.path.join(docdir, 'SUMMARY.md')
    try:
        with open(summary_file, 'r', encoding='utf-8') as file:
            content = file.read()
    except FileNotFoundError:
        print(f"SUMMARY.md 不存在于 {docdir}")
        return
    except Exception as e:
        print(f"SUMMARY.md 读取错误: {e}")
        return

    # 修改 SUMMARY.md 内容
    summary_content = re.sub(r'## (.+?)$', r'[\1](rawchaptertext:\1)', content, flags=re.MULTILINE)

    # 将修改后的内容写入新文件
    os.makedirs('build', exist_ok=True)
    try:
        with open('build/summary.md', 'w', encoding='utf-8') as file:
            file.write(summary_content)
    except Exception as e:
        print(f"写入构建/summary.md 错误: {e}")
        return

    # 找到所有 Markdown 文件的链接
    file_paths = re.findall(r'\[.*?\](.*?)', summary_content)

    # 合并 Markdown 文件并生成 HTML
    output_file = 'build/xxx.html'
    combine_markdown_to_html(docdir, file_paths, output_file)

    # 合并额外的 HTML 片段
    try:
        with open('start.html', 'r', encoding='utf-8') as f1, \
                open(output_file, 'r', encoding='utf-8') as f2, \
                open('end.html', 'r', encoding='utf-8') as f3:
            merged_content = f1.read() + '\n' + f2.read() + '\n' + f3.read()
        
        final_output = 'build/final.html'
        with open(final_output, 'w', encoding='utf-8') as f:
            f.write(merged_content)
        print(f"文件合并成功 Result saved in {final_output}")
    except FileNotFoundError as e:
        print(f"合并时未发现文件: {e}")
        return
    except Exception as e:
        print(f"合并文件时发生错误: {e}")
        return

    # 转换 HTML 为 PDF
    try:
        font_config = FontConfiguration()
        HTML(final_output).write_pdf('build/final.pdf', font_config=font_config)
        print('PDF 转换完成，最终文件: build/final.pdf')
    except Exception as e:
        print(f"PDF 转换出错: {e}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Document root directory')
    parser.add_argument('docdir', type=str, help='Path to the document root directory')
    args = parser.parse_args()
    main(args.docdir)