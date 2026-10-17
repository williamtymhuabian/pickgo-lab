const assert = require('node:assert/strict');
const S = require('../simulator-core.js');
let checks=0;
function test(name,fn){fn();checks++;console.log('PASS '+name);}
test('离线单文件与独立仿真核心一致，无外部资源',()=>{
  const fs=require('node:fs'),path=require('node:path');
  const html=fs.readFileSync(path.join(__dirname,'../index.html'),'utf8');
  const source=fs.readFileSync(path.join(__dirname,'../simulator-core.js'),'utf8');
  const normalize=text=>text.replace(/\r\n/g,'\n').trim();
  assert.equal(normalize(html.match(/<script id="sim-core">\s*([\s\S]*?)\s*<\/script>/)[1]),normalize(source));
  assert.equal(/<(script|link|img)[^>]+(?:src|href)=["']https?:/i.test(html),false);
  assert.equal(/<script[^>]+src=/i.test(html),false);
});
test('正逆运动学：可达位姿闭环误差 < 1e-8 m',()=>{
  for(const yaw of [0,Math.PI/2,-1.2])for(const [x,y,z] of [[.4,0,.375],[.18,0,.49],[-.15,0,.235],[-.15,0,.36]]){
    const base={x:.2,y:-.3,yaw},target=S.local(base,x,y,z),q=S.ik(base,target);
    assert.ok(S.distance(S.fk(base,q)[3],target)<1e-8);
  }
  assert.throws(()=>S.ik({x:0,y:0,yaw:0},{x:2,y:0,z:.4}),/OUT_OF_REACH/);
});
test('A* 路径绕开障碍，所有线段满足膨胀后间隙',()=>{
  const start={x:-1.48,y:.32},end={x:1.06,y:.34};
  assert.equal(S.segmentFree(start,end),false);
  const path=S.planPath(start,end);assert.ok(path.length>2);
  for(let i=1;i<path.length;i++)assert.ok(S.segmentFree(path[i-1],path[i]));
  assert.throws(()=>S.planPath({x:0,y:0},end),/NAV_INVALID/);
});
for(const id of ['red','blue','yellow'])test(id+' 完成抓取、托盘运输、投放与收拢',()=>{
  const sim=new S.Simulation();sim.start(id);let ticks=0,held=false,tray=false;
  while(sim.status==='RUNNING'&&ticks++<30000){
    sim.tick(.04);held ||= sim.target().mode==='held';tray ||= sim.target().mode==='tray';
    if(Math.abs(sim.base.v)>.001){assert.ok(sim.stowed());assert.equal(sim.held,null);assert.equal(S.blocked(sim.base,S.CONFIG.radius),false);}
  }
  assert.equal(sim.status,'SUCCEEDED',JSON.stringify(sim.snapshot()));
  assert.ok(held&&tray);assert.equal(sim.target().mode,'delivered');assert.ok(sim.stowed());
  assert.ok(sim.objects.filter(o=>o.mode==='source').length===2);
});
test('暂停不推进运动，继续后完成；重复启动受到保护',()=>{
  const sim=new S.Simulation();sim.start('red');sim.tick(2);sim.pause();const before=sim.snapshot();
  sim.tick(4);assert.deepEqual(sim.snapshot(),before);assert.throws(()=>sim.start('blue'),/BUSY/);
  sim.resume();for(let i=0;i<30000&&sim.status==='RUNNING';i++)sim.tick(.04);
  assert.equal(sim.status,'SUCCEEDED');
});
test('持物取消保持物体状态，重置恢复初始场景',()=>{
  const sim=new S.Simulation();sim.start('blue');for(let i=0;i<10000&&!sim.held&&sim.status==='RUNNING';i++)sim.tick(.04);
  assert.equal(sim.held,'blue');sim.cancel();const before=sim.snapshot();sim.tick(3);assert.deepEqual(sim.snapshot(),before);
  assert.throws(()=>sim.start('red'),/PAYLOAD_OCCUPIED/);sim.reset();assert.equal(sim.status,'IDLE');assert.equal(sim.held,null);assert.ok(sim.objects.every(o=>o.mode==='source'));
});
test('手动移动受收臂互锁和底盘碰撞边界保护',()=>{
  const sim=new S.Simulation();sim.setJoint(1,.4);assert.equal(sim.manualDrive(.2,0,.04),false);
  sim.q=[...S.STOW];sim.base={x:-.65,y:0,yaw:0,v:0,w:0};
  for(let i=0;i<100;i++)sim.manualDrive(.25,0,.04);
  assert.equal(S.blocked(sim.base,S.CONFIG.radius),false);assert.ok(sim.base.x<-.55);
});
console.log(JSON.stringify({tests:checks,status:'passed'}));
