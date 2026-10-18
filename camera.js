/* Local USB / built-in camera helpers. No microphone, storage or hardware control. */
(function(scope){
  'use strict';
  function camera_error(name,message){const error=new Error(message);error.name=name;return error;}
  function stop_tracks(stream){if(stream)for(const track of stream.getTracks())track.stop();}
  function create_camera(video,devices){
    return {video,devices,stream:null,generation:0,opening:false,on_disconnect:null,cancel_open:null};
  }
  function close_camera(camera){
    const cancel=camera.cancel_open;camera.cancel_open=null;
    camera.generation++;camera.opening=false;if(cancel)cancel();
    const stream=camera.stream;camera.stream=null;
    camera.video.pause();camera.video.srcObject=null;stop_tracks(stream);
  }
  async function list_cameras(camera){
    if(!camera.devices?.enumerateDevices)return [];
    const devices=await camera.devices.enumerateDevices();
    return devices.filter(device=>device.kind==='videoinput').map((device,index)=>({
      id:device.deviceId,label:device.label||'摄像头 '+(index+1),
    }));
  }
  async function open_camera(camera,device_id='',timeout_ms=20000){
    close_camera(camera);
    if(!camera.devices?.getUserMedia)throw camera_error('NotSupportedError','此浏览器无法访问摄像头，请使用本机 Edge / Chrome 打开页面');
    const generation=camera.generation;camera.opening=true;
    let timer,stream,cancel;
    try{
      const acquisition=camera.devices.getUserMedia({audio:false,video:{
        width:{ideal:640},height:{ideal:480},frameRate:{ideal:15,max:30},
        ...(device_id?{deviceId:{exact:device_id}}:{}),
      }}).then(value=>{
        if(generation!==camera.generation){stop_tracks(value);throw camera_error('AbortError','摄像头请求已取消');}
        return value;
      });
      const timeout=new Promise((_,reject)=>{
        cancel=()=>reject(camera_error('AbortError','摄像头请求已取消'));camera.cancel_open=cancel;
        timer=setTimeout(()=>reject(camera_error('TimeoutError','等待摄像头授权超时，请关闭后重试')),timeout_ms);
      });
      stream=await Promise.race([acquisition,timeout]);
      camera.stream=stream;camera.video.srcObject=stream;
      for(const track of stream.getVideoTracks())track.addEventListener('ended',()=>{
        if(camera.stream!==stream)return;
        close_camera(camera);if(camera.on_disconnect)camera.on_disconnect();
      },{once:true});
      await Promise.race([camera.video.play(),timeout]);
      if(generation!==camera.generation)throw camera_error('AbortError','摄像头请求已取消');
      return stream.getVideoTracks()[0]?.getSettings?.()||{};
    }catch(error){
      stop_tracks(stream);
      if(generation===camera.generation)close_camera(camera);
      throw error;
    }finally{
      clearTimeout(timer);if(camera.cancel_open===cancel)camera.cancel_open=null;
      if(generation===camera.generation)camera.opening=false;
    }
  }
  function frame_layout(source_width,source_height,width,height,zoom=1){
    if(![source_width,source_height,width,height,zoom].every(Number.isFinite)||
      Math.min(source_width,source_height,width,height)<=0||zoom<1||zoom>3)throw Error('Invalid frame dimensions or zoom');
    const sw=source_width/zoom,sh=source_height/zoom,scale=Math.min(width/sw,height/sh);
    return {source:[(source_width-sw)/2,(source_height-sh)/2,sw,sh],
      destination:[(width-sw*scale)/2,(height-sh*scale)/2,sw*scale,sh*scale]};
  }
  function capture_camera(camera,context,width,height,zoom=1){
    const video=camera.video;
    if(!camera.stream||!camera.stream.getVideoTracks().some(track=>track.readyState==='live')||video.readyState<2)
      throw camera_error('NotReadableError','摄像头尚无可读取画面，请等待或重新打开');
    const layout=frame_layout(video.videoWidth,video.videoHeight,width,height,zoom);
    context.fillStyle='#383838';context.fillRect(0,0,width,height);
    context.drawImage(video,...layout.source,...layout.destination);
    return {source_size:[video.videoWidth,video.videoHeight],crop:layout.source,
      destination:layout.destination,captured_at_ms:Date.now()};
  }
  function error_message(error){
    const messages={
      NotAllowedError:'摄像头权限被拒绝。请在浏览器地址栏允许本站使用摄像头，并检查 Windows 相机隐私设置。',
      SecurityError:'浏览器禁止摄像头访问，请用本机 Edge / Chrome 打开 localhost 页面。',
      NotFoundError:'没有找到摄像头，请连接 USB 摄像头或检查内置摄像头。',
      NotReadableError:'摄像头画面无法读取，可能正被其他程序占用、已拔出或被系统禁止。',
      OverconstrainedError:'所选摄像头已不可用，请刷新设备列表，选择默认设备后重试。',
    };
    return messages[error.name]||error.message||'摄像头打开失败';
  }
  function camera_kind(label){
    // RealSense 的 RGB 接口名称中也含有 "Depth Camera"，优先检查接口后缀。
    if(/\brgb\s*(\([^)]*\))?\s*$/i.test(label))return 'rgb';
    if(/\b(depth|infrared|ir)\s*(\([^)]*\))?\s*$/i.test(label))return 'depth';
    return 'video';
  }
  const api=Object.freeze({create_camera,open_camera,close_camera,list_cameras,capture_camera,frame_layout,error_message,camera_kind});
  scope.PickGoCamera=api;
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
})(typeof globalThis!=='undefined'?globalThis:this);
