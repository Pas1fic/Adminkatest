'use strict';
const API=(()=>{
 const PAGE=10;
 let admin=null,csrf='',pendingLogin='',lastAction=Date.now();
 const error=(message,code=0)=>Object.assign(new Error(message),{code});
 async function request(path,{method='GET',body,auth=true}={}){
  const headers={'Accept':'application/json'};
  if(body!==undefined)headers['Content-Type']='application/json';
  if(auth&&csrf&&method!=='GET')headers['X-CSRF-Token']=csrf;
  const response=await fetch(path,{method,headers,credentials:'same-origin',body:body===undefined?undefined:JSON.stringify(body)});
  if(response.status===204)return{};
  const type=response.headers.get('content-type')||'';
  const result=type.includes('application/json')?await response.json():{};
  if(!response.ok)throw error(result.message||result.error||'Ошибка сервера',response.status);
  lastAction=Date.now();
  return result;
 }
 const moduleName=name=>name==='journal'?'audit':name;
 const can=section=>!!admin&&(admin.role==='super'||(admin.permissions||[]).includes(moduleName(section)));
 return{
  async init(){
   try{const result=await request('/api/auth/me');admin={...result.admin,permissions:result.permissions||[]};csrf=result.csrf||'';return admin}
   catch(e){if(e.code===401){admin=null;csrf='';return null}throw e}
  },
  can,
  me:()=>admin&&{login:admin.username,role:admin.role,email:admin.email,id:admin.id},
  left:()=>admin?Math.max(0,30*60-Math.floor((Date.now()-lastAction)/1000)):0,
  touch(){if(admin)lastAction=Date.now()},
  async login(username,password){
   await request('/api/auth/login',{method:'POST',auth:false,body:{username,password}});
   pendingLogin=username;
  },
  async verify(code){
   const result=await request('/api/auth/verify',{method:'POST',auth:false,body:{username:pendingLogin,code}});
   admin={...result.admin,permissions:result.permissions||[]};csrf=result.csrf;pendingLogin='';
  },
  async logout(){
   try{if(admin)await request('/api/auth/logout',{method:'POST'})}
   finally{admin=null;csrf='';pendingLogin=''}
  },
  async list(module,options={}){
   const params=new URLSearchParams();
   if(options.q)params.set('q',options.q);
   if(options.field)params.set('field',options.field);
   params.set('page',String(options.page||1));
   for(const[key,value]of Object.entries(options.f||{}))if(value)params.set('f.'+key,value);
   if(options.all)params.set('all','1');
   if(options.from&&options.dk){params.set('from',options.from);params.set('dk',options.dk)}
   const result=await request(`/api/${moduleName(module)}?${params}`);
   const rows=result.items||[];
   return{rows,total:result.total??rows.length,pages:Math.max(1,Math.ceil((result.total??rows.length)/(result.limit||PAGE)))};
  },
  async save(module,id,values){
   await request(`/api/${moduleName(module)}`,{method:'POST',body:{...values,id}});
  },
  async reauthenticate(password){
   await request('/api/auth/reauth',{method:'POST',body:{password}});
  },
  async add(module,values){
   await request(`/api/${moduleName(module)}`,{method:'POST',body:values});
  },
  async del(module,id){
   await request(`/api/${moduleName(module)}/${id}`,{method:'DELETE'});
  },
  async act(module,id,action){
   await request(`/api/${moduleName(module)}/${id}/actions`,{method:'POST',body:{action}});
  },
  async userDetail(id){
   return request(`/api/users/${id}`);
  },
  async stats(){
   return request('/api/stats');
  },
  async profit(){
   return request('/api/profit');
  },
  async bulk(id,progress){
   if(!id)return(await request('/api/bulk')).operations;
   const result=await request('/api/bulk',{method:'POST',body:{id}});
   progress?.(result.affected||0);
  },
  async scan(){
   return request('/api/scan');
  },
  async saveScan(mapping){
   return request('/api/scan',{method:'POST',body:{mapping}});
  },
  async ask(text){
   const result=await request('/api/assistant',{method:'POST',body:{text}});
   return result;
  },
  async sendNewsletter(subject,body){
   return request('/api/newsletter/send',{method:'POST',body:{subject,body}});
  },
  async downloadAdminLog(id){
   const response=await fetch(`/api/admin-logs/${id}.txt`,{credentials:'same-origin'});
   if(!response.ok)throw error('Не удалось скачать журнал',response.status);
   const blob=await response.blob(),link=document.createElement('a');
   link.href=URL.createObjectURL(blob);link.download=`admin-${id}.txt`;link.click();
   setTimeout(()=>URL.revokeObjectURL(link.href),1000);
  }
 };
})();
