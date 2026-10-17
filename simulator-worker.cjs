'use strict';
// 只负责运行运动核心；Python、网页、MCP 共用此进程中的一个场景。
const readline = require('node:readline');
const {randomUUID} = require('node:crypto');
const S = require('./simulator-core.js');
const sim = new S.Simulation();
let speed = 3, taskId = null, lastCommand = null, revision = 0;

function state() {
  return {...sim.snapshot(), backend:'sim', instance_id:instanceId, task_id:taskId, revision,
    selected:sim.selected, major:sim.major, index:sim.index, total:sim.queue.length,
    held:sim.held, path:sim.path, trail:sim.trail, speed, last_command:lastCommand};
}
function idle() {
  if (!['IDLE','SUCCEEDED','CANCELED'].includes(sim.status)) throw Error('BUSY: 请先停止或重置任务');
}
function number(value, low, high) {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < low || value > high)
    throw Error('INVALID_ARGUMENT: 数值超出范围');
  return value;
}
const instanceId = randomUUID();
const COMMAND = {
  state:()=>{},
  start:p=>{
    if (!['red','blue','yellow'].includes(p.target)) throw Error('INVALID_TARGET');
    const nextSpeed = p.speed === undefined ? speed : number(p.speed,1,6);
    sim.start(p.target); speed = nextSpeed; taskId = randomUUID();
  },
  pause:()=>{if(sim.status !== 'RUNNING')throw Error('NOT_RUNNING');sim.pause();},
  resume:()=>{if(sim.status !== 'PAUSED')throw Error('NOT_PAUSED');sim.resume();},
  stop:()=>sim.cancel(),
  reset:()=>{sim.reset();taskId=null;},
  select:p=>{idle();if(!['red','blue','yellow'].includes(p.target))throw Error('INVALID_TARGET');sim.selected=p.target;},
  speed:p=>{speed=number(p.value,1,6);},
  joint:p=>{idle();if(!Number.isInteger(p.index))throw Error('INVALID_JOINT');sim.setJoint(number(p.index,0,3),number(p.value,-Math.PI,Math.PI));},
  jaw:p=>{idle();if(sim.held)throw Error('PAYLOAD_OCCUPIED');sim.aperture=number(p.value,0,.1);},
  stow:()=>{idle();if(sim.held)throw Error('PAYLOAD_OCCUPIED');sim.q=[...S.STOW];},
  drive:p=>{idle();if(!sim.manualDrive(number(p.v,-.22,.22),number(p.w,-1.15,1.15),number(p.dt,0,.1)))throw Error('DRIVE_BLOCKED');},
};
let last = performance.now();
const timer = setInterval(()=>{
  const now=performance.now(),dt=Math.min(.1,(now-last)/1000);last=now;
  if(sim.status==='RUNNING'){sim.tick(dt*speed);revision++;}
  else sim.base.v=sim.base.w=sim.base.left=sim.base.right=0;
},20);
const input = readline.createInterface({input:process.stdin,crlfDelay:Infinity});
input.on('line',line=>{
  let request;
  try {
    request=JSON.parse(line);
    if(!Object.hasOwn(COMMAND,request.command))throw Error('UNKNOWN_COMMAND');
    COMMAND[request.command](request.params||{});
    if(request.command!=='state'){lastCommand={command:request.command,source:request.source||'python'};revision++;}
    process.stdout.write(JSON.stringify({id:request.id,result:state()})+'\n');
  } catch(error) {
    process.stdout.write(JSON.stringify({id:request?.id??null,error:error.message})+'\n');
  }
});
input.on('close',()=>{clearInterval(timer);process.exit(0);});
