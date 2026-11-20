#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""下载 veraPDF CLI 并对给定 PDF 执行 PDF/A 校验（CI 与本地复检共用）。

安装包从 software.verapdf.org 下载（固定版本，保证校验结果可复现），
缓存到系统临时目录后从中提取 CLI fat jar，再以 -f 指定的 flavour 校验；
文本报告首行为 PASSED/FAILED，不合规时以非零码退出。

用法：python tests/verapdf_cli.py <pdf路径> [-f 4]
"""

import argparse
import io
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile

# 固定版本号：/rel 指向最新版会随上游发版漂移，导致校验结果不可复现
VERAPDF_VERSION = '1.30.4'
# 下载目录按 major.minor 划分（1.30.4 的安装包位于 releases/1.30/ 下）
_RELEASE_DIR = '.'.join(VERAPDF_VERSION.split('.')[:2])
INSTALLER_URL = ('https://software.verapdf.org/releases/{0}/'
                 'verapdf-greenfield-{1}-installer.zip').format(
                     _RELEASE_DIR, VERAPDF_VERSION)
# 安装器为 IzPack 结构，CLI fat jar 位于 resources/packs/pack-veraPDF CLI
CLI_PACK_SUFFIX = 'pack-veraPDF CLI'
CLI_MAIN_CLASS = 'org.verapdf.apps.GreenfieldCliWrapper'


def cache_dir():
    """安装包与提取出的 jar 统一缓存复用

    默认放在系统临时目录；CI 通过 VERAPDF_CLI_CACHE 指向工作区内的
    持久路径，配合 actions/cache 免去每次构建重新下载 33MB 安装包。
    """
    d = os.environ.get('VERAPDF_CLI_CACHE') or os.path.join(
        tempfile.gettempdir(), 'verapdf-cli')
    os.makedirs(d, exist_ok=True)
    return d


def download_installer(dest):
    """下载安装包，失败时重试两次"""
    print('Downloading', INSTALLER_URL, flush=True)
    tmp = dest + '.part'
    last_err = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(INSTALLER_URL)
            with urllib.request.urlopen(req, timeout=1800) as resp, \
                    open(tmp, 'wb') as f:
                shutil.copyfileobj(resp, f)
            os.replace(tmp, dest)
            print('Installer saved to', dest, flush=True)
            return
        except OSError as err:
            last_err = err
            print('Download attempt %d failed: %s' % (attempt + 1, err),
                  flush=True)
            time.sleep(5)
    raise RuntimeError('安装包下载失败: %s' % last_err)


def ensure_installer():
    path = os.path.join(cache_dir(), 'verapdf-installer-' + VERAPDF_VERSION + '.zip')
    if not (os.path.exists(path) and os.path.getsize(path) > 1024 * 1024):
        download_installer(path)
    return path


def ensure_cli_jar(installer):
    """从安装包提取 CLI fat jar，提取结果同样缓存复用

    安装包有两种形态：早期版本直接以 IzPack 结构把 pack 放在
    resources/packs/ 下；1.30 起是引导包（verapdf-install 脚本 +
    verapdf-izpack-installer-*.jar），真正的 pack 在内层 jar 中。
    """
    jar = os.path.join(cache_dir(), 'verapdf-cli-' + VERAPDF_VERSION + '.jar')
    if os.path.exists(jar) and os.path.getsize(jar) > 1024 * 1024:
        return jar
    print('Extracting CLI jar from', installer, flush=True)
    with zipfile.ZipFile(installer) as outer:
        names = outer.namelist()
        packs = [n for n in names if n.endswith(CLI_PACK_SUFFIX)]
        if packs:
            data = outer.read(packs[0])
        else:
            inner_jars = [n for n in names if n.endswith('.jar')]
            if not inner_jars:
                raise RuntimeError('安装包结构无法识别，含有的条目: '
                                   + ', '.join(names[:10]))
            with zipfile.ZipFile(io.BytesIO(outer.read(inner_jars[0]))) as iz:
                packs = [n for n in iz.namelist()
                         if n.endswith(CLI_PACK_SUFFIX)]
                if packs:
                    data = iz.read(packs[0])
                else:
                    # 兜底：pack 路径名随版本可能调整，CLI pack 是内层唯一的
                    # 大体积条目（其它条目都是安装器自身的 class/资源）
                    infos = sorted(iz.infolist(),
                                   key=lambda i: i.file_size, reverse=True)
                    if infos and infos[0].file_size > 1024 * 1024:
                        data = iz.read(infos[0])
                    else:
                        raise RuntimeError('安装器内未找到 CLI 包，含有的条目: '
                                           + ', '.join(iz.namelist()[:30]))
    with open(jar + '.part', 'wb') as f:
        f.write(data)
    os.replace(jar + '.part', jar)
    print('CLI jar saved to', jar, flush=True)
    return jar


def validate(pdf_path, flavour, jar):
    """运行 veraPDF 并按文本报告首行判定合规性

    文本报告首行为 PASS / FAIL（旧版为 PASSED），后接文件路径与 flavour。
    """
    cmd = ['java', '-cp', jar, CLI_MAIN_CLASS,
           '-f', flavour, '--format', 'text', os.path.abspath(pdf_path)]
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          encoding='utf-8', errors='replace', timeout=900)
    report = (proc.stdout or '') + (proc.stderr or '')
    print(report, flush=True)
    lines = [ln for ln in report.splitlines() if ln.strip()]
    first = lines[0] if lines else ''
    verdict = first.split()[0] if first else ''
    if verdict not in ('PASS', 'PASSED'):
        print('PDF/A-' + flavour + ' 校验未通过: ' + first, file=sys.stderr)
        return 1
    print('PDF/A-' + flavour + ' 校验通过 (' + pdf_path + ')')
    return 0


def main():
    parser = argparse.ArgumentParser(
        description='对给定 PDF 执行 veraPDF PDF/A 校验')
    parser.add_argument('pdf', help='待校验的 PDF 文件路径')
    parser.add_argument('-f', '--flavour', default='4',
                        help='校验 flavour（默认 4，即基础 PDF/A-4）')
    args = parser.parse_args()

    installer = ensure_installer()
    jar = ensure_cli_jar(installer)
    sys.exit(validate(args.pdf, args.flavour, jar))


if __name__ == '__main__':
    main()
