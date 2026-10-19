import fs from 'node:fs';
import fsp from 'node:fs/promises';
import path from 'node:path';
import {Readable} from 'node:stream';
import {pipeline} from 'node:stream/promises';
import {createHash} from 'node:crypto';
import {spawn} from 'node:child_process';
const root=process.cwd();
const taskTemp=path.join(process.env.LOCALAPPDATA,'Temp','libera_v493_render_20261019');
await fsp.mkdir(taskTemp,{recursive:true});
const msi=path.join(taskTemp,'LibreOffice_26.8.1_Win_x86-64.msi');
const official='https://download.documentfoundation.org/libreoffice/stable/26.8.1/win/x86_64/LibreOffice_26.8.1_Win_x86-64.msi';
const mirror='https://ftp.kaist.ac.kr/tdf/libreoffice/stable/26.8.1/win/x86_64/LibreOffice_26.8.1_Win_x86-64.msi';
const expected='c6298b10cfa1748bcbedad94c62ce771e240e5021bfd6d7a967cd571b04b5312';
const size=374870016;
async function digest(file){const h=createHash('sha256');for await(const c of fs.createReadStream(file,{highWaterMark:16*1024*1024}))h.update(c);return h.digest('hex');}
let ok=await fsp.stat(msi).then(s=>s.size===size).catch(()=>false);
if(ok)ok=(await digest(msi))===expected;
if(!ok){
  const partial=msi+'.part';
  const prefix=await fsp.stat(partial).then(s=>Math.min(s.size,size)).catch(()=>0);
  console.log('Resuming verified renderer download from '+prefix+' bytes using six independent ranges.');
  const chunkSize=Math.ceil((size-prefix)/6), chunks=[];
  const results=await Promise.allSettled(Array.from({length:6},async(_,i)=>{
    const start=prefix+i*chunkSize,end=Math.min(size-1,start+chunkSize-1);
    if(start>end)return;
    const dest=msi+'.range'+i;chunks[i]=dest;
    for(let attempt=0;attempt<4;attempt++){
      const have=await fsp.stat(dest).then(s=>s.size).catch(()=>0);
      if(have===end-start+1)break;
      if(have>end-start+1)throw new Error('Range file is unexpectedly oversized');
      const resume=start+have;
      const res=await fetch(mirror,{headers:{Range:'bytes='+resume+'-'+end},signal:AbortSignal.timeout(600000)});
      if(res.status!==206||res.headers.get('content-range')!=='bytes '+resume+'-'+end+'/'+size)throw new Error('Range response mismatch');
      try{await pipeline(Readable.fromWeb(res.body),fs.createWriteStream(dest,{flags:'a'}));}
      catch(error){if(attempt===3)throw error;}
    }
    if((await fsp.stat(dest)).size!==end-start+1)throw new Error('Range size mismatch');
    console.log('Range '+i+' complete.');
  }));
  for(const result of results)if(result.status==='rejected')throw result.reason;
  const joined=msi+'.joined';
  if(prefix>0)await fsp.copyFile(partial,joined);else await fsp.writeFile(joined,Buffer.alloc(0));
  for(const chunk of chunks.filter(Boolean))await fsp.appendFile(joined,await fsp.readFile(chunk));
  const stat=await fsp.stat(joined), hash=await digest(joined);
  if(stat.size!==size||hash!==expected)throw new Error('MSI size or SHA256 mismatch');
  await fsp.rename(joined,msi);
}
console.log('MSI verified against official mirrorlist SHA256.');
const target=path.join(taskTemp,'administrative_image');
await fsp.mkdir(target,{recursive:true});
const log=path.join(taskTemp,'administrative_extract.log');
const code=await new Promise((resolve,reject)=>{
  const proc=spawn('C:/Windows/System32/msiexec.exe',['/a',msi,'/qn','/norestart','TARGETDIR='+target,'/L*v',log],{windowsHide:true,stdio:'ignore'});
  proc.on('error',reject);proc.on('exit',resolve);
});
if(code!==0&&code!==3010)throw new Error('Administrative extraction failed with '+code+'; log '+log);
async function findExe(dir){for(const d of await fsp.readdir(dir,{withFileTypes:true})){const p=path.join(dir,d.name);if(d.isFile()&&d.name.toLowerCase()==='soffice.exe')return p;if(d.isDirectory()){const hit=await findExe(p);if(hit)return hit;}}return null;}
const exe=await findExe(target);if(!exe)throw new Error('Extracted soffice.exe missing');
const receipt={official_url:official,mirror_url:mirror,mirrorlist_url:official+'.mirrorlist',expected_msi_bytes:size,verified_msi_sha256:expected,msi_path:msi,mode:'administrative image extraction only, no system installation',extract_exit_code:code,extract_log:log,soffice_exe:exe,task_temp:taskTemp,render_started:false};
await fsp.writeFile(path.join(root,'research/v493_portable_renderer_20261019.json'),JSON.stringify(receipt,null,2));
console.log(JSON.stringify(receipt));
