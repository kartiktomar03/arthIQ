const {chromium}=require('../../frontend/node_modules/playwright');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
(async()=>{
 const browser=await chromium.launch({channel:'msedge'});
 try {
 const page=await browser.newPage();
 const errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 for(const width of [1440,1280,768,390]){
  await page.setViewportSize({width,height:width===390?844:900});
  for(const state of ['opening','analysis','chapter']){
   await page.goto(pathToFileURL(path.join(__dirname,'index.html')).href+'#'+state);
   if(width<=768 && state!=='opening') await page.locator('#flip').click();
   if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Overflow '+state+' '+width);
   await page.screenshot({path:path.join(__dirname,'screenshots',state+'-'+width+'.png'),fullPage:true});
  }
 }
 if(errors.length)throw Error(errors.join('\n'));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
