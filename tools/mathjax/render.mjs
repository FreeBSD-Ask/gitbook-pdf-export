// MathJax 4 + Bun：把一段 LaTeX 公式渲染成自包含的 SVG。
//
// 用法：bun render.mjs '<latex>' <输出文件> [display|inline]
//
// 由 mdconv.py 调用（PATH 中需有 bun，且本目录已执行过 bun install）。
//
// 直接使用 source 模块而不是 tex-svg bundle：bundle 会预加载
// a11y/sre，其 speech worker 在 Bun 下会因 fetch() 失败而崩溃。
// source 路径只装配 TeX 输入、SVG 输出与新 CM 字体，启动更快。
// fontCache: 'none' 让每个字符输出显式 path，不依赖阅读端字体，
// 与 LaTeX 后端的 dvisvgm --no-fonts 效果一致。
import { writeFile } from 'node:fs/promises';
import { mathjax } from '@mathjax/src/js/mathjax.js';
import { TeX } from '@mathjax/src/js/input/tex.js';
import '@mathjax/src/js/input/tex/ams/AmsConfiguration.js';
import '@mathjax/src/js/input/tex/newcommand/NewcommandConfiguration.js';
import '@mathjax/src/js/input/tex/mathtools/MathtoolsConfiguration.js';
import { SVG } from '@mathjax/src/js/output/svg.js';
import { liteAdaptor } from '@mathjax/src/js/adaptors/liteAdaptor.js';
import { RegisterHTMLHandler } from '@mathjax/src/js/handlers/html.js';
import { MathJaxNewcmFont } from '@mathjax/mathjax-newcm-font/js/svg.js';

const [, , tex, outPath, mode] = process.argv;

if (!tex || !outPath) {
  console.error('用法: bun render.mjs <latex> <out.svg> [display|inline]');
  process.exit(2);
}

const display = mode !== 'inline';

try {
  const adaptor = liteAdaptor();
  RegisterHTMLHandler(adaptor);

  const input = new TeX({
    packages: ['base', 'ams', 'newcommand', 'mathtools'],
  });
  const output = new SVG({
    fontCache: 'none',
    fontData: new MathJaxNewcmFont(),
  });
  const doc = mathjax.document('', { InputJax: input, OutputJax: output });

  const node = doc.convert(tex, {
    display,
    em: 16,
    ex: 8,
    containerWidth: 80 * 16,
  });

  let svg = adaptor.serializeXML(adaptor.tags(node, 'svg')[0]);

  // MathJax 默认把 TeX 错误画成红框而不是抛异常；这里还原为失败，
  // 让 mdconv 与 LaTeX 后端一致地保留原始公式文本。
  const mjxError = svg.match(/data-mjx-error="([^"]*)"/);
  if (mjxError) {
    console.error(`MathJax: ${mjxError[1]}`);
    process.exit(1);
  }

  // <img> 内的 currentColor 依赖上下文，统一成正文墨色更稳妥
  svg = svg.replaceAll('currentColor', '#212529');

  // MathJax 默认用 ex 标注尺寸（1ex = 8px = 6pt）。转成 pt 后
  // WeasyPrint 能稳定解析，不必依赖其对替换元素 ex 单位的支持。
  const EX_TO_PT = 6;
  svg = svg.replace(
    /\b(width|height)="(-?[\d.]+)ex"/g,
    (_, attr, value) => `${attr}="${(parseFloat(value) * EX_TO_PT).toFixed(3)}pt"`,
  );
  svg = svg.replace(
    /vertical-align:\s*(-?[\d.]+)ex/g,
    (_, value) => `vertical-align: ${(parseFloat(value) * EX_TO_PT).toFixed(3)}pt`,
  );

  await writeFile(outPath, svg);
} catch (err) {
  console.error(String(err && err.stack ? err.stack : err));
  process.exit(1);
}
