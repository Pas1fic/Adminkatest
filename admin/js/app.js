'use strict';
const $=document.getElementById('app'),root=document.documentElement;
const st={d:{},chat:[]}; // состояние в памяти: фильтры, страницы, чат. Живёт до конца сессии
let tm;
const h=(t,a={},...c)=>{const e=document.createElement(t);
 for(const k in a){const v=a[k];if(k.startsWith('on')){v&&e.addEventListener(k.slice(2),v)}else if(v!==false&&v!=null)e.setAttribute(k,v===true?'':v)}
 for(const x of c.flat(9)){if(x===false||x==null)continue;e.append(x.nodeType?x:String(x))}return e};
const ls=(k,v)=>{try{return v?localStorage.setItem(k,v):localStorage.getItem(k)}catch{}};
root.dataset.theme=ls('th')||(matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light');
const theme=()=>{root.dataset.theme=root.dataset.theme=='dark'?'light':'dark';ls('th',root.dataset.theme)};
addEventListener('pointerdown',()=>API.touch(),true);addEventListener('keydown',()=>API.touch(),true);

function toast(t){const e=h('div',{class:'toast',role:'status'},t);document.body.append(e);setTimeout(()=>e.remove(),3000)}
function dlg(...c){const d=h('dialog',{},...c);d.addEventListener('close',()=>d.remove());document.body.append(d);d.showModal();return d}
const ask=m=>new Promise(r=>{const d=dlg(h('h3',{},'Подтвердите действие'),h('p',{},m),h('div',{class:'row'},
 h('button',{class:'btn t',onclick:()=>d.close()},'Отмена'),h('button',{class:'btn',onclick:()=>{r(true);d.close()}},'Подтвердить')));
 d.addEventListener('close',()=>r(false))});
function fail(e){e.code==401?expire():toast(e.message||'Ошибка')}
async function expire(){clearInterval(tm);try{await API.logout()}catch(e){toast(e.message)}login('Сессия завершена или сервер недоступен. Войдите снова.')}

function formDlg(title,fields,labels,vals,ok){
 const ins={},required=Object.keys(vals).length===0;
 const rows=Object.entries(fields).map(([k,t])=>{let el;
  if(Array.isArray(t)){el=h('select',{},t.map(o=>h('option',{},o)));el.value=vals[k]??t[0]}
  else if(t=='bool'){el=h('input',{type:'checkbox'});el.checked=!!vals[k]}
  else if(t=='area'){el=h('textarea',{rows:4,required});el.value=vals[k]??''}
  else if(t=='image'){el=h('input',{type:'file',accept:'image/*'});}
  else if(t=='blob'){el=h('input',{type:'file'});}
  else{el=h('input',{type:t||'text',required});el.value=vals[k]??''}
  const fieldLabel=labels[k]||({image_data:'Изображение (уменьшится и сохранится в Base64)',
   password:'Пароль администратора',sections:'Разрешённые разделы через запятую'}[k]||k);
  ins[k]=el;return h('label',{class:'f'},h('span',{},fieldLabel),el)});
 const errorMessage=h('p',{class:'er','aria-live':'polite'});
 const d=dlg(h('form',{method:'dialog',onsubmit:async e=>{e.preventDefault();errorMessage.textContent='';
  try{const p={};
   for(const k in ins){const t=fields[k],v=ins[k];
    if(t=='bool')p[k]=v.checked;
    else if(t=='number')p[k]=Number(v.value);
    else if(t=='image'&&v.files[0])p[k]=await resizeImage(v.files[0]);
    else if(t=='blob'&&v.files[0])p[k]=await readBinaryFile(v.files[0]);
    else if(t!='image'&&t!='blob')p[k]=v.value.trim()}
   if(await ok(p)!==false)d.close()
  }catch(error){errorMessage.textContent=error.message||'Не удалось сохранить данные.'}
 }},h('h3',{},title),rows,errorMessage,
  h('div',{class:'row'},h('button',{type:'button',class:'btn t',onclick:()=>d.close()},'Отмена'),h('button',{class:'btn'},'Сохранить'))));
}
function readBinaryFile(file){return new Promise((resolve,reject)=>{const r=new FileReader();r.onerror=()=>reject(new Error('Не удалось прочитать файл.'));r.onload=()=>resolve(String(r.result).split(',')[1]||'');r.readAsDataURL(file)})}
function resizeImage(file){return new Promise((resolve,reject)=>{
 const reader=new FileReader();reader.onerror=()=>reject(new Error('Не удалось прочитать изображение.'));
 reader.onload=()=>{const image=new Image();image.onerror=()=>reject(new Error('Некорректное изображение.'));
  image.onload=()=>{const scale=Math.min(1,1600/image.width,1600/image.height),canvas=document.createElement('canvas');
   canvas.width=Math.max(1,Math.round(image.width*scale));canvas.height=Math.max(1,Math.round(image.height*scale));
   canvas.getContext('2d').drawImage(image,0,0,canvas.width,canvas.height);resolve(canvas.toDataURL('image/jpeg',.82))};
  image.src=reader.result};
 reader.readAsDataURL(file)
})}

function shell(title,body,back=true){
 const tmr=h('span',{class:'tm',title:'До автоматического выхода'});
 const tick=()=>{const s=API.left();if(s<=0)return expire();tmr.textContent='⏱ '+Math.floor(s/60)+':'+String(s%60).padStart(2,'0')};
 clearInterval(tm);tm=setInterval(tick,1000);tick();
 $.replaceChildren(h('header',{class:'top'},back&&h('button',{class:'btn t',onclick:pageMenu},'← В меню'),h('b',{class:'ttl'},title),h('span',{class:'sp'}),tmr,
  h('button',{class:'ib',title:'Светлая / тёмная тема','aria-label':'Сменить тему',onclick:theme},'◐'),
  h('button',{class:'btn t',onclick:async()=>{clearInterval(tm);try{await API.logout()}catch(e){toast(e.message)}login()}},'Выйти')),h('main',{},body));
}

/* ---------- Вход ---------- */
function stub(){ // нейтральная страница площадки; 10 нажатий за 4 с на иконку профиля открывают запрос кода
 let t=[];
 const ic=h('button',{class:'ib','aria-label':'Профиль',onclick:()=>{const n=Date.now();t=t.filter(x=>n-x<4000);t.push(n);if(t.length>=10){t=[];gate()}}},'👤');
 $.replaceChildren(h('header',{class:'top'},h('b',{class:'ttl'},'Площадка'),h('span',{class:'sp'}),ic),
  h('main',{},h('div',{class:'card'},h('h2',{},'Каталог'),h('p',{class:'mt'},'Здесь будет витрина площадки.'))));
}
function gate(){const i=h('input',{type:'password',inputmode:'numeric',autocomplete:'off','aria-label':'Код доступа'});
 const d=dlg(h('form',{method:'dialog',onsubmit:e=>{e.preventDefault();d.close();if(i.value===CODE)login()}},h('p',{},'Код доступа'),i,h('button',{class:'btn'},'OK')))}
function authCard(title,note,fields,onok,hint){
 const er=h('p',{class:'er',role:'alert'},note||'');
 const f=h('form',{class:'card auth',onsubmit:async e=>{e.preventDefault();try{await onok(...fields.map(x=>x.value))}catch(x){er.textContent=x.message}}},
  h('h2',{},title),fields.map(x=>h('label',{class:'f'},h('span',{},x.dataset.l),x)),er,h('button',{class:'btn'},'Далее'),hint&&h('p',{class:'mt'},hint));
 $.replaceChildren(h('main',{class:'c'},f));fields[0].focus();
}
function login(note){clearInterval(tm);
 const u=h('input',{required:true,autocomplete:'username','data-l':'Логин'}),p=h('input',{type:'password',required:true,autocomplete:'current-password','data-l':'Пароль'});
 authCard('Вход',note,[u,p],async(l,pw)=>{await API.login(l,pw);code()},'Введите учётные данные администратора.');
}
function code(){const c=h('input',{required:true,inputmode:'numeric',autocomplete:'one-time-code','data-l':'Код из письма'});
 authCard('Подтверждение',0,[c],async v=>{await API.verify(v);route()},'В режиме разработки код выводится в консоль сервера.')}

/* ---------- Меню и разделы ---------- */
const GROUPS=[
 {t:'Поддержка',i:'🎧',d:'Обращения пользователей и жалобы',page:'support',items:['support','complaints']},
 {t:'Информация обо всём',i:'🧭',d:'Пользователи, лоты и магазины',page:'info',items:['users','lots','shops']},
 {t:'Добавление контента',i:'✨',d:'Баннеры, новости и курсы валют',page:'content',items:['banners','news','currencies']}
];
const ADMIN_HOME=['users','lots','news','complaints','support','shops','currencies','newsletter'];
const MODULE_PAGES={promotion:'finance',profit:'finance',refunds:'finance',stats:'analytics',transactions:'analytics',
 newsletter:'system',journal:'system',admins:'system',scan:'system',bulk:'system',assistant:'system',project_data:'system'};
function moduleTiles(keys){return h('div',{class:'tiles'},keys.filter(k=>API.can(k)).map(k=>{
 const s=SEC[k];return h('button',{class:'tile',onclick:()=>location.href='/admin/'+(GROUPS.find(g=>g.items.includes(k))?.page||MODULE_PAGES[k]||'')+'/index.html?module='+encodeURIComponent(k)},h('span',{class:'ic'},s.i),s.t)
}))}
function menu(){
 if(API.me().role!=='super')return shell('Меню · '+API.me().login,moduleTiles(ADMIN_HOME),false);
 const grouped=new Set(GROUPS.flatMap(g=>g.items));
 const groups=GROUPS.map(g=>h('button',{class:'tile group-tile',onclick:()=>location.href='/admin/'+g.page+'/index.html'},
  h('span',{class:'ic'},g.i),h('span',{class:'group-copy'},h('b',{},g.t),h('small',{},g.d))));
 const other=Object.keys(SEC).filter(k=>!grouped.has(k)&&k!=='refunds'&&API.can(k));
 const locked=h('button',{class:'tile disabled-tile',disabled:true,title:'Раздел временно неактивен'},
  h('span',{class:'ic'},SEC.refunds.i),h('span',{},SEC.refunds.t),h('small',{},'Временно неактивно'));
 shell('Меню · '+API.me().login,h('div',{class:'menu-groups'},h('div',{class:'tiles'},groups),
  h('h2',{class:'section-title'},'Инструменты администратора'),
  h('div',{class:'tiles'},[...moduleTiles(other).children,locked])),false)
}
function pageMenu(){location.href='/admin/'}
function route(){
 const page=document.body.dataset.adminPage;
 if(!page)return menu();
 const group=GROUPS.find(item=>item.page===page),config=window.ADMIN_PAGE_CONFIG||{};
 const keys=config.modules||group?.items||({
  finance:['promotion','profit','refunds'],
  analytics:['stats','transactions'],
  system:['newsletter','journal','admins','scan','bulk','assistant']
 }[page]||[]);
 const selected=new URLSearchParams(location.search).get('module');
 if(selected&&keys.includes(selected)&&API.can(selected))return open(selected);
 const available=keys.filter(k=>API.can(k)||k==='refunds');
 const tiles=moduleTiles(available.filter(k=>k!=='refunds'));
 if(available.includes('refunds'))tiles.append(h('button',{class:'tile disabled-tile',disabled:true},
  h('span',{class:'ic'},SEC.refunds.i),h('span',{},SEC.refunds.t),h('small',{},'Временно неактивно')));
 shell(config.title||group?.t||({finance:'Финансы',analytics:'Аналитика',system:'Администрирование'}[page]||'Меню'),
  h('div',{},(config.description||group?.d)&&h('p',{class:'group-lead mt'},config.description||group.d),tiles),true)
}
function open(k){
 if(k==='profit')return unlockProfit();

 const box=h('div');shell(SEC[k].t,box);({bulk,assistant,profit,stats,scan}[k]||listView)(k,box)
}
async function unlockProfit(){
 formDlg('Подтвердите пароль',{password:'password'},{password:'Пароль'}, {},async data=>{
  try{await API.reauthenticate(data.password);const box=h('div');shell(SEC.profit.t,box);profit('profit',box)}
  catch(e){if(e.message.includes('Сессия'))fail(e);else toast(e.message);return false}
 })
}

const GOOD=/^(active|done|accepted)$/i,BAD=/^(blocked|rejected|new|pending)$/i;
const cell=v=>{
 if(typeof v==='boolean')return v?'\u2713':'\u2014';
 if(typeof v==='string'&&['none','null','undefined'].includes(v.trim().toLowerCase()))return '\u2014';
 if(typeof v==='string'&&v.startsWith('data:image/'))return h('img',{class:'table-thumb',src:v,alt:'\u0418\u0437\u043e\u0431\u0440\u0430\u0436\u0435\u043d\u0438\u0435',loading:'lazy'});
 if(typeof v==='string'&&(GOOD.test(v)||BAD.test(v)))return h('span',{class:'bd '+(GOOD.test(v)?'ok':'bad')},v);
 if(typeof v==='string'&&v.length>90)return h('span',{title:v},v.slice(0,87)+'\u2026');
 return v==null||v===''?'\u2014':v;
};

function listView(k,box){
 const s=SEC[k],co=s.co||k,d=st.d[k]??={q:'',page:1,f:{},from:''};
 const tw=h('div',{class:'tw'}),pg=h('div',{class:'pg'}),bar=h('div',{class:'bar'});let categoryFilter=null;
 const load=async()=>{try{const r=await API.list(co,{...d,dk:s.dk});if(k==='lots'){d.categories=r.categories||d.categories||[];if(categoryFilter){const current=d.category||'';categoryFilter.replaceChildren(h('option',{value:''},'\u0412\u0441\u0435 \u043a\u0430\u0442\u0435\u0433\u043e\u0440\u0438\u0438'),...(d.categories||[]).map(v=>h('option',{value:v.name},v.name+' ('+v.count+')')));categoryFilter.value=current}}draw(r)}catch(e){fail(e)}};
 const btn=(t,on,fn)=>h('button',{class:'btn t',disabled:!on,onclick:fn},t);
 const edit=r=>formDlg('Запись #'+r.id,s.e,s.c,r,async p=>{try{await API.save(co,r.id,p);toast('Сохранено');load()}catch(e){fail(e);return false}});
 const detail=r=>{
  if(['users','shops','lots'].includes(k)){
   const title=k==='users'?'\u041f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044c':k==='shops'?'\u041c\u0430\u0433\u0430\u0437\u0438\u043d':'\u041b\u043e\u0442';
   const fields=Object.entries(r).filter(([key,value])=>value!=null&&value!==''&&String(value).toLowerCase()!=='none'&&!['null','undefined'].includes(String(value).toLowerCase())).map(([key,value])=>{
    const label=s.c[key]||key;
    if(typeof value==='string'&&value.startsWith('data:image/'))return h('div',{class:'record-media'},h('b',{},label),h('img',{class:'record-image',src:value,alt:label,loading:'lazy'}));
    let shown=value;
    if(typeof value==='string'&&/^[\[{]/.test(value)){try{shown=JSON.stringify(JSON.parse(value),null,2)}catch{}}
    return h('div',{class:'pd-field'},h('b',{},label),h('span',{},String(shown)));
   });
   const d=dlg(h('div',{class:'record-head'},h('h3',{},title+' \u00b7 #'+r.id),h('span',{class:'mt'},k==='shops'?(r.name||'')+' '+(r.surname||'')+' \u00b7 \u0432\u043b\u0430\u0434\u0435\u043b\u0435\u0446':'\u041f\u043e\u0434\u0440\u043e\u0431\u043d\u0430\u044f \u0438\u043d\u0444\u043e\u0440\u043c\u0430\u0446\u0438\u044f')),
    h('div',{class:'pd-detail'},fields.length?fields:h('p',{class:'mt'},'\u041d\u0435\u0442 \u0437\u0430\u043f\u043e\u043b\u043d\u0435\u043d\u043d\u044b\u0445 \u0434\u043e\u043f\u043e\u043b\u043d\u0438\u0442\u0435\u043b\u044c\u043d\u044b\u0445 \u043f\u043e\u043b\u0435\u0439.')),
    h('div',{class:'row'},h('button',{class:'btn t',onclick:()=>d.close()},'\u0417\u0430\u043a\u0440\u044b\u0442\u044c')));
   d.classList.add('record-dialog');
  }else if(s.e)edit(r)
 };
 const run=(label,r,fn)=>async()=>{if(await ask(label+' · запись #'+r.id+'?'))try{await fn();toast('Готово');load()}catch(e){fail(e)}};
 const draw=r=>{const cols=Object.keys(s.c).filter(c=>(!r.columns||r.columns.includes(c))&&!(s.hide||[]).includes(c)),has=s.act||s.del||s.logs;d.page=Math.min(d.page,r.pages);
  tw.replaceChildren(h('table',{},h('thead',{},h('tr',{},cols.map(c=>h('th',{},s.c[c])),has&&h('th',{},''))),
   h('tbody',{},r.rows.length?r.rows.map(r=>h('tr',{class:s.e||['users','shops','lots'].includes(k)?'cl':'',onclick:(s.e||['users','shops','lots'].includes(k))&&(()=>detail(r))},cols.map(c=>h('td',{},cell(r[c]))),
    has&&h('td',{onclick:e=>e.stopPropagation()},(s.act||[]).map(([a,l])=>h('button',{class:'btn t sm',onclick:run(l,r,()=>API.act(co,r.id,a))},l)),
     s.del&&h('button',{class:'btn t sm',onclick:run('Удалить',r,()=>API.del(co,r.id))},'Удалить'),
     s.logs&&h('button',{class:'btn t sm',onclick:()=>API.downloadAdminLog(r.id).catch(fail)},'TXT')))):
    h('tr',{},h('td',{colspan:cols.length+1},'Ничего не найдено. Измените поиск или фильтры.')))));
  pg.replaceChildren(btn('←',d.page>1,()=>{d.page--;load()}),h('span',{},`стр. ${d.page} из ${r.pages} · всего ${r.total}`),btn('→',d.page<r.pages,()=>{d.page++;load()}))};
 if(s.q){const q=h('input',{type:'search',placeholder:'Поиск: '+s.q,'aria-label':'Поиск'});q.value=d.q;let t;
  q.oninput=()=>{clearTimeout(t);t=setTimeout(()=>{d.q=q.value;d.page=1;load()},250)};bar.append(q)}
 if(k==='lots'){categoryFilter=h('select',{'aria-label':'\u041a\u0430\u0442\u0435\u0433\u043e\u0440\u0438\u044f \u043b\u043e\u0442\u043e\u0432'},h('option',{value:''},'\u0412\u0441\u0435 \u043a\u0430\u0442\u0435\u0433\u043e\u0440\u0438\u0438'));categoryFilter.value=d.category||'';categoryFilter.onchange=()=>{d.category=categoryFilter.value;d.page=1;load()};bar.append(categoryFilter)} for(const[fk,o]of Object.entries(s.f||{})){const f=h('select',{'aria-label':s.c[fk]},h('option',{value:''},s.c[fk]+': все'),o.map(v=>h('option',{},v)));
  f.value=d.f[fk]||'';f.onchange=()=>{d.f[fk]=f.value;d.page=1;load()};bar.append(f)}
 if(s.dk){const f=h('input',{type:'date','aria-label':'С даты',title:'С даты'});f.value=d.from;f.onchange=()=>{d.from=f.value;d.page=1;load()};bar.append(f)}
 if(s.a)bar.append(h('button',{class:'btn',onclick:()=>formDlg('Добавить',s.a,s.c,k==='admins'?{sections:ADMIN_HOME.join(',')}:(s.defaults||{}),async p=>{try{await API.add(co,p);toast('Добавлено');load()}catch(e){fail(e);return false}})},'+ Добавить'));
 if(s.x)bar.append(h('button',{class:'btn t',onclick:async()=>{try{const{rows}=await API.list(co,{...d,all:true,dk:s.dk}),cols=Object.keys(s.c);
  const csv=[cols.map(c=>s.c[c]),...rows.map(r=>cols.map(c=>r[c]))].map(r=>r.map(v=>'"'+String(v).replaceAll('"','""')+'"').join(',')).join('\n');
  const a=h('a',{href:URL.createObjectURL(new Blob(['\ufeff'+csv],{type:'text/csv'})),download:co+'.csv'});a.click();URL.revokeObjectURL(a.href)}catch(e){fail(e)}}},'Экспорт CSV'));
 box.append(bar,tw,pg);load();
}

async function projectDataView(box){
 const bar=h('div',{class:'bar'}),area=h('div'),pager=h('div',{class:'pg'});
 const tableSelect=h('select',{'aria-label':'\u0422\u0430\u0431\u043b\u0438\u0446\u0430 Project Data'}),search=h('input',{type:'search',placeholder:'\u041f\u043e\u0438\u0441\u043a \u043f\u043e \u0432\u0441\u0435\u043c \u043f\u043e\u043b\u044f\u043c'});
 const state={table:'',q:'',page:1,tables:[]};
 const showDetail=row=>{
  const fields=Object.entries(row).map(([key,value])=>h('div',{class:'pd-field'},h('b',{},key),h('span',{},value===null?'NULL':String(value))));
  const d=dlg(h('h3',{},'\u0417\u0430\u043f\u0438\u0441\u044c - '+state.table+' - #'+(row.id??'?')),
   h('div',{class:'pd-detail'},fields),
   h('div',{class:'row'},h('button',{class:'btn t',onclick:()=>d.close()},'\u0417\u0430\u043a\u0440\u044b\u0442\u044c')));
 };
 const load=async()=>{try{
  const r=await API.list('project_data',{table:state.table,q:state.q,page:state.page});
  if(!state.table){state.tables=r.tables;tableSelect.replaceChildren(...r.tables.map(t=>h('option',{value:t.name},t.name+' | '+t.count)));state.table=r.tables[0]?.name||'';tableSelect.value=state.table;if(state.table)return load();}
  const cols=r.columns,visible=cols.slice(0,7);
  area.replaceChildren(h('p',{class:'mt'},'\u0422\u0430\u0431\u043b\u0438\u0446\u0430: '+state.table+' | \u043f\u043e\u043b\u0435\u0439: '+cols.length+' | \u0437\u0430\u043f\u0438\u0441\u0435\u0439: '+r.total+' | \u041d\u0430\u0436\u043c\u0438\u0442\u0435 \u043d\u0430 \u0441\u0442\u0440\u043e\u043a\u0443, \u0447\u0442\u043e\u0431\u044b \u043f\u0440\u043e\u0441\u043c\u043e\u0442\u0440\u0435\u0442\u044c \u0432\u0441\u0435 \u043f\u043e\u043b\u044f.'),
   h('div',{class:'tw'},h('table',{},h('thead',{},h('tr',{},visible.map(c=>h('th',{},c)),h('th',{},'\u0412\u0441\u0435 \u043f\u043e\u043b\u044f'))),
    h('tbody',{},r.rows.length?r.rows.map(row=>h('tr',{class:'cl',onclick:()=>showDetail(row)},visible.map(c=>h('td',{},row[c]===null?'NULL':String(row[c]??''))),h('td',{},'\u041e\u0442\u043a\u0440\u044b\u0442\u044c >'))):h('tr',{},h('td',{colspan:visible.length+1},'\u0417\u0430\u043f\u0438\u0441\u0435\u0439 \u043d\u0435\u0442.'))))));
  pager.replaceChildren(h('button',{class:'btn t',disabled:state.page<=1,onclick:()=>{state.page--;load()}},'Prev'),h('span',{},`\u0421\u0442\u0440. ${r.page||state.page} \u0438\u0437 ${r.pages} | \u0432\u0441\u0435\u0433\u043e ${r.total}`),h('button',{class:'btn t',disabled:state.page>=(r.pages||1),onclick:()=>{state.page++;load()}},'Next'));
 }catch(e){fail(e)}};
 tableSelect.onchange=()=>{state.table=tableSelect.value;state.page=1;load()};
 let timer;search.oninput=()=>{clearTimeout(timer);timer=setTimeout(()=>{state.q=search.value;state.page=1;load()},250)};
 bar.append(tableSelect,search);box.append(bar,area,pager);load();
}

async function stats(k,box){try{const r=await API.stats();
 const max=Math.max(1,...r.items.map(([,v])=>Number(v)||0));
 box.append(h('p',{class:'mt'},'Показатели рассчитаны по данным, доступным в подключённых разделах панели.'),h('div',{class:'cards'},r.items.map(([l,v])=>h('div',{class:'card st'},h('b',{},v),h('span',{},l),
  h('progress',{class:'stat-progress',max,value:Number(v)||0,'aria-label':l}))))) }catch(e){fail(e)}}

async function profit(k,box){try{const r=await API.profit();
 box.append(h('p',{class:'mt'},'Пока нет подключённых финансовых данных. Суммы не являются фактической выручкой.'),
  h('section',{class:'card'},h('h3',{},'Рекламные баннеры'),
   h('div',{class:'cards'},(r.banners||[]).map(item=>h('article',{class:'card st'},h('b',{},item.total),
    h('span',{},item.title),h('p',{class:'mt'},`Оплачено: ${item.paid} · Доход сегодня: 0 ₽`))))),
  h('div',{class:'cards'},[
   ['Оборот по лотам',r.lot_turnover],
   ['Чистая прибыль с лотов',r.lot_profit]
  ].map(([title,value])=>h('article',{class:'card st'},h('b',{},value+' ₽'),h('span',{},title))),
  API.me().role==='super'&&h('article',{class:'card st'},h('b',{},r.free_money+' ₽'),h('span',{},'Свободные деньги'))))}catch(e){fail(e)}}

async function userDetail(row){
 try{const result=await API.userDetail(row.id),user=result.user,activity=result.activity;
  const d=dlg(h('h3',{},'Профиль пользователя · '+(user.nick||user.id)),
   h('p',{class:'mt'},'Данные профиля. Подробная карточка загружается по запросу.'),
   h('div',{class:'cards'},Object.entries({Email:user.email||'—',ID:user.id,Статус:user.status||'—',
    'Баланс':user.balance??'—','Лоты':activity.lots,'Магазины':activity.shops,
    'Жалобы':activity.complaints,'Обращения':activity.support}).map(([label,value])=>
      h('div',{class:'card st'},h('b',{},value),h('span',{},label)))),
   h('div',{class:'row'},h('button',{class:'btn t',onclick:()=>d.close()},'Закрыть'),
    h('button',{class:'btn',onclick:()=>{d.close();formDlg('Редактировать пользователя',SEC.users.e,SEC.users.c,user,async values=>{
     try{await API.save('users',user.id,values);toast('Сохранено')}catch(e){fail(e);return false}
    })}},'Редактировать')))
 }catch(e){fail(e)}
}

function newsletter(k,box){
 const form=h('form',{class:'card auth'},h('h3',{},'Рассылка подписчикам'),
  h('label',{class:'f'},'Тема письма',h('input',{name:'subject',required:true,maxlength:200})),
  h('label',{class:'f'},'Текст письма',h('textarea',{name:'body',rows:6,required:true})),
  h('p',{class:'mt'},'Письмо отправляется только адресам с активной подпиской. Нужна настройка SMTP.'),
  h('button',{class:'btn'},'Отправить подписчикам'));
 form.onsubmit=async e=>{e.preventDefault();const fd=new FormData(form),subject=fd.get('subject'),body=fd.get('body');
  if(!await ask('Отправить письмо всем активным подписчикам?'))return;
  try{const result=await API.sendNewsletter(subject,body);toast('Отправлено: '+result.sent);form.reset()}
  catch(error){fail(error)}
 };
 box.append(form)
}

async function bulk(k,box){try{const ops=await API.bulk();
 box.append(h('p',{class:'mt'},'Перед запуском показывается, сколько записей затронет операция. Выполняется пакетами по 10.'),
 ops.map(o=>h('div',{class:'card row2'},h('div',{},h('b',{},o.t),h('div',{class:'mt'},'Будет затронуто записей: '+o.n)),
  h('button',{class:'btn',disabled:!o.n,onclick:async()=>{
   if(!await ask(`«${o.t}»: будет затронуто записей: ${o.n}. Выполнить?`))return;
   const pr=h('progress',{max:o.n,value:0}),d=dlg(h('h3',{},o.t),pr);
   try{await API.bulk(o.id,n=>{pr.value=n});toast('Готово')}catch(e){fail(e)}
   d.close();box.replaceChildren();bulk(k,box)}},'Выполнить'))))}catch(e){fail(e)}}

async function scan(k,box){try{const r=await API.scan(),sel={};
 box.append(h('p',{class:'mt'},'Для каждого поля укажите, что это. Ответы запоминаются и при следующих сканированиях подставляются сами.'),
 Object.entries(r.tables).map(([t,fs])=>h('details',{class:'card',open:t=='users'},h('summary',{},t+' · полей: '+fs.length),
  fs.map(f=>{const s=h('select',{'aria-label':t+'.'+f},MEAN.map(m=>h('option',{},m)));s.value=r.saved[t+'.'+f]||MEAN[0];sel[t+'.'+f]=s;
   return h('label',{class:'f in'},h('code',{},f),s)}))),
 h('button',{class:'btn',onclick:async()=>{const m={};for(const x in sel)m[x]=sel[x].value;try{await API.saveScan(m);toast('Сохранено')}catch(e){fail(e)}}},'Сохранить ответы'))}catch(e){fail(e)}}

function assistant(k,box){
 if(!st.chat.length)st.chat.push({w:'b',t:'Здравствуйте! Спросите, где что найти или как выполнить действие. Я подскажу и открою нужный раздел.'});
 const log=h('div',{class:'chat','aria-live':'polite'}),inp=h('input',{placeholder:'Например: где жалобы?','aria-label':'Вопрос помощнику'});
 const draw=()=>log.replaceChildren(...st.chat.map(m=>h('div',{class:'m '+m.w},m.t,m.go&&API.can(m.go)&&h('div',{},h('button',{class:'btn',onclick:()=>open(m.go)},'Открыть: '+SEC[m.go].t)))));
 box.append(log,h('form',{class:'send',onsubmit:async e=>{e.preventDefault();const t=inp.value.trim();if(!t)return;inp.value='';
  st.chat.push({w:'u',t});draw();try{const r=await API.ask(t);st.chat.push({w:'b',...r});draw()}catch(x){fail(x)}}},inp,h('button',{class:'btn'},'Отправить')));
 draw();
}

async function boot(){
 try{
  await API.init();
  if(API.me()){
   if(document.body.hasAttribute('data-admin-entry')&&!document.body.dataset.adminPage)menu();
   else route();
  }else if(document.body.hasAttribute('data-admin-entry')||document.body.dataset.adminPage)login();
  else stub();
 }catch(error){
  if(document.body.hasAttribute('data-admin-entry')||document.body.dataset.adminPage)login('Не удалось подключиться к серверу: '+error.message);
  else stub();
 }
}
boot();
