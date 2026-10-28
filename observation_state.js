/* Read-only observation tracker and independent kinematic comparison. */
(function(root){
'use strict';
const S=typeof module!=='undefined'&&module.exports?require('./simulator-core.js'):root.RobotSim;
const CONFIG=Object.freeze({max_age_ms:2500,max_gap_ms:2000,min_frames:3,max_center_step_px:8,min_box_iou:.5});
function create_tracker(){return {frames:[],last:null,reason:'WAITING'};}
function reset_tracker(tracker,reason='WAITING'){tracker.frames=[];tracker.last=null;tracker.reason=reason;}
function box_iou(a,b){const width=Math.max(0,Math.min(a[2],b[2])-Math.max(a[0],b[0]));const height=Math.max(0,Math.min(a[3],b[3])-Math.max(a[1],b[1]));const intersection=width*height;return intersection/Math.max(1,(a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-intersection);}
function tracker_status(tracker,now){
  const last=tracker.last;
  if(!last)return {status:tracker.reason,consecutive:0,age_ms:null};
  const age=now-last.captured_mono_ms;
  if(!Number.isFinite(age)||age<0)return {status:'STALE',consecutive:0,age_ms:Math.max(0,Math.round(age))};
  if(last.source!=='camera')return {status:'FROZEN',consecutive:1,age_ms:Math.round(age)};
  if(age>CONFIG.max_age_ms)return {status:'STALE',consecutive:0,age_ms:Math.round(age)};
  const fresh=tracker.frames.filter(p=>now-p.captured_mono_ms>=0&&now-p.captured_mono_ms<=CONFIG.max_age_ms).length;
  return {status:fresh>=CONFIG.min_frames?'STABLE':'OBSERVING',consecutive:fresh,age_ms:Math.round(age)};
}
function update_tracker(tracker,observation,now){
  if(!observation){reset_tracker(tracker,'NO_TARGET');return tracker_status(tracker,now);}
  const o=observation;
  if(!Number.isFinite(o.captured_mono_ms)||!Array.isArray(o.center)||o.center.length!==2||!o.center.every(Number.isFinite)||!Array.isArray(o.box)||o.box.length!==4||!o.box.every(Number.isFinite)||o.box[2]<=o.box[0]||o.box[3]<=o.box[1])throw Error('Invalid observation');
  if((o.source==='camera'&&now-o.captured_mono_ms>CONFIG.max_age_ms)||now<o.captured_mono_ms){reset_tracker(tracker,'STALE');return tracker_status(tracker,now);}
  const old=tracker.last;
  if(old&&old.source_key===o.source_key&&old.frame_id===o.frame_id)return tracker_status(tracker,now);
  if(old&&old.source_key===o.source_key&&o.video_frame_token!==null&&o.video_frame_token!==undefined&&o.video_frame_token===old.video_frame_token)return tracker_status(tracker,now);
  if(old&&old.source_key===o.source_key&&o.captured_mono_ms<=old.captured_mono_ms)return tracker_status(tracker,now);
  tracker.frames=tracker.frames.filter(p=>now-p.captured_mono_ms<=CONFIG.max_age_ms);
  const matches=old&&now-old.captured_mono_ms<=CONFIG.max_age_ms&&old.label===o.label&&old.source_key===o.source_key&&o.captured_mono_ms>old.captured_mono_ms&&o.captured_mono_ms-old.captured_mono_ms<=CONFIG.max_gap_ms&&Math.hypot(o.center[0]-old.center[0],o.center[1]-old.center[1])<=CONFIG.max_center_step_px&&box_iou(o.box,old.box)>=CONFIG.min_box_iou;
  if(!matches)tracker.frames=[];
  tracker.last={...o};tracker.frames.push({...o});tracker.frames=tracker.frames.slice(-CONFIG.min_frames);
  // 限制整个窗口的累计漂移，防止每帧小移动被误认成静止。
  if(tracker.frames.some(p=>Math.hypot(p.center[0]-o.center[0],p.center[1]-o.center[1])>CONFIG.max_center_step_px))tracker.frames=[{...o}];
  return tracker_status(tracker,now);
}
function geometry_budget(y=.76,lift=.10,errorMm=2,speedMmS=20){
  if(![y,lift,errorMm,speedMmS].every(Number.isFinite)||y<.66||y>1.1||lift<.02||lift>.2||errorMm<0||errorMm>100||speedMmS<0||speedMmS>200)throw Error('Invalid geometry comparison parameters');
  const base={x:-1.48,y:.32,yaw:Math.PI/2},step=.0005,cap=.12;
  function check(targetY,all){try{S.ik(base,{x:base.x,y:targetY,z:.375});if(all)S.ik(base,{x:base.x,y:targetY,z:.375+lift});return true;}catch{return false;}}
  function margin(all){if(!check(y,all))return {feasible:false,margin_mm:0,censored:false};let last=0;for(let i=1;i<=Math.round(cap/step);i++){const d=i*step;if(!check(y-d,all)||!check(y+d,all))return {feasible:true,margin_mm:last*1000,censored:false};last=d;}return {feasible:true,margin_mm:last*1000,censored:true};}
  const grasp=margin(false),chain=margin(true);
  const remaining=Math.max(0,chain.margin_mm-errorMm);
  const horizon=!chain.feasible||remaining===0?0:speedMmS===0?null:remaining/speedMmS;
  return {kind:'independent-kinematic-example',target_y_m:y,lift_m:lift,initial_error_mm:errorMm,speed_bound_mm_s:speedMmS,grasp,three_key_poses:chain,recheck_estimate_s:horizon,
    advice:!chain.feasible?'示例关键位姿不可达，需调整停车位或任务条件':remaining===0?'假设误差已达到采样余量，建议复查':speedMmS===0?'速度界为零，不据此承诺无限有效期':'在假设误差/速度界下安排停车位复查；闭爪前仍需新观测',
    linked_to_camera:false,scope:'Sampled key-pose IK only; no continuous collision check or hardware guarantee'};
}
function strip_images(value){
  if(Array.isArray(value))return value.map(strip_images);
  if(value&&typeof value==='object'){const out={};for(const [key,item]of Object.entries(value)){if(['image','masks','depth_le_u16'].includes(key))continue;if(typeof item==='string'&&item.startsWith('data:image/'))continue;out[key]=strip_images(item);}return out;}
  return value;
}
const api={CONFIG,create_tracker,reset_tracker,update_tracker,tracker_status,geometry_budget,strip_images,box_iou};
if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.PickGoObservationState=api;
})(typeof globalThis!=='undefined'?globalThis:this);
