import fs from 'node:fs/promises';
import path from 'node:path';
import { createRequire } from 'node:module';

const runtimeRequire = createRequire('C:/Users/Insun/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/package.json');
const { chromium } = runtimeRequire('playwright');
const work = path.dirname(new URL(import.meta.url).pathname.replace(/^\/(\w:)/, '$1'));
const output = 'C:/Users/Insun/Downloads/Workflow_RAG_보완안_루프';
const source = await fs.readFile(output + '.mmd', 'utf8');
const browser = await chromium.launch({
  executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  headless: true,
});
try {
  const page = await browser.newPage({ viewport: { width: 1800, height: 1800 }, deviceScaleFactor: 2 });
  await page.setContent('<!doctype html><html lang="ko"><head><meta charset="utf-8"><style>html,body{margin:0;background:white;}body{width:max-content;}svg{display:block;background:white;}</style></head><body><main id="diagram"></main></body></html>');
  await page.addScriptTag({ path: path.join(work, 'mermaid.min.js') });
  const svg = await page.evaluate(async (diagramSource) => {
    mermaid.initialize({
      startOnLoad: false,
      securityLevel: 'strict',
      theme: 'base',
      fontFamily: 'Malgun Gothic, Arial, sans-serif',
      themeVariables: {
        fontFamily: 'Malgun Gothic, Arial, sans-serif',
        fontSize: '18px',
        primaryColor: '#FFFFFF',
        primaryTextColor: '#17212F',
        primaryBorderColor: '#6B7280',
        lineColor: '#75808F',
        secondaryColor: '#FFFFFF',
        tertiaryColor: '#FFFFFF',
        edgeLabelBackground: '#FFFFFF',
      },
      flowchart: { htmlLabels: false, useMaxWidth: false, curve: 'linear', nodeSpacing: 32, rankSpacing: 32, diagramPadding: 26, wrappingWidth: 300 },
    });
    const result = await mermaid.render('workflowRagFigure', diagramSource);
    document.getElementById('diagram').innerHTML = result.svg;
    await document.fonts.ready;
    const svgElement = document.querySelector('svg');
    svgElement.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
    return svgElement.outerHTML;
  }, source);
  await fs.writeFile(output + '.svg', svg, 'utf8');
  await page.locator('svg').screenshot({ path: output + '.png' });
  const dimensions = await page.locator('svg').boundingBox();
  const actualText = await page.locator('svg').textContent();
  await fs.writeFile(path.join(work, 'render_check.json'), JSON.stringify({ dimensions, actualText, source }, null, 2), 'utf8');
  console.log(JSON.stringify({ svg: output + '.svg', png: output + '.png', dimensions }));
} finally {
  await browser.close();
}
