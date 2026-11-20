#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""构建用于 CI 中 veraPDF 校验的最小 PDF/A 样本。

复用回归测试的 BuildFixture（中文标题、跨章内部链接、同名图片），
保证 CI 校验的对象与单元测试覆盖的是同一种文档结构；
构建目录位于仓库内时，start.html 的 ../fonts 才能解析到待嵌入字体。

用法：python tests/build_pdfa_sample.py <build_dir>
"""

import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
# 脚本可从任意工作目录运行：仓库根提供 mdconv，tests 目录提供 BuildFixture
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import mdconv
from test_mdconv import BuildFixture


def main():
    build_dir = sys.argv[1] if len(sys.argv) > 1 else 'pdfa-sample'
    docdir = tempfile.mkdtemp(prefix='pdfa-sample-doc-')
    try:
        BuildFixture(docdir)
        mdconv.main(docdir, build_dir=build_dir, make_pdf=True,
                    make_epub=False, make_docx=False,
                    formulas_enabled=False, title='PDF/A-4U sample')
    finally:
        shutil.rmtree(docdir, ignore_errors=True)


if __name__ == '__main__':
    main()
