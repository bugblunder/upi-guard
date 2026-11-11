/* DOM behavior checks against a real local Flask API. Not a browser-layout test. */
const {JSDOM,CookieJar,VirtualConsole}=require('jsdom');
const fs=require('fs');
const base=process.env.GUARD_UI_URL||'http://127.0.0.1:5061';
const jar=new CookieJar(),errors=[],checks=[];
async function fetchWithCookies(url,options={}){
 url=new URL(url,base).href;options.headers={...(options.headers||{}),Cookie:jar.getCookieStringSync(url)};
 const response=await fetch(url,options);
 for(const cookie of response.headers.getSetCookie())jar.setCookieSync(cookie,url);
 return response;
}
async function wait(check,label){const end=Date.now()+12000;while(Date.now()<end){if(check())return;await new Promise(r=>setTimeout(r,25));}throw new Error('Timed out: '+label);}
async function main(){
 let r=await fetchWithCookies('/api/csrf'),token=(await r.json()).csrf_token;
 r=await fetchWithCookies('/api/login',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':token},body:JSON.stringify({username:'admin',password:process.env.GUARD_UI_PASSWORD})});
 if(r.status!==200)throw new Error('Authentication failed');checks.push('Authenticated cookie and rotated CSRF token');
 const virtualConsole=new VirtualConsole();virtualConsole.on('jsdomError',e=>errors.push(e.message));
 const dom=await JSDOM.fromURL(base+'/',{cookieJar:jar,runScripts:'dangerously',resources:'usable',pretendToBeVisual:true,virtualConsole,
  beforeParse(w){w.fetch=fetchWithCookies;w.HTMLCanvasElement.prototype.getContext=()=>({clearRect(){},beginPath(){},arc(){},stroke(){},fillText(){}});w.HTMLDialogElement.prototype.showModal=function(){this.setAttribute('open','');};w.HTMLDialogElement.prototype.close=function(){this.removeAttribute('open');};}});
 const w=dom.window,d=w.document,$=s=>d.querySelector(s),click=s=>$(s).click(),submit=s=>$(s).dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));
 await wait(()=>$('#total').textContent==='300','dashboard totals');checks.push('Overview renders 300 persisted transactions');
 click('button.nav-item[data-tab="transactions"]');await wait(()=>$('#transaction-rows tr'),'transaction list');
 $('#tx-search').value='sim-99-0000001';submit('#filter-form');await wait(()=>$('#tx-page').textContent.includes('1 transactions'),'transaction search');checks.push('Transaction ID search updates the table');
 click('.manual-review');await wait(()=>$('#case-dialog').hasAttribute('open'),'manual review');await wait(()=>$('#shap-evidence').textContent.includes('SHAP'),'model explanation');checks.push('Manual case creation and additive SHAP model evidence');click('#close-case');
 click('button.nav-item[data-tab="cases"]');await wait(()=>$('.case-open'),'case queue');click('.case-open');await wait(()=>$('#case-dialog').hasAttribute('open'),'case dialog');
 $('#case-form select[name="status"]').value='resolved';$('#case-form select[name="outcome"]').value='fraud';$('#case-form textarea').value='Confirmed synthetic incident for DOM integration test.';submit('#case-form');
 await wait(()=>!$('#case-dialog').hasAttribute('open'),'case save');checks.push('Case assignment, notes and confirmed resolution');
 click('button.nav-item[data-tab="model"]');await wait(()=>$('#model-rows tr')&&$('.drift-item'),'model and monitoring');if($('#drift-content').textContent.includes('undefined')||!$('#drift-content').textContent.includes('PSI')||!$('#drift-content').textContent.includes('JS'))throw new Error('Distribution diagnostics did not render');checks.push('Measured model comparison and numeric/categorical diagnostics render');
 click('button.nav-item[data-tab="overview"]');click('#tab-overview button[data-tab="score"]');submit('#score-form');await wait(()=>$('#score-result').textContent.includes('ASSESSMENT COMPLETE'),'single scoring');await wait(()=>!$('#score-form button').disabled,'scoring refresh complete');checks.push('Single scoring form receives and renders API assessment');
 submit('#score-form');await wait(()=>$('#score-result').textContent.includes('EXISTING ASSESSMENT'),'replay');await wait(()=>!$('#score-form button').disabled,'replay refresh complete');checks.push('Duplicate form submission shows existing assessment');
 const report={checks,errors,scope:'jsdom 26 DOM interactions against a live local HTTP API; canvas and dialog primitives stubbed. Not browser rendering, CSP execution or responsive-layout verification.'};
 fs.writeFileSync('reports/ui-dom-check.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));dom.window.close();
 if(errors.length)process.exitCode=1;
}
main().catch(e=>{console.error(e);process.exitCode=1;});
