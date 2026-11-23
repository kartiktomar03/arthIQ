const $=s=>document.querySelector(s);
const pages=[
 {question:'Show total revenue by category.',name:'Revenue by category',rows:[['Home Office',315],['Kitchen',247],['Outdoor',220]],observation:'Home Office leads at $315. Kitchen follows at $247, with Outdoor contributing the remaining $220.'},
 {question:'What is Kitchen revenue?',name:'Kitchen revenue',rows:[['Kitchen',247]],observation:'Kitchen accounts for $247 of the $782 in category revenue.'},
 {question:'Compare Kitchen and Outdoor revenue.',name:'Kitchen vs Outdoor',rows:[['Kitchen',247],['Outdoor',220]],observation:'Kitchen generated $27 more revenue than Outdoor.'}
];
let entry=0,side=1,chapter='Category notebook',deleted=false,action='',lastRoute='',draft='';
const marked=new Set();
const esc=s=>s.replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=n=>String(n).padStart(2,'0');
const route=()=>['analysis','chapter'].includes(location.hash.slice(1))?location.hash.slice(1):'opening';
const head=(a,b)=>'<div class="running"><span>'+a+'</span><span>'+b+'</span></div>';
const leaf=(content,label,n)=>'<section class="leaf">'+content+'<div class="folio"><span>'+label+'</span><b>'+num(n)+'</b></div></section>';
function engraving(){
 let paths='';
 for(let i=0;i<18;i++){const d=i*2.9;paths+='<path d="M20 '+(75+d)+' Q85 '+(54+d)+' 150 '+(93+d)+' Q212 '+(50+d)+' 280 '+(51+d)+' L280 '+(49+d)+' Q211 '+(42+d)+' 150 '+(85+d)+' Q85 '+(43+d)+' 20 '+(66+d)+' Z"/>'}
 return '<svg class="engraving" viewBox="0 0 300 160" aria-hidden="true"><circle cx="205" cy="53" r="35" fill="#d8b76d"/><g stroke="#476d67" stroke-width="1.15" fill="#faf8ee">'+paths+'</g><path d="M205 96l15 -5v32l-8 -4 -7 7z" fill="#ab483f"/></svg>'
}
function opening(){
 const toc=pages.map((p,i)=>'<button class="toc" data-entry="'+i+'"><small>'+num(i+1)+'</small><span>'+p.name+'</span><i>↗</i></button>').join('');
 return leaf(head('The business journal','Index')+'<div class="kicker">Reader’s index</div><h1>Table of<br><em>Contents.</em></h1><h3>Recent entries</h3>'+toc+'<h3>Collected chapters</h3>'+(deleted?'<p>No chapters in this preview.</p>':'<a class="chapterlink" href="#chapter"><span class="flag"></span>'+esc(chapter)+' <i>→</i></a>'),'Contents',1)
 +leaf(head('Opening entry','ArthIQ')+engraving()+'<h2>Every Number<br><em>Has a Story.</em></h2><form id="query"><label for="question">Business question</label><textarea id="question" placeholder="Ask a question about your business…">'+esc(draft)+'</textarea><div class="formfoot"><small>Demo preview</small><button class="solid">Explore entry →</button></div></form><div class="examples">'+pages.map((p,i)=>'<button data-sample="'+i+'">'+p.name+' ↗</button>').join('')+'</div>','New entry',2)
}
function analysis(){
 const p=pages[entry],total=p.rows.reduce((a,r)=>a+r[1],0);
 const bars=p.rows.map(([name,v],i)=>'<div class="barrow"><span>'+name+'</span><div class="track"><i tabindex="0" title="'+name+': $'+v+'" style="width:'+v/350*100+'%;background:var(--s'+i+')"></i></div><b>$'+v+'</b></div>').join('');
 return leaf(head('Analysis entry','No. '+num(entry+1))+'<div class="kicker">The question</div><h1 class="question">'+p.question+'</h1><h3>Observation</h3><p class="observation">'+p.observation+'</p><p class="context">Measure: revenue in USD<br>Grouped by product category</p><details><summary>SQL reference</summary><p>This static example contains no executed SQL.</p></details><details><summary>Schema reference</summary><p>Displayed fields: category and revenue. No database metadata was retrieved.</p></details><div class="arrows"><button data-entry="'+(entry-1)+'" '+(!entry?'disabled':'')+'>← Previous entry</button><button data-entry="'+(entry+1)+'" '+(entry===2?'disabled':'')+'>Next entry →</button></div>','Analysis',3+entry*2)
 +leaf(head('Figure '+num(entry+1),'USD')+'<button class="ribbon" data-mark aria-pressed="'+marked.has(entry)+'">'+(marked.has(entry)?'Bookmarked':'Bookmark page')+'</button><div class="kicker">Revenue study</div><h2>'+p.name+'</h2><figure aria-label="Revenue in US dollars">'+bars+'<figcaption>Revenue · USD &nbsp; / &nbsp; Scale $0–350</figcaption></figure><table><thead><tr><th>Category</th><th>Revenue</th></tr></thead><tbody>'+p.rows.map(r=>'<tr><td>'+r[0]+'</td><td>$'+r[1]+'</td></tr>').join('')+'</tbody><tfoot><tr><th>Total</th><th>$'+total+'</th></tr></tfoot></table>','Results',4+entry*2)
}
function collection(){
 if(deleted)return leaf(head('Chapter library','Collection')+'<h1>My chapters.</h1><p>This chapter was removed from the preview.</p><button data-restore>Restore demo chapter</button>','Library',9)+leaf(head('Chapter pages','Index')+'<h2>No pages selected.</h2><a href="#opening">Back to contents →</a>','Contents',10)
 return leaf(head('Collected work','Chapter I')+'<div class="chapterseal">I</div><div class="kicker">Saved chapter · Three pages</div><h1>'+esc(chapter)+'</h1><p class="observation">A category-wide view of revenue, followed by a closer look at Kitchen and its comparison with Outdoor.</p><div class="arrows"><button class="solid" data-entry="0">Open chapter →</button><button data-edit="rename">Rename</button><button data-edit="delete">Delete</button></div>','Collection',9)
 +leaf(head('Chapter contents','Three analyses')+'<h2>Inside this <em>chapter.</em></h2><div class="chapterpages">'+pages.map((p,i)=>'<button data-entry="'+i+'"><span class="tab t'+i+'">'+num(i+1)+'</span><span><small>Analysis page</small><strong>'+p.name+'</strong><span>'+['Three categories · $782 total','Kitchen · $247','Kitchen $247 / Outdoor $220'][i]+'</span></span><i>↗</i></button>').join('')+'</div>','Chapter index',10)
}
function render(){
 const r=route();if(lastRoute!==r){side=r==='opening'?1:0;lastRoute=r}
 $('#book').innerHTML=({opening,analysis,chapter:collection})[r]();$('#book').dataset.side=String(side);
 document.querySelectorAll('nav a').forEach(a=>a.setAttribute('aria-current',a.hash==='#'+r?'page':'false'));
 const titles={opening:['Contents','New entry'],analysis:['Observation','Chart & results'],chapter:['Chapter overview','Chapter contents']};
 $('#flip').textContent=titles[r][1-side]+' →';
}
$('#flip').onclick=()=>{side=1-side;render();window.scrollTo(0,0)};
function openEntry(i){entry=i;side=0;location.hash='analysis';render();window.scrollTo(0,0)}
document.addEventListener('click',e=>{
 const b=e.target.closest('button');if(!b)return;
 if(b.hasAttribute('data-entry'))openEntry(Number(b.dataset.entry));
 if(b.hasAttribute('data-sample')){draft=pages[Number(b.dataset.sample)].question;$('#question').value=draft;$('#question').setCustomValidity('');$('#question').focus()}
 if(b.hasAttribute('data-mark')){marked.has(entry)?marked.delete(entry):marked.add(entry);render();document.querySelector('[data-mark]').focus()}
 if(b.hasAttribute('data-restore')){deleted=false;render()}
 if(b.dataset.edit){action=b.dataset.edit;$('#editor').returnValue='cancel';$('#name').hidden=action==='delete';$('#name').value=chapter;$('#dialogLabel').textContent=action==='delete'?'Delete this demo chapter?':'Chapter name';$('#dialogNote').textContent='Changes apply only to this preview session.';$('#confirm').textContent=action==='delete'?'Delete':'Rename';$('#editor').showModal()}
});
document.addEventListener('submit',e=>{if(e.target.id==='query'){e.preventDefault();const q=$('#question').value.trim();const i=pages.findIndex(p=>p.question===q);if(i<0&&q){$('#question').setCustomValidity('Choose one of the three examples to explore this preview.');$('#question').reportValidity()}else openEntry(i<0?0:i)}else if(e.submitter?.value==='ok'&&action==='rename'&&!$('#name').value.trim()){e.preventDefault();$('#name').focus()}});
$('#editor').onclose=()=>{if($('#editor').returnValue==='ok'){if(action==='rename')chapter=$('#name').value.trim();else deleted=true;render()}};
document.addEventListener('input',e=>{if(e.target.id==='question'){draft=e.target.value;e.target.setCustomValidity('')}});
window.addEventListener('hashchange',render);render();
