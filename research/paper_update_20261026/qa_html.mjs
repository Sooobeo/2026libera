import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {createRequire} from 'node:module';
const req=createRequire('C:/Users/Insun/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright-core/package.json');
const {chromium}=req('playwright-core');
const root=process.cwd();
const out=path.join(root,'research/paper_update_20261026/qa/html');
await fs.mkdir(out,{recursive:true});
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
try {
 const page=await browser.newPage({viewport:{width:1440,height:1100},deviceScaleFactor:1});
 await page.goto(pathToFileURL(path.join(root,'paper/LIBERA_텀페이퍼_v5.0_20261026.html')).href);
 await page.screenshot({path:path.join(out,'top.png')});
 const headings=await page.locator('h2').all();
 const shots=[];
 for(let i=0;i<headings.length;i++){
  const h=headings[i];await h.scrollIntoViewIfNeeded();
  const name=`section-${i+1}.png`;
  await page.screenshot({path:path.join(out,name)});
  shots.push({heading:await h.innerText(),png:name});
 }
 const checks=await page.evaluate(()=>({title:document.title,bodyWidth:document.body.scrollWidth,viewport:innerWidth,headings:[...document.querySelectorAll('h2,h3')].length,tables:document.querySelectorAll('table').length,missingAnchors:[...document.querySelectorAll('a[href^="#"]')].filter(a=>!document.querySelector(a.getAttribute('href'))).map(a=>a.href),overflowElements:[...document.querySelectorAll('p,th,td,h1,h2,h3')].filter(e=>e.scrollWidth>e.clientWidth+2).map(e=>({tag:e.tagName,text:e.textContent.slice(0,80)}))}));
 await page.setViewportSize({width:390,height:844});await page.evaluate(()=>scrollTo(0,0));await page.screenshot({path:path.join(out,'mobile-top.png')});
 const mobile=await page.evaluate(()=>({bodyWidth:document.body.scrollWidth,viewport:innerWidth,tableScrollContainers:document.querySelectorAll('.table-wrap').length}));
 await fs.writeFile(path.join(out,'receipt.json'),JSON.stringify({renderer:'headless Chrome via managed playwright-core',checks,mobile,shots,visual_review:'pending'},null,2));
 console.log(JSON.stringify({checks,mobile,shots}));
} finally {await browser.close();}
