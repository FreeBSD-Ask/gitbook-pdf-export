#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""下载 EPUBCheck 并对给定 EPUB 执行合规校验（CI 与本地复检共用）。

EPUBCheck 是 W3C 官方的 EPUB 一致性检查器，zip 发行包从 GitHub Releases
下载并缓存；文本/XML 报告中出现 error 级问题即以非零码退出，warning 放行。

用法：python tests/epubcheck_cli.py <epub路径> [--severity warning]
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile

EPUBCHECK_VERSION = '5.2.1'
RELEASE_URL = ('https://github.com/w3c/epubcheck/releases/download/'
               'v{0}/epubcheck-{0}.zip').format(EPUBCHECK_VERSION)


def cache_dir():
    """发行包与解压结果统一缓存在系统临时目录的 epubcheck/ 下"""
    d = os.path.join(tempfile.gettempdir(), 'epubcheck')
    os.makedirs(d, exist_ok=True)
    return d


def ensure_epubcheck():
    """下载并解压发行包，返回 epubcheck.jar 的路径"""
    root = cache_dir()
    jar = os.path.join(root, 'epubcheck-' + EPUBCHECK_VERSION,
                       'epubcheck.jar')
    if os.path.exists(jar):
        return jar
    dest = os.path.join(root, 'epubcheck-' + EPUBCHECK_VERSION + '.zip')
    if not (os.path.exists(dest) and os.path.getsize(dest) > 1024 * 1024):
        print('Downloading', RELEASE_URL, flush=True)
        tmp = dest + '.part'
        last_err = None
        for attempt in range(3):
            try:
                req = urllib.request.Request(RELEASE_URL)
                with urllib.request.urlopen(req, timeout=1200) as resp, \
                        open(tmp, 'wb') as f:
                    shutil.copyfileobj(resp, f)
                os.replace(tmp, dest)
                break
            except OSError as err:
                last_err = err
                print('Download attempt %d failed: %s' % (attempt + 1, err),
                      flush=True)
                time.sleep(5)
        else:
            raise RuntimeError('EPUBCheck 下载失败: %s' % last_err)
    with zipfile.ZipFile(dest) as z:
        z.extractall(root)
    if not os.path.exists(jar):
        raise RuntimeError('解压后未找到 epubcheck.jar，缓存目录: ' + root)
    return jar


def validate(epub_path, severity='error'):
    """运行 EPUBCheck；error 级问题返回 1，warning 仅在显式要求时计入

    发行 zip 中的 epubcheck.jar 是含依赖的 fat jar，官方脚本即
    java -jar 方式启动。
    """
    jar = ensure_epubcheck()
    cmd = ['java', '-jar', jar, '--severity', severity,
           os.path.abspath(epub_path)]
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          encoding='utf-8', errors='replace', timeout=1200)
    report = (proc.stdout or '') + (proc.stderr or '')
    print(report, flush=True)
    # EPUBCheck：有 error 或 fatal 时退出码非 0
    if proc.returncode != 0:
        print('EPUB 校验未通过 (' + epub_path + ')', file=sys.stderr)
        return 1
    print('EPUB 校验通过 (' + epub_path + ')')
    return 0


def main():
    parser = argparse.ArgumentParser(
        description='对给定 EPUB 执行 EPUBCheck 校验')
    parser.add_argument('epub', help='待校验的 EPUB 文件路径')
    parser.add_argument('--severity', default='error',
                        help='计入退出码的最低级别（默认 error）')
    args = parser.parse_args()
    sys.exit(validate(args.epub, args.severity))


if __name__ == '__main__':
    main()
