#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mdconv.py 的回归测试

覆盖内部链接转换、同名图片、heading id 去重、EPUB 元数据/目录/链接重映射、
PDF 书签禁用、目录页与公式缓存等核心行为。
"""

import base64
import os
import re
import shutil
import struct
import tempfile
import unittest
import zipfile

import mdconv

try:
    import pypdf
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False


def make_png(path, color=(255, 0, 0)):
    """生成一个最小化的合法 PNG 文件（1x1 像素）"""
    import zlib

    def chunk(tag, data):
        c = struct.pack('>I', len(data)) + tag + data
        return c + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff)

    ihdr = struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)
    raw = zlib.compress(b'\x00' + bytes(color))
    data = (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', ihdr)
            + chunk(b'IDAT', raw)
            + chunk(b'IEND', b''))
    with open(path, 'wb') as f:
        f.write(data)


def outline_titles(pdf_path):
    """递归收集 PDF 书签标题（深度优先）"""
    reader = pypdf.PdfReader(pdf_path)
    titles = []

    def walk(items):
        for item in items:
            if isinstance(item, list):
                walk(item)
            else:
                titles.append(item.title)

    walk(reader.outline)
    return titles


class BuildFixture:
    """构造最小化的 GitBook 文档结构供各测试复用"""

    def __init__(self, root):
        self.root = root
        os.makedirs(os.path.join(root, 'ch1', 'img'), exist_ok=True)
        os.makedirs(os.path.join(root, 'ch2', 'img'), exist_ok=True)

        with open(os.path.join(root, 'SUMMARY.md'), 'w', encoding='utf-8') as f:
            f.write(
                '# Summary\n\n'
                '## 第一章\n\n'
                '* [第一节](ch1/sec1.md)\n'
                '* [第二节](ch2/sec2.md)\n'
            )

        # 第一节：指向第二节的内部链接 + 引用本目录同名图片
        with open(os.path.join(root, 'ch1', 'sec1.md'), 'w', encoding='utf-8') as f:
            f.write(
                '# 第一节\n\n'
                '参见[第二节](../ch2/sec2.md)。\n\n'
                '![图一](img/pic.png)\n'
            )

        # 第二节（位于另一目录）：与第一节同名的标题（id 冲突）+ 不同内容的同名图片
        with open(os.path.join(root, 'ch2', 'sec2.md'), 'w', encoding='utf-8') as f:
            f.write(
                '# 第一节\n\n'
                '重复标题用于测试 id 去重。\n\n'
                '![图二](img/pic.png)\n'
            )

        # 两张同名但内容不同的图片
        make_png(os.path.join(root, 'ch1', 'img', 'pic.png'), (255, 0, 0))
        make_png(os.path.join(root, 'ch2', 'img', 'pic.png'), (0, 255, 0))

        # 封面
        make_png(os.path.join(root, 'book-logo.png'))


class MdconvTest(unittest.TestCase):
    """核心导出流程的端到端测试"""

    @classmethod
    def setUpClass(cls):
        cls.docdir = tempfile.mkdtemp(prefix='mdconv-doc-')
        cls.build = tempfile.mkdtemp(prefix='mdconv-build-')
        cls.cache = tempfile.mkdtemp(prefix='mdconv-cache-')
        # 将公式缓存重定向到临时目录，避免污染用户缓存
        cls._orig_cache = os.environ.get('MDCONV_FORMULA_CACHE')
        os.environ['MDCONV_FORMULA_CACHE'] = cls.cache
        BuildFixture(cls.docdir)
        mdconv.main(cls.docdir, build_dir=cls.build, make_pdf=HAS_PYPDF,
                    make_epub=True, formulas_enabled=False,
                    title='测试书籍')

    @classmethod
    def tearDownClass(cls):
        if cls._orig_cache is None:
            os.environ.pop('MDCONV_FORMULA_CACHE', None)
        else:
            os.environ['MDCONV_FORMULA_CACHE'] = cls._orig_cache
        shutil.rmtree(cls.docdir, ignore_errors=True)
        shutil.rmtree(cls.build, ignore_errors=True)
        shutil.rmtree(cls.cache, ignore_errors=True)

    @property
    def final_html(self):
        with open(os.path.join(self.build, 'final.html'), encoding='utf-8') as f:
            return f.read()

    def test_internal_links_have_no_dollar(self):
        """内部 md 链接应规范化为相对文档根的锚点且不含 "$"（href="#$xxx" 会导致链接全部失效）"""
        self.assertIn('href="#ch2/sec2"', self.final_html)
        self.assertNotIn('href="#$', self.final_html)

    def test_duplicate_ids_are_deduped(self):
        """跨文件同名标题的 id 应去重为唯一"""
        ids = re.findall(r'id="([^"]+)"', self.final_html)
        self.assertEqual(len(ids), len(set(ids)), f'存在重复 id: {ids}')

    def test_same_name_images_not_overwritten(self):
        """不同目录的同名图片应生成不同的目标文件"""
        images = os.listdir(os.path.join(self.build, 'images'))
        pics = [n for n in images if n.endswith('.png') and 'pic' in n]
        self.assertEqual(len(pics), 2, f'同名图片被覆盖，仅剩: {pics}')

    @unittest.skipIf(not HAS_PYPDF, '未安装 pypdf，跳过 PDF 测试')
    def test_pdf_outline_bookmarks(self):
        """PDF 应生成侧边栏书签，条目文本取自标题"""
        titles = outline_titles(os.path.join(self.build, 'final.pdf'))
        self.assertTrue(titles, '未生成 PDF 书签')
        # 两章标题相同，书签应各保留一条
        self.assertEqual(titles.count('第一节'), 2, f'书签条目异常: {titles}')

    @unittest.skipIf(not HAS_PYPDF, '未安装 pypdf，跳过 PDF 测试')
    def test_pdf_is_pdf_a_4u(self):
        """PDF 应声明基础 PDF/A-4（ISO 19005-4，基于 PDF 2.0），且不带 conformance"""
        reader = pypdf.PdfReader(os.path.join(self.build, 'final.pdf'))
        root = reader.trailer['/Root']
        self.assertEqual(reader.pdf_header, '%PDF-2.0', 'PDF 版本不是 2.0')
        self.assertIn('/OutputIntents', root, '缺少 PDF/A 输出意图')
        xmp = root['/Metadata'].get_data().decode('utf-8', 'ignore')
        self.assertIn('pdfaid:part="4"', xmp, 'PDF/A 版本不是 4')
        # ISO 19005-4 6.7.3：基础 PDF/A-4 不得提供 conformance（仅 4e/4f 才有），
        # 且 pdfaid:rev 必须为 2020（WeasyPrint 的变体默认不写该属性）
        self.assertNotIn('pdfaid:conformance', xmp, '基础 PDF/A-4 不应带 conformance')
        self.assertIn('pdfaid:rev="2020"', xmp, 'PDF/A-4 缺少 pdfaid:rev="2020"')

    def test_epub_metadata(self):
        """EPUB 元数据应来自调用参数而非占位符"""
        with zipfile.ZipFile(os.path.join(self.build, 'final.epub')) as z:
            opf = z.read('EPUB/content.opf').decode('utf-8')
        self.assertIn('<dc:title>测试书籍</dc:title>', opf)
        self.assertIn('mdconv-', opf)
        self.assertNotIn('My Book', opf)

    def test_epub_no_duplicate_zip_names(self):
        """EPUB zip 包内不应有重复条目"""
        with zipfile.ZipFile(os.path.join(self.build, 'final.epub')) as z:
            names = z.namelist()
        dup = [n for n in names if names.count(n) > 1]
        self.assertEqual(len(names), len(set(names)), f'存在重复条目: {dup}')

    def test_epub_includes_embedded_css(self):
        """EPUB 应包含内嵌样式，且剥离排版引擎专用的打印 CSS"""
        with zipfile.ZipFile(os.path.join(self.build, 'final.epub')) as z:
            css_names = [n for n in z.namelist() if n.endswith('.css')]
            self.assertTrue(css_names, 'EPUB 缺少样式表')
            main_css = z.read('EPUB/css/main.css').decode('utf-8')
        self.assertIn('LXGW WenKai GB Screen', main_css)
        # @page / bookmark-* 属于 CSS Paged Media 与排版引擎，阅读器不识别，
        # EPUBCheck 会报 CSS-008 解析错误
        self.assertNotIn('@page', main_css)
        self.assertNotIn('bookmark-level', main_css)

    def test_epub_nav_is_nested(self):
        """EPUB 目录应按 H1/H2 建立两级层级"""
        with zipfile.ZipFile(os.path.join(self.build, 'final.epub')) as z:
            nav = z.read('EPUB/nav.xhtml').decode('utf-8')
        # 顶层 <ol> 之外，章内还应存在嵌套的 <ol>（H2 挂在 H1 之下）
        self.assertGreaterEqual(nav.count('<ol>'), 2, 'EPUB 目录缺少两级层级')

    def test_epub_cross_chapter_links_remapped(self):
        """EPUB 中指向其他章节的内部链接应重映射为目标章节文件"""
        with zipfile.ZipFile(os.path.join(self.build, 'final.epub')) as z:
            chaps = [n for n in z.namelist() if n.startswith('EPUB/chap_')]
            remapped = []
            for name in chaps:
                content = z.read(name).decode('utf-8')
                remapped += re.findall(r'href="(chap_\d+\.xhtml#[^"]+)"', content)
        self.assertTrue(remapped, '跨章节链接未重映射')

    def test_epub_cover_meta_present(self):
        """存在 book-logo.png 时 EPUB 应通过 meta 标记封面且封面页在目录首位"""
        with zipfile.ZipFile(os.path.join(self.build, 'final.epub')) as z:
            names = z.namelist()
            opf = z.read('EPUB/content.opf').decode('utf-8')
        self.assertIn('name="cover"', opf, 'EPUB 缺少封面 meta')
        self.assertIn('EPUB/cover.xhtml', names, 'EPUB 缺少封面页')


class TocPageTest(unittest.TestCase):
    """目录页由正文标题构建：只进 PDF，源目录文件不再排版成正文"""

    def setUp(self):
        self.docdir = tempfile.mkdtemp(prefix='mdconv-toc-')
        self.build = tempfile.mkdtemp(prefix='mdconv-toc-build-')

    def tearDown(self):
        shutil.rmtree(self.docdir, ignore_errors=True)
        shutil.rmtree(self.build, ignore_errors=True)

    def _build_doc(self, en_pdf=True, **kwargs):
        with open(os.path.join(self.docdir, 'SUMMARY.md'), 'w', encoding='utf-8') as f:
            f.write(
                '# Summary\n\n'
                '## 第一章\n\n'
                '* [第一节](ch1/sec1.md)\n'
                '* [第二节](ch2/sec2.md)\n'
                '* [目录](mu-lu.md)\n'
            )
        with open(os.path.join(self.docdir, 'mu-lu.md'), 'w', encoding='utf-8') as f:
            f.write(
                '# 目录\n\n'
                '## 第一章\n\n'
                '* [第一节](ch1/sec1.md)\n'
                '* [第二节](ch2/sec2.md)\n'
                '* [目录](mu-lu.md)\n'
            )
        # 每章含 Markdown 一、二、三级标题，用于验证书签深度
        for sub, name, first in (('ch1', 'sec1.md', '第一节'),
                                 ('ch2', 'sec2.md', '第二节')):
            os.makedirs(os.path.join(self.docdir, sub), exist_ok=True)
            with open(os.path.join(self.docdir, sub, name), 'w', encoding='utf-8') as f:
                f.write(f'# {first}\n\n正文内容。\n\n'
                        f'## {first}的子节\n\n子节内容。\n\n'
                        f'### {first}的小节\n\n小节内容。\n')
        mdconv.main(self.docdir, build_dir=self.build, make_pdf=en_pdf,
                    make_epub=False, make_docx=False, formulas_enabled=False,
                    **kwargs)

    def _read(self, name):
        with open(os.path.join(self.build, name), encoding='utf-8') as f:
            return f.read()

    def test_source_toc_file_not_rendered_as_body(self):
        """mu-lu.md 不应作为正文章节重复排版"""
        self._build_doc(en_pdf=False)
        self.assertNotIn('<a id="mu-lu"></a>', self._read('final.html'))

    def test_toc_page_only_in_pdf_html(self):
        """目录页只出现在 PDF 专用 HTML 中，EPUB/Word 读的 final.html 不含"""
        self._build_doc(en_pdf=False)
        self.assertNotIn('<div class="toc-page"', self._read('final.html'))
        self.assertIn('<div class="toc-page"', self._read('pdf.html'))

    @unittest.skipIf(not HAS_PYPDF, '未安装 pypdf，跳过 PDF 测试')
    def test_toc_page_numbers_start_at_body(self):
        """目录为第一页，正文首页页脚应为 1（封面与目录不计入页码）"""
        self._build_doc()
        reader = pypdf.PdfReader(os.path.join(self.build, 'final.pdf'))
        toc_text = reader.pages[0].extract_text() or ''
        # build 在临时目录时仍应命中内置 GB 字体（absolutize_pdf_assets），
        # 这样中文条目可正常提取，不依赖宿主系统字体
        self.assertIn('第一节', toc_text, '目录页缺少章节条目')
        body_text = reader.pages[1].extract_text() or ''
        self.assertIn('· 1 ·', body_text, f'正文首页页码异常: {body_text[:80]}')

    @unittest.skipIf(not HAS_PYPDF, '未安装 pypdf，跳过 PDF 测试')
    def test_bookmark_depth_default_stops_at_h2(self):
        """默认深度 2：书签含章与节，不含三级标题"""
        self._build_doc()
        titles = outline_titles(os.path.join(self.build, 'final.pdf'))
        self.assertIn('第一节', titles)
        self.assertIn('第一节的子节', titles)
        self.assertNotIn('第一节的小节', titles)

    @unittest.skipIf(not HAS_PYPDF, '未安装 pypdf，跳过 PDF 测试')
    def test_bookmark_depth_one_only_chapters(self):
        """深度 1：书签只到章（SUMMARY 分组标题与 Markdown 一级标题）"""
        self._build_doc(bookmark_depth=1)
        # 分组标题来自 SUMMARY.md 的 ## 行，渲染为 h1，始终作为章级书签
        self.assertEqual(outline_titles(os.path.join(self.build, 'final.pdf')),
                         ['第一章', '第一节', '第二节'])


def docx_heading_texts(docx_path):
    """提取 Word 文档中所有标题段落的文本（按出现顺序）"""
    import docx
    d = docx.Document(docx_path)
    return [p.text for p in d.paragraphs
            if p.style.name.startswith('Heading')]


def epub_nav_titles(epub_path):
    """提取 EPUB nav 的条目文本（按出现顺序）"""
    with zipfile.ZipFile(epub_path) as z:
        nav = next(n for n in z.namelist() if n.endswith('nav.xhtml'))
        html = z.read(nav).decode('utf-8')
    return re.findall(r'<a[^>]*>([^<]+)</a>', html)


class ContentIntegrityTest(unittest.TestCase):
    """三格式导出的内容完整性：源文档的标题、图片、代码块、内链

    必须在 PDF/EPUB/Word 中等价呈现，任何一种介质不得丢内容或产坏链接。
    """

    @classmethod
    def setUpClass(cls):
        cls.docdir = tempfile.mkdtemp(prefix='mdconv-ci-')
        cls.build = tempfile.mkdtemp(prefix='mdconv-ci-build-')
        cls.cache = tempfile.mkdtemp(prefix='mdconv-ci-cache-')
        cls._orig_cache = os.environ.get('MDCONV_FORMULA_CACHE')
        os.environ['MDCONV_FORMULA_CACHE'] = cls.cache
        with open(os.path.join(cls.docdir, 'SUMMARY.md'), 'w', encoding='utf-8') as f:
            f.write('# Summary\n\n## 卷一\n\n'
                    '* [第一章](ch1/c1.md)\n* [第二章](ch2/c2.md)\n')
        # ch1 一张图、ch2 两张图；两章含跨章链接、代码块与三级标题
        for sub, num, title, pics in (('ch1', '一', '第一章', 1),
                                      ('ch2', '二', '第二章', 2)):
            os.makedirs(os.path.join(cls.docdir, sub, 'img'), exist_ok=True)
            for k in range(pics):
                make_png(os.path.join(cls.docdir, sub, 'img', f'pic{k}.png'),
                         (k * 120, 0, 0))
            other = 'ch2/c2.md' if sub == 'ch1' else 'ch1/c1.md'
            other_title = '第二章' if sub == 'ch1' else '第一章'
            body = (f'# {title}\n\n'
                    f'参见[{other_title}]({other})。\n\n'
                    + ''.join(f'![图{k}](img/pic{k}.png)\n\n'
                              for k in range(pics))
                    + f'## 第{num}节\n\n'
                    '```sh\necho hello\n```\n\n'
                    f'### 第{num}小节\n\n'
                    '正文。\n')
            fname = 'c1.md' if sub == 'ch1' else 'c2.md'
            with open(os.path.join(cls.docdir, sub, fname), 'w', encoding='utf-8') as f:
                f.write(body)
        mdconv.main(cls.docdir, build_dir=cls.build, make_pdf=True,
                    make_epub=True, make_docx=True, formulas_enabled=False,
                    title='内容完整性')
        cls._pdf = os.path.join(cls.build, 'final.pdf')
        cls._epub = os.path.join(cls.build, 'final.epub')
        cls._docx = os.path.join(cls.build, 'final.docx')

    @classmethod
    def tearDownClass(cls):
        if cls._orig_cache is None:
            os.environ.pop('MDCONV_FORMULA_CACHE', None)
        else:
            os.environ['MDCONV_FORMULA_CACHE'] = cls._orig_cache
        shutil.rmtree(cls.docdir, ignore_errors=True)
        shutil.rmtree(cls.build, ignore_errors=True)
        shutil.rmtree(cls.cache, ignore_errors=True)

    def source_titles(self):
        """按 SUMMARY 顺序解析源文档的标题文本"""
        with open(os.path.join(self.docdir, 'SUMMARY.md'), encoding='utf-8') as f:
            summary = f.read()
        titles = []
        for line in summary.splitlines():
            m = re.match(r'## (.+?)\s*$', line)
            if m and '[' not in m.group(1):
                titles.append(m.group(1).strip())
        for path in re.findall(r'\[.*?\]\((.*?)\)', summary):
            with open(os.path.join(self.docdir, path), encoding='utf-8') as f:
                for line in f:
                    m = re.match(r'(#+) (.+?)\s*$', line)
                    if m:
                        titles.append(m.group(2).strip())
        return titles

    def pdf_images(self):
        reader = pypdf.PdfReader(self._pdf)
        images = set()
        for page in reader.pages:
            xo = (page.get('/Resources') or {}).get('/XObject') or {}
            for key, value in xo.items():
                if value.get_object().get('/Subtype') == '/Image':
                    images.add(key)
        return images

    def test_source_titles_match_format_structure(self):
        """源标题集合应与 PDF 书签、EPUB nav、Word 标题一一对应"""
        src = self.source_titles()
        depth_two = [t for t in src if not t.endswith('小节')]
        self.assertEqual(outline_titles(self._pdf), depth_two,
                         'PDF 书签与源标题（到 ## 深度）不一致')
        self.assertEqual(docx_heading_texts(self._docx), src,
                         'Word 标题与源标题不一致')
        # EPUB nav 只到章级（分组 + 文件标题）
        chapters = [t for t in src if not t.startswith(('第', '第二小节'))]
        chapters = [t for t in src if t in ('卷一', '第一章', '第二章')]
        self.assertEqual(epub_nav_titles(self._epub),
                         ['卷一', '第一章', '第二章'],
                         'EPUB nav 应含分组与章标题')

    def test_images_present_in_all_formats(self):
        """三张源图片应在三种格式中都存在"""
        self.assertGreaterEqual(len(self.pdf_images()), 3, 'PDF 缺少图片')
        with zipfile.ZipFile(self._epub) as z:
            media = [n for n in z.namelist()
                     if '/images/' in n and n.endswith('.png')]
        self.assertGreaterEqual(len(media), 3, 'EPUB 缺少图片')
        import docx
        d = docx.Document(self._docx)
        self.assertGreaterEqual(len(d.inline_shapes), 3, 'Word 缺少图片')

    def test_epub_images_are_packaged(self):
        """EPUB 章节 body 引用的每张图片都必须已打包，不得断链"""
        with zipfile.ZipFile(self._epub) as z:
            names = set(z.namelist())
            missing = []
            for name in [n for n in names if n.endswith('.xhtml')]:
                html = z.read(name).decode('utf-8')
                for src in re.findall(r'<img[^>]+src="([^"]+)"', html):
                    base = src.split('/')[-1]
                    if not any(base in x for x in names):
                        missing.append(f'{name} -> {src}')
        self.assertEqual(missing, [], 'EPUB 存在断链图片')

    def test_code_block_content_survives(self):
        """代码块内容必须进入三种介质"""
        reader = pypdf.PdfReader(self._pdf)
        text = ''.join((p.extract_text() or '') for p in reader.pages)
        self.assertIn('echo hello', text, 'PDF 丢失代码块内容')
        with zipfile.ZipFile(self._epub) as z:
            bodies = [re.sub(r'<[^>]+>', '', z.read(n).decode('utf-8'))
                      for n in z.namelist() if n.endswith('.xhtml')]
        self.assertTrue(any('echo hello' in b for b in bodies),
                        'EPUB 丢失代码块内容')
        import docx
        d = docx.Document(self._docx)
        self.assertTrue(any('echo hello' in p.text for p in d.paragraphs),
                        'Word 丢失代码块内容')

    def test_pdf_internal_links_resolve(self):
        """PDF 里的内部链接注释必须指向有效页面

        mdconv 用命名目标（named destination）定位章节，目标名必须
        能在文档目录中解析回真实页面。
        """
        reader = pypdf.PdfReader(self._pdf)
        named = reader.named_destinations
        links = 0
        broken = []
        for idx, page in enumerate(reader.pages):
            for annot in (page.get('/Annots') or []):
                obj = annot.get_object()
                if obj.get('/Subtype') != '/Link':
                    continue
                dest = obj.get('/Dest')
                if dest is None:
                    action = obj.get('/A')
                    if action is not None:
                        dest = action.get_object().get('/D')
                if dest is None:
                    continue
                links += 1
                dest_obj = dest.get_object()
                if isinstance(dest_obj, str):
                    # /Dest 直接是命名目标名
                    name = dest_obj
                else:
                    first = dest_obj[0]
                    name = first if isinstance(first, str) else None
                    if name is None:
                        target = first.get_object()
                        if target.get('/Type') != '/Page':
                            broken.append(f'第{idx + 1}页 -> 目标不是页面')
                        continue
                if name not in named:
                    broken.append(f'第{idx + 1}页 -> 命名目标 {name!r} 不存在')
        self.assertGreater(links, 0, '跨章链接未生成 PDF 内链')
        self.assertEqual(broken, [], 'PDF 存在指向无效页面的内链')

    def test_docx_has_toc_field(self):
        """Word 文档必须包含 TOC 域（打开后按 F9 更新）"""
        with zipfile.ZipFile(self._docx) as z:
            body = z.read('word/document.xml').decode('utf-8', 'ignore')
        self.assertIn('TOC \\o', body, 'Word 缺少 TOC 域')


class PaginationTest(unittest.TestCase):
    """分页回归测试：封面/目录与章标题各自的分页规则不应叠加出空白页"""

    def setUp(self):
        self.docdir = tempfile.mkdtemp(prefix='mdconv-page-')
        self.build = tempfile.mkdtemp(prefix='mdconv-page-build-')

    def tearDown(self):
        shutil.rmtree(self.docdir, ignore_errors=True)
        shutil.rmtree(self.build, ignore_errors=True)

    def _build_doc(self):
        os.makedirs(os.path.join(self.docdir, 'ch1'), exist_ok=True)
        with open(os.path.join(self.docdir, 'SUMMARY.md'), 'w', encoding='utf-8') as f:
            f.write('# Summary\n\n## 第一章\n\n* [第一节](ch1/sec1.md)\n')
        with open(os.path.join(self.docdir, 'mu-lu.md'), 'w', encoding='utf-8') as f:
            f.write('# 目录\n\n## 第一章\n\n* [第一节](ch1/sec1.md)\n')
        with open(os.path.join(self.docdir, 'ch1', 'sec1.md'), 'w', encoding='utf-8') as f:
            f.write('# 第一节\n\n正文内容。\n')
        make_png(os.path.join(self.docdir, 'book-logo.png'))

    @unittest.skipIf(not HAS_PYPDF, '未安装 pypdf，跳过 PDF 测试')
    def test_no_blank_page_between_cover_toc_and_body(self):
        """封面→目录→正文交界处不应出现只有页脚的空白页"""
        self._build_doc()
        mdconv.main(self.docdir, build_dir=self.build, make_pdf=True,
                    make_epub=False, formulas_enabled=False)
        reader = pypdf.PdfReader(os.path.join(self.build, 'final.pdf'))
        # 首页为纯图片封面，其后各页都应带有文字（目录或正文）
        blanks = [i + 1 for i, page in enumerate(reader.pages)
                  if i > 0 and not (page.extract_text() or '').strip()]
        self.assertEqual([], blanks, f'存在空白页: {blanks}')


class Pdfa4Test(unittest.TestCase):
    """PDF/A-4 合规细节：内容流不得含 nan 操作符，图像 Interpolate 必须为 false

    前者是上游 SVG 渲染对部分图形（如 shields.io 徽章）写出 NaN 坐标的真实事故；
    后者以 SVG 内嵌位图触发（该路径不经过 CSS image-rendering，上游默认写 true）。
    """

    def setUp(self):
        self.docdir = tempfile.mkdtemp(prefix='mdconv-pdfa-')
        self.build = tempfile.mkdtemp(prefix='mdconv-pdfa-build-')
        self.cache = tempfile.mkdtemp(prefix='mdconv-pdfa-cache-')
        self._orig_cache = os.environ.get('MDCONV_FORMULA_CACHE')
        os.environ['MDCONV_FORMULA_CACHE'] = self.cache

    def tearDown(self):
        if self._orig_cache is None:
            os.environ.pop('MDCONV_FORMULA_CACHE', None)
        else:
            os.environ['MDCONV_FORMULA_CACHE'] = self._orig_cache
        shutil.rmtree(self.docdir, ignore_errors=True)
        shutil.rmtree(self.build, ignore_errors=True)
        shutil.rmtree(self.cache, ignore_errors=True)

    def _build_doc(self):
        # 位图以 data URI 内嵌进 SVG：内嵌图走 RasterImage 的 XObject 路径，
        # 且不依赖 mdconv 复制同名图片到 build/images 的行为
        png_path = os.path.join(self.docdir, 'pic.png')
        make_png(png_path)
        with open(png_path, 'rb') as f:
            data = base64.b64encode(f.read()).decode('ascii')
        with open(os.path.join(self.docdir, 'badge.svg'), 'w', encoding='utf-8') as f:
            f.write(
                '<svg xmlns="http://www.w3.org/2000/svg" width="80" height="60" '
                'viewBox="0 0 80 60">'
                '<image x="0" y="0" width="80" height="60" '
                'href="data:image/png;base64,' + data + '"/></svg>'
            )
        with open(os.path.join(self.docdir, 'SUMMARY.md'), 'w', encoding='utf-8') as f:
            f.write('# Summary\n\n* [A](a.md)\n')
        with open(os.path.join(self.docdir, 'a.md'), 'w', encoding='utf-8') as f:
            f.write('# 第一节\n\n![徽章](badge.svg)\n')

    def _render(self):
        self._build_doc()
        mdconv.main(self.docdir, build_dir=self.build, make_pdf=True,
                    make_epub=False, make_docx=False, formulas_enabled=False)
        return pypdf.PdfReader(os.path.join(self.build, 'final.pdf'))

    def _iter_images(self, reader):
        for page in reader.pages:
            xobjects = ((page.get('/Resources') or {}).get('/XObject') or {})
            for value in xobjects.values():
                obj = value.get_object()
                if obj.get('/Subtype') == '/Image':
                    yield obj

    @unittest.skipIf(not HAS_PYPDF, '未安装 pypdf，跳过 PDF 测试')
    def test_images_interpolate_disabled(self):
        """PDF/A 6.2.7.1：所有图像 XObject 的 Interpolate 不得为 true"""
        reader = self._render()
        values = [obj.get('/Interpolate') for obj in self._iter_images(reader)]
        self.assertTrue(values, '测试文档未生成图像 XObject')
        self.assertNotIn(True, values, f'存在 Interpolate=true 的图像: {values}')

    @unittest.skipIf(not HAS_PYPDF, '未安装 pypdf，跳过 PDF 测试')
    def test_content_streams_have_no_nan(self):
        """PDF/A 6.2.2：内容流不得出现未定义操作符（上游 NaN 坐标会序列化为 nan）"""
        reader = self._render()
        for page in reader.pages:
            contents = page.get('/Contents')
            streams = contents if isinstance(contents, list) else [contents]
            raw = b''.join(stream.get_data() for stream in streams)
            self.assertIsNone(re.search(rb'(?<![A-Za-z0-9])nan(?![A-Za-z0-9])', raw),
                              '内容流中出现 nan 操作符')

    def test_nan_numbers_are_sanitized(self):
        """pydyf 数字序列化应对 NaN/Inf 折算为 0，避免产生非法操作符"""
        import pydyf
        mdconv._patch_pdfa4_output()
        self.assertEqual(pydyf._to_bytes(float('nan')), b'0')
        self.assertEqual(pydyf._to_bytes(float('inf')), b'0')
        self.assertEqual(pydyf._to_bytes(1.5), b'1.5')


@unittest.skipIf(shutil.which('xelatex') is None, '未安装 xelatex，跳过公式渲染测试')
class FormulaTest(unittest.TestCase):
    """LaTeX 公式渲染与持久缓存测试"""

    def test_formula_rendered_and_cached(self):
        docdir = tempfile.mkdtemp(prefix='mdconv-doc-')
        build = tempfile.mkdtemp(prefix='mdconv-build-')
        cache = tempfile.mkdtemp(prefix='mdconv-cache-')
        orig_cache = os.environ.get('MDCONV_FORMULA_CACHE')
        os.environ['MDCONV_FORMULA_CACHE'] = cache
        try:
            with open(os.path.join(docdir, 'SUMMARY.md'), 'w', encoding='utf-8') as f:
                f.write('# Summary\n\n* [A](a.md)\n')
            with open(os.path.join(docdir, 'a.md'), 'w', encoding='utf-8') as f:
                f.write('公式 $E = mc^2$ 测试。\n')

            mdconv.main(docdir, build_dir=build, make_pdf=False, make_epub=False)

            # build/images 与持久缓存中都应存在公式 SVG
            images = os.listdir(os.path.join(build, 'images'))
            self.assertTrue([n for n in images if n.startswith('formula_') and n.endswith('.svg')],
                            '公式 SVG 未生成')
            cached = os.listdir(cache)
            self.assertTrue([n for n in cached if n.startswith('formula_') and n.endswith('.svg')],
                            '公式未写入持久缓存')
        finally:
            if orig_cache is None:
                os.environ.pop('MDCONV_FORMULA_CACHE', None)
            else:
                os.environ['MDCONV_FORMULA_CACHE'] = orig_cache
            shutil.rmtree(docdir, ignore_errors=True)
            shutil.rmtree(build, ignore_errors=True)
            shutil.rmtree(cache, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
