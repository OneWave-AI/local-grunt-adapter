const $=id=>document.getElementById(id);
const token=new URLSearchParams(location.search).get('token');
let idleFrames=0;
const expanded=new Set();
const phases={preparing:'Preparing',loading:'Loading model',running:'Running',complete:'Complete',failed:'Failed',interrupted:'Interrupted',kept_with_caller:'Kept with cloud'};
const el=(tag,cls,text)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e};
const number=n=>(n||0).toLocaleString();
const duration=(start,end)=>{const s=Math.max(0,Math.floor(end-start));return s<60?s+'s':Math.floor(s/60)+'m '+s%60+'s'};
const seconds=n=>typeof n==='number'?(n<.01?'<0.01':n.toFixed(2))+'s':'—';
function detail(grid,title,value){const box=el('div');box.append(el('label','',title),el('strong','',value));grid.append(box)}
function render(data){
 const roi=data.usage?.roi;
 if(roi){const box=$("roi");box.replaceChildren();for(const [label,value] of [["Calls / accepted",roi.calls+" / "+roi.accepted],["Local input / output",number(roi.local_input_tokens)+" / "+number(roi.local_output_tokens)],["Estimated net cloud tokens",number(roi.estimated_net_cloud_tokens_saved)],["Measured net cloud tokens",roi.measured_net_cloud_tokens_saved===null?"No paired measurements":number(roi.measured_net_cloud_tokens_saved)],["Estimated net USD",roi.estimated_net_usd===null?"Configure rate":"$"+roi.estimated_net_usd.toFixed(4)],["ROI",roi.estimated_roi_percent===null?"Needs rate + local cost":roi.estimated_roi_percent+"%"],["Local processing",seconds(roi.local_elapsed_seconds)]]){const row=el("div","kv");row.append(el("span","",label),el("strong","",value));box.append(row)}}
 const jobs=data.jobs,active=jobs.filter(j=>j.finished===null),done=jobs.filter(j=>j.phase==='complete'),failed=jobs.filter(j=>['failed','interrupted'].includes(j.phase)),kept=jobs.filter(j=>j.phase==='kept_with_caller');
 for(const [id,count,unit] of [['running',active.length,active.length===1?'task':'tasks'],['completed',done.length,done.length===1?'task':'tasks'],['tokens',jobs.reduce((n,j)=>n+(j.output_tokens||0),0),'tokens'],['failures',failed.length,failed.length===1?'task':'tasks']])$(id).replaceChildren(document.createTextNode(number(count)),el('span','',unit));
 $('kept').textContent=number(kept.length);$('cache-hits').textContent=number(jobs.filter(j=>j.cached).length);$('reviewed').textContent=jobs.filter(j=>j.outcome).length+' / '+jobs.filter(j=>j.outcome==='accepted').length;$('input-tokens').textContent=number(jobs.reduce((n,j)=>n+(j.input_tokens||0),0));
 const complete=jobs.length>0&&active.length===0;
 $('headline').textContent=active.length?'Your local crew is on it.':complete?'The crew is all done.':'Ready when work arrives.';
 $('subtitle').textContent=active.length?'Focused work is running on your Mac. Every task has a visible trail.':complete?(failed.length?'Processing has stopped. Review the tasks that need attention.':'Local work has finished. Open any task to inspect how it ran.'):'Smart routing keeps small tasks with your cloud assistant.';
 $('orb').textContent=active.length?'↗':complete?'✓':'↗';$('orb').classList.toggle('running',active.length>0);document.body.classList.toggle('idle',complete);$('activity-label').textContent=active.length?'LIVE · '+active.length+' ACTIVE':complete?'FINISHED SNAPSHOT':'WAITING';
 const list=$('jobs');list.replaceChildren();if(!jobs.length)list.append(el('div','empty','Waiting for an eligible task. Small requests stay with your cloud assistant.'));
 for(const j of jobs){
  const status=j.finished===null?'active':j.phase==='complete'?'done':j.phase==='kept_with_caller'?'kept':'failed';
  const row=el('div','job '+status);row.append(el('div','icon',status==='active'?'↗':status==='done'?'✓':status==='kept'?'↗':'!'));
  const body=el('div');body.append(el('p','job-title',j.label),el('div','job-sub',j.model+(j.cached?' · cache hit':'')));
  const toggle=el('button','',expanded.has(j.id)?'Hide details −':'Show details +');toggle.setAttribute('aria-expanded',expanded.has(j.id));body.append(toggle);row.append(body);
  const state=el('div','state',phases[j.phase]||j.phase);state.append(el('small','',duration(j.started,j.finished||data.now)));row.append(state);
  const details=el('div','job-detail'+(expanded.has(j.id)?' open':''));
  details.append(el('p','reason',j.routing_reason||'Local worker requested by the caller.'));
  const grid=el('div','detail-grid');
  detail(grid,'Task type',j.task);detail(grid,'Source',j.source_mode?(j.source_mode+(j.file_count?' · '+j.file_count+' file'+(j.file_count>1?'s':''):'')):'—');detail(grid,'Input size',j.source_chars?number(j.source_chars)+' chars':'—');
  detail(grid,'Context allocation',j.context_tokens?number(j.context_tokens)+' tokens':'—');detail(grid,'Local input',number(j.input_tokens)+' tokens');detail(grid,'Local output',number(j.output_tokens)+' tokens');
  detail(grid,'Model load',j.cached?'cache hit':seconds(j.load_seconds));detail(grid,'Generation',j.cached?'no inference':seconds(j.generation_seconds));detail(grid,'Generation rate',!j.cached&&j.generation_seconds>0?((j.output_tokens||0)/j.generation_seconds).toFixed(1)+' tok/s':'—');
  details.append(grid);
  if(status!=='kept'){
   const stage=el('div','stage-line');const index=({preparing:0,loading:1,running:2,complete:3})[j.phase]??0;
   ['Prepare','Model','Generate','Done'].forEach((name,i)=>stage.append(el('span',i<=index?'reached':'',name)));details.append(stage);
   if(status==='done')details.append(el('div','review-pill'+(j.outcome?'':' pending'),j.outcome?'Caller review: '+j.outcome:'Awaiting caller review'));
  }
  if(j.error)details.append(el('p','reason',j.error));
  toggle.addEventListener('click',()=>{expanded.has(j.id)?expanded.delete(j.id):expanded.add(j.id);details.classList.toggle('open',expanded.has(j.id));toggle.textContent=expanded.has(j.id)?'Hide details −':'Show details +';toggle.setAttribute('aria-expanded',expanded.has(j.id))});
  row.append(details);list.append(row);
 }
 const loaded=data.loaded_models,names=new Set([...loaded.map(m=>m.name),...active.map(j=>j.model).filter(n=>n!=='Choosing model')]);
 $('model-count').textContent=loaded.length+' LOADED';$('models').replaceChildren();if(!names.size)$('models').append(el('div','job-sub','No model loaded. Models start only when needed.'));
 for(const name of names){const m=loaded.find(x=>x.name===name),running=active.some(j=>j.model===name);const box=el('div','model');box.append(el('div','model-name',name));const meta=el('div','model-meta'),state=el('span');state.append(el('i','dot'+(running?'':' idle')),document.createTextNode(running?'Working':m?'Loaded · idle':'Preparing'));meta.append(state,el('span','',m?(m.bytes/1073741824).toFixed(1)+' GiB':''));box.append(meta);if(m)box.append(el('div','model-runtime',[m.runner,m.quantization,m.context?number(m.context)+' context':''].filter(Boolean).join(' · ')));$('models').append(box)}
 $('memory').textContent=data.memory.available_gib.toFixed(1)+' / '+data.memory.total_gib.toFixed(0)+' GiB available';$('memory-bar').style.width=((1-data.memory.available_gib/data.memory.total_gib)*100)+'%';
 $('footer').textContent=complete?'Finished '+new Date(data.now*1000).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})+' · Monitoring paused · Safe to close':'Connected locally · Updating every second';
 $('close').textContent=active.length?'Hide panel ↗':'Close panel ↗';
 $('hint').textContent=complete?'Generation has stopped. Loaded models may remain warm briefly. Close this panel whenever you’re ready.':'Source text and results stay out of this panel. Task labels, routing decisions and runtime details appear here.';
 $('error').style.display=data.backend_available?'none':'block';if(!data.backend_available)$('error').textContent='Ollama is not responding. Existing task history remains available.';
 return complete;
}
async function update(){try{const response=await fetch('/api/state?token='+encodeURIComponent(token),{cache:'no-store'});if(!response.ok)throw Error('Connection unavailable');const complete=render(await response.json());idleFrames=complete?idleFrames+1:0;if(idleFrames<2)setTimeout(update,1000)}catch(e){$('error').style.display='block';$('error').textContent='The panel connection stopped. The next local task will reconnect it.';$('footer').textContent='Disconnected · Check the calling assistant for task status'}}
$('close').addEventListener('click',()=>{if(window.webkit?.messageHandlers?.closePanel)window.webkit.messageHandlers.closePanel.postMessage('close');else window.close()});
update();
