/* Suggestions and reports only. No robot commands, model downloads or camera opening. */
(function(root){
'use strict';
const A=root.PickGoObservationState;
function create_panel(callbacks){
  const $=id=>document.getElementById(id),tracker=A.create_tracker();
  let snapshot=null,selected=0,quality=null,available=false,busy=false,generation=0,active=null;
  let geometry=A.geometry_budget();
  const statusNames={WAITING:'等待新观测',NO_TARGET:'未检测到目标',STALE:'观测已过期',FROZEN:'冻结帧：不判断实时稳定性',OBSERVING:'正在收集连续新帧',STABLE:'连续三帧位置稳定',ERROR:'请求失败，需重新观察',SOURCE_CHANGED:'输入已变化',PAGE_HIDDEN:'页面暂停，需重新观察',CAMERA_CLOSED:'摄像头已关闭'};
  function object(){return snapshot?.objects[selected]||null;}
  function clear_quality(){quality=null;$('obs-quality').textContent='尚未评估';$('obs-details').textContent='';}
  function clear_frame(){generation++;if(active)active.abort();snapshot=null;selected=0;$('obs-review-label').value='unreviewed';clear_quality();render();}
  function reset(reason='SOURCE_CHANGED'){A.reset_tracker(tracker,reason);clear_frame();}
  function track(packet,item,source){
    if(!item)return A.update_tracker(tracker,null,performance.now());
    return A.update_tracker(tracker,{frame_id:packet.frame_id,source:source.kind,source_key:source.key,
      captured_mono_ms:packet.captured_mono_ms,video_frame_token:packet.video_frame_token,
      center:item.center,box:item.box,label:item.label},performance.now());
  }
  function select(index){
    if(!snapshot||!snapshot.objects[index]||selected===index)return;
    generation++;if(active)active.abort();selected=index;$('obs-review-label').value='unreviewed';clear_quality();A.reset_tracker(tracker);
    track(snapshot.packet,object(),snapshot.source);render();
  }
  function on_result(packet,result,source){
    if(document.hidden)return;
    let objects=result.objects||[];
    if(!result.objects&&result.found&&result.corners){
      const xs=result.corners.map(p=>p[0]),ys=result.corners.map(p=>p[1]);
      objects=[{label:result.color,score:null,center:result.center,box:[Math.min(...xs),Math.min(...ys),Math.max(...xs),Math.max(...ys)]}];
    }
    snapshot={packet:{...packet},result:A.strip_images(result),objects,source:{...source}};selected=0;
    track(packet,result.found?object():null,source);render();
  }
  function report(){
    if(!snapshot)return null;
    return {schema_version:1,application:'PickGo Lab',version:'0.5.0',exported_at:new Date().toISOString(),
      frame:{frame_id:snapshot.packet.frame_id,image_size:[snapshot.packet.width,snapshot.packet.height],
        frozen_at:new Date(snapshot.packet.timestamp_ms).toISOString(),source:snapshot.source.kind,
        note:'冻结/采集时间；上传照片的原始拍摄时间未知'},
      review_label:$('obs-review-label').value,temporal_state:A.tracker_status(tracker,performance.now()),
      selected_object:A.strip_images(object()),detection:snapshot.result,assessment:A.strip_images(quality),
      independent_geometry_example:geometry,robot_execution_authorized:false,
      limitations:['候选一致性不是准确率或独立观测','像素坐标未标定到机器人坐标','仿真示例与摄像头目标没有空间绑定','报告不包含图像或深度缓冲区']};
  }
  function update_report(){
    const value=report(),link=$('obs-report');
    if(!value){link.removeAttribute('href');link.setAttribute('aria-disabled','true');return;}
    link.href='data:application/json;charset=utf-8,'+encodeURIComponent(JSON.stringify(value,null,2));link.setAttribute('aria-disabled','false');
  }
  function render(){
    const state=A.tracker_status(tracker,performance.now());
    $('obs-temporal').textContent=busy?'正在处理新帧 / 评估中':(statusNames[state.status]||state.status);
    $('obs-age').textContent=state.age_ms===null?'—':state.age_ms+' ms · '+state.consecutive+' 帧';
    const item=object();$('obs-target').textContent=item?item.label+' · '+snapshot.packet.frame_id:'无当前目标';
    $('obs-assess').disabled=!available||busy||!item;
    if(!available)$('obs-advice').textContent='观测评估后端未就绪，请更新并重启服务。';
    else if(busy)$('obs-advice').textContent='等待当前处理完成。';
    else if(!item)$('obs-advice').textContent='先识别物体或完成手动框选分割，再评估所选区域。';
    else if(state.status==='STALE')$('obs-advice').textContent='当前是旧帧。分析仍可查看，实时判断需要重新拍摄。';
    else if(quality?.status==='REOBSERVE'||quality?.status==='NO_FOREGROUND'||quality?.status==='INCOMPLETE')$('obs-advice').textContent=quality.advice;
    else if(state.status==='STABLE'&&quality?.status==='CONSISTENT')$('obs-advice').textContent='当前连续帧位置稳定、候选分割较一致。尚未验证世界坐标、可达性或物理抓取。';
    else if(state.status==='FROZEN')$('obs-advice').textContent='可以分析冻结帧的分割敏感性；同一帧重复提交不计为连续观测。';
    else $('obs-advice').textContent='连续采集至少三张新帧检查位置变化；质量评估会暂停连续送检并使用当前同一帧。';
    update_report();
  }
  function render_geometry(){
    try{
      geometry=A.geometry_budget($('geometry-y').valueAsNumber,Number($('geometry-lift').value),$('geometry-error').valueAsNumber,$('geometry-speed').valueAsNumber);
      $('geometry-y-value').textContent=geometry.target_y_m.toFixed(3)+' m';
      const g=geometry.grasp,c=geometry.three_key_poses;
      $('geometry-result').textContent='抓取点余量 '+g.margin_mm.toFixed(1)+' mm'+(g.censored?'（扫描截断）':'')+'；三关键位姿共同余量 '+c.margin_mm.toFixed(1)+' mm'+(c.censored?'（扫描截断）':'')+'。复查时间估计：'+(geometry.recheck_estimate_s===null?'未计算（零速度界）':geometry.recheck_estimate_s.toFixed(3)+' s')+'。';
      $('geometry-advice').textContent=geometry.advice;
    }catch(error){geometry=null;$('geometry-result').textContent=error.message;$('geometry-advice').textContent='请填写有效的示例参数。';}
    update_report();
  }
  async function assess(){
    if(!available||busy||!object())return;
    const version=generation,item=object(),frame=snapshot.packet;
    const width=frame.width,height=frame.height;
    const roi=[Math.max(0,Math.floor(item.box[0])),Math.max(0,Math.floor(item.box[1])),Math.min(width,Math.ceil(item.box[2])),Math.min(height,Math.ceil(item.box[3]))];
    const request=new AbortController();if(!callbacks.begin(request))return;
    active=request;busy=true;clear_quality();$('obs-quality').textContent='评估中，使用当前冻结帧…';render();
    const timeout=setTimeout(()=>request.abort(),30000);
    try{
      const response=await fetch('/api/vision/assess',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({...frame,roi,tolerance_px:Number($('obs-tolerance').value),policy:$('obs-policy').value,max_samples:Number($('obs-budget').value)}),signal:request.signal});
      const value=await response.json();if(version!==generation)return;
      if(!response.ok)throw Error(value.error||'评估失败');
      if(value.frame_id!==frame.frame_id)throw Error('评估帧不匹配，已丢弃');
      quality={...value,evaluated_at:new Date().toISOString(),frame_age_at_assessment_ms:Math.round(performance.now()-frame.captured_mono_ms)};
      const names={CONSISTENT:'候选分割较一致',REOBSERVE:'建议补充观察',NO_FOREGROUND:'未得到有效前景',INCOMPLETE:'评估未完成'};
      $('obs-quality').textContent=(names[value.status]||value.status)+' · '+value.metrics.sample_count+'/'+value.max_samples+' 次候选 · '+value.elapsed_ms+' ms';
      const m=value.metrics;
      $('obs-details').textContent='最小候选 IoU：'+(m.min_pair_iou===null?'—':m.min_pair_iou.toFixed(3))+'；中心最大差：'+m.max_center_spread_px+' px；共同前景：'+m.core_area_px+' px；候选内部点：'+(m.candidate_surface_pixel?m.candidate_surface_pixel.join(' / '):'无')+'。停止原因：'+value.stop_reason+'。';
      if(m.candidate_surface_pixel)callbacks.point(m.candidate_surface_pixel);
    }catch(error){if(version===generation){clear_quality();$('obs-quality').textContent=error.name==='AbortError'?'评估已取消或超时':error.message;}}
    finally{clearTimeout(timeout);if(active===request)active=null;busy=false;callbacks.end(request);render();}
  }
  $('obs-assess').addEventListener('click',assess);
  for(const id of ['obs-policy','obs-budget','obs-tolerance'])$(id).addEventListener('change',()=>{generation++;if(active)active.abort();clear_quality();render();});
  $('obs-review-label').addEventListener('change',update_report);
  for(const id of ['geometry-y','geometry-lift','geometry-error','geometry-speed'])$(id).addEventListener('input',render_geometry);
  const ticker=setInterval(render,500);render_geometry();render();
  return {on_result,select,clear_frame,reset,set_busy:value=>{busy=value;render();},set_ready:value=>{available=!!value;render();},
    destroy:()=>{generation++;if(active)active.abort();clearInterval(ticker);}};
}
root.PickGoObservationUI={create_panel};
})(typeof globalThis!=='undefined'?globalThis:this);
