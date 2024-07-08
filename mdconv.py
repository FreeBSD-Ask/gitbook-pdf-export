from weasyprint import HTML
from weasyprint.text.fonts import FontConfiguration
import re
import argparse

import mistune

# 读取 Markdown 文件内容
def read_markdown_file(filename):
    with open(filename, 'r', encoding='utf-8') as file:
        markdown_text = file.read()
    return markdown_text

# 将 Markdown 转换为 HTML
class CustomRenderer(mistune.HTMLRenderer):
    def heading(self, text, level, raw=None):
        # 将所有标题级别降一级
        new_level = level + 1
        return f'<h{new_level}>{text}</h{new_level}>'

def markdown_to_html(markdown_text):   # 目录降级
    renderer = CustomRenderer(escape=False)
    markdown = mistune.create_markdown(renderer=renderer,plugins=['table'])
    html_output = markdown(markdown_text)
    return html_output

def markdown_to_html_origin(markdown_text):
    html_output = mistune.html(markdown_text)
    return html_output
# 将多个 Markdown 文件转换为一个 HTML 文件
def combine_markdown_to_html(docdir, input_files, output_file):
    combined_html = ''

    for file in input_files:
        pattern = r'rawchaptertext:'
        if re.search(pattern, file):
            chaptername = re.sub(pattern, '', file)
            print(f'process chapter name {chaptername}')
            html_output = '<h1>' + chaptername + '</h1>' + '\n'
        else:
            markdown_text = read_markdown_file(docdir + '/' + file)
            print(f'converting {file}')
            if '/' in file:
                html_output = markdown_to_html(markdown_text)
            else:
                html_output = markdown_to_html_origin(markdown_text)
        combined_html += html_output + '\n'

    # 写入合并后的 HTML 到输出文件
    with open(output_file, 'w', encoding='utf-8') as file:
        file.write(combined_html)

    print(f'Combined HTML saved to {output_file}')


        
# 主函数
def main(docdir):
# 读取原始文件内容
    with open(docdir + '/SUMMARY.md', 'r', encoding='utf-8') as file:
        content = file.read()
# 定义正则表达式模式
    pattern = r'## (.+?)$'
    replacement = r'[\1](rawchaptertext:\1)'
# 使用 re.sub 进行替换
    summary_content = re.sub(pattern, replacement, content, flags=re.MULTILINE)

# 将修改后的内容写入新文件
    with open('build/summary.md', 'w', encoding='utf-8') as file:
        file.write(summary_content)
# 读取 SUMMARY.md 文件内容
#    with open(docdir + '/SUMMARY.md', 'r', encoding='utf-8') as file:
#        summary_content = file.read()

# 使用正则表达式找到所有 Markdown 文件的链接
    #pattern = r'\* \[.*?\]\((.*?)\)'
    pattern = r'\[.*?\]\((.*?)\)'
    matches = re.findall(pattern, summary_content, re.DOTALL)

# 将匹配到的路径放在一个数组中
    file_paths = [match for match in matches]

# 打印数组内容
    output_file = 'build/xxx.html'  # 输出的 HTML 文件名
    combine_markdown_to_html(docdir, file_paths, output_file)

    with open('start.html', 'r', encoding='utf-8') as f1:
        content1 = f1.read()
    with open('build/xxx.html', 'r', encoding='utf-8') as f2:
        content2 = f2.read()
    with open('end.html', 'r', encoding='utf-8') as f3:
        content3 = f3.read()
    merged_content = content1 + '\n' + content2 + '\n' + content3
    with open('build/final.html', 'w', encoding='utf-8') as f:
        f.write(merged_content)

    print(f"合并文件成功，结果保存在 build/final 中。")
    print('转换成pdf，时间较长，耐心等待')

    font_config = FontConfiguration()
    HTML('build/final.html').write_pdf( 'build/final.pdf')
    print('转换完成，最终文件 build/final.pdf')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='document root dir')
    parser.add_argument('docdir',type=str,help='path to the document root dir')
    args = parser.parse_args()
    main(args.docdir)
