/* RealSense session lifecycle; never combine SDK depth with browser RGB. */
(function(root){
'use strict';
function pixel(x,y,width=320,height=240){return [Math.max(0,Math.min(width-1,Math.round(x))),Math.max(0,Math.min(height-1,Math.round(y)))];}
function range_text(range){
  if(range?.mm!=null)return (range.mm/1000).toFixed(3)+' m / '+Math.round(range.mm)+' mm';
  return range?.reason==='MIXED_SURFACES'?'边缘或多表面混合，请重新选点':'无有效深度，请调整距离或选点';
}
function create_client(fetcher=root.fetch.bind(root)){
  const state={token:null,opening:false,generation:0,frame:null};
  async function call(path,payload,signal,keepalive=false){
    const response=await fetcher('/api/depth/'+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),signal,keepalive});
    const result=await response.json();if(!response.ok)throw Error(result.error||'RGB-D 请求失败');return result;
  }
  async function open(){
    const version=++state.generation;state.opening=true;
    try{
      const result=await call('open',{});
      if(version!==state.generation){await call('close',{token:result.token}).catch(()=>{});throw Error('RGB-D 打开操作已取消');}
      state.token=result.token;return result;
    }finally{if(version===state.generation)state.opening=false;}
  }
  async function close(){
    state.generation++;state.opening=false;const token=state.token;state.token=null;state.frame=null;
    if(token)await call('close',{token},undefined,true).catch(()=>{});
  }
  async function frame(task,point,signal,options={}){
    if(!state.token)throw Error('请先打开 RGB-D 相机');const version=state.generation;
    const result=await call('frame',{...options,token:state.token,task,point},signal);
    if(version!==state.generation)throw Error('RGB-D 会话已变化');state.frame=result.frame_id;return result;
  }
  async function measure(point,signal,frameId=state.frame){
    const frame=frameId,version=state.generation;
    const result=await call('measure',{token:state.token,frame_id:frame,x:point[0],y:point[1]},signal);
    if(version!==state.generation||state.frame!==frame)return null;return result;
  }
  return {state,open,close,frame,measure};
}
const api={pixel,range_text,create_client};
if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.PickGoDepth=api;
})(typeof globalThis!=='undefined'?globalThis:this);
