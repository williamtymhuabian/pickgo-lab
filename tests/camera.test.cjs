'use strict';
const assert=require('node:assert/strict');
const C=require('../camera.js');
let tests=0;
async function test(name,fn){await fn();tests++;console.log('PASS '+name);}
function fixture(getUserMedia){
  const track={readyState:'live',stops:0,stop(){this.stops++;this.readyState='ended';},
    addEventListener(name,fn){this[name]=fn;},getSettings(){return {width:640,height:480};}};
  const stream={getTracks:()=>[track],getVideoTracks:()=>[track]};
  const video={srcObject:null,videoWidth:640,videoHeight:480,readyState:2,pause(){},async play(){}};
  const devices={getUserMedia:getUserMedia||(()=>Promise.resolve(stream)),
    async enumerateDevices(){return [{kind:'audioinput',deviceId:'mic'},
      {kind:'videoinput',deviceId:'usb',label:'USB Camera'}];}};
  return {camera:C.create_camera(video,devices),track,stream,devices,video};
}
(async()=>{
  await test('只申请视频，支持指定设备并在关闭时释放',async()=>{
    const f=fixture();let constraints;f.devices.getUserMedia=async value=>{constraints=value;return f.stream;};
    await C.open_camera(f.camera,'usb');assert.equal(constraints.audio,false);
    assert.equal(constraints.video.deviceId.exact,'usb');assert.equal(f.video.srcObject,f.stream);
    C.close_camera(f.camera);assert.equal(f.track.readyState,'ended');assert.equal(f.video.srcObject,null);
  });
  await test('枚举时排除麦克风',async()=>assert.deepEqual(await C.list_cameras(fixture().camera),[{id:'usb',label:'USB Camera'}]));
  await test('RealSense 的彩色和深度接口正确区分',()=>{
    assert.equal(C.camera_kind('Intel(R) RealSense(TM) Depth Camera 435 with RGB Module RGB'),'rgb');
    assert.equal(C.camera_kind('Intel(R) RealSense(TM) Depth Camera 435 with RGB Module Depth'),'depth');
    assert.equal(C.camera_kind('RealSense Depth (8086:0b07)'),'depth');
    assert.equal(C.camera_kind('USB2.0 HD UVC WebCam'),'video');
  });
  await test('取消尚未完成的授权；迟到的流自动释放',async()=>{
    let resolve;const f=fixture(()=>new Promise(r=>resolve=r));
    const opening=C.open_camera(f.camera);C.close_camera(f.camera);
    await assert.rejects(opening,{name:'AbortError'});resolve(f.stream);
    await new Promise(r=>setImmediate(r));assert.equal(f.track.readyState,'ended');assert.equal(f.camera.stream,null);
  });
  await test('授权超时；迟到的流不重新打开相机',async()=>{
    let resolve;const f=fixture(()=>new Promise(r=>resolve=r));
    await assert.rejects(C.open_camera(f.camera,'',10),{name:'TimeoutError'});resolve(f.stream);
    await new Promise(r=>setImmediate(r));assert.equal(f.track.readyState,'ended');
  });
  await test('权限被拒绝和播放失败都可恢复',async()=>{
    const f=fixture(async()=>{throw Object.assign(Error('denied'),{name:'NotAllowedError'});});
    await assert.rejects(C.open_camera(f.camera),{name:'NotAllowedError'});
    assert.equal(f.camera.opening,false);assert.match(C.error_message({name:'NotAllowedError'}),/权限被拒绝/);
    f.devices.getUserMedia=async()=>f.stream;f.video.play=async()=>{throw Error('play failed');};
    await assert.rejects(C.open_camera(f.camera),/play failed/);assert.equal(f.track.readyState,'ended');
  });
  await test('拔出相机时释放设备并通知界面',async()=>{
    const f=fixture();let disconnected=0;f.camera.on_disconnect=()=>disconnected++;
    await C.open_camera(f.camera);f.track.ended();assert.equal(f.camera.stream,null);assert.equal(disconnected,1);
  });
  await test('送检图像等比缩放、中心裁剪，不制造深度',async()=>{
    assert.deepEqual(C.frame_layout(1280,720,320,240),{source:[0,0,1280,720],destination:[0,30,320,180]});
    assert.deepEqual(C.frame_layout(640,480,320,240,2),{source:[160,120,320,240],destination:[0,0,320,240]});
    const f=fixture();await C.open_camera(f.camera);let args;
    const result=C.capture_camera(f.camera,{fillRect(){},drawImage(...value){args=value;}},320,240,2);
    assert.equal(args[0],f.video);assert.deepEqual(result.crop,[160,120,320,240]);assert.equal('depth' in result,false);
    C.close_camera(f.camera);assert.throws(()=>C.capture_camera(f.camera,{},320,240),/尚无可读取/);
  });
  console.log(JSON.stringify({tests,status:'passed'}));
})().catch(error=>{console.error(error);process.exitCode=1;});
