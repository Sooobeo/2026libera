import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {createRequire} from 'node:module';
const req=createRequire('C:/Users/Insun/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright-core/package.json');
const {chromium}=req('playwright-core');
const root=process.cwd();
const html=path.join(root,'paper/LIBERA_소논문_v5.2_20261026.html');
const out=path.join(root,'research/manuscript_v520_20261026/qa');
await fs.mkdir(out,{recursive:true});
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
try{
  const page=await browser.newPage({viewport:{width:1440,height:1100},deviceScaleFactor:1});
  await page.goto(pathToFileURL(html).href);
  await page.screenshot({path:path.join(out,'top.png')});
  const sections=await page.locator('h2').all();
  const screenshots=[];
  for(let i=0;i<sections.length;i++){
    await sections[i].scrollIntoViewIfNeeded();
    const file=`section-${String(i+1).padStart(2,'0')}.png`;
    await page.screenshot({path:path.join(out,file)});
    screenshots.push({heading:await sections[i].innerText(),file});
  }
  const tables=await page.locator('figure').all();
  for(let i=0;i<tables.length;i++){
    const file=`table-${String(i+1).padStart(2,'0')}.png`;
    await tables[i].screenshot({path:path.join(out,file)});
    screenshots.push({table:i+1,file});
  }
  const desktop=await page.evaluate(()=>({
    bodyWidth:document.body.scrollWidth,viewport:innerWidth,
    tableCount:document.querySelectorAll('table').length,
    headings:document.querySelectorAll('h2,h3').length,
    missingAnchors:[...document.querySelectorAll('a[href^="#"]')].filter(a=>!document.querySelector(a.getAttribute('href'))).map(a=>a.href),
    overflow:[...document.querySelectorAll('p,th,td,h1,h2,h3')].filter(e=>e.scrollWidth>e.clientWidth+2).map(e=>e.textContent.slice(0,80)),
  }));
  await page.setViewportSize({width:390,height:844});
  await page.evaluate(()=>scrollTo(0,0));
  await page.screenshot({path:path.join(out,'mobile.png')});
  const mobile=await page.evaluate(()=>({bodyWidth:document.body.scrollWidth,viewport:innerWidth}));
  const pass=desktop.bodyWidth<=desktop.viewport&&desktop.tableCount===11&&desktop.headings===46&&!desktop.missingAnchors.length&&!desktop.overflow.length&&mobile.bodyWidth<=mobile.viewport;
  await fs.writeFile(path.join(out,'reader_checks.json'),JSON.stringify({pass,desktop,mobile,screenshots,visualReview:'pending'},null,2));
  console.log(JSON.stringify({pass,desktop,mobile,screenshotCount:screenshots.length+2}));
  if(!pass)process.exitCode=1;
}finally{await browser.close();}
