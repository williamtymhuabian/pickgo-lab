/* Offline kinematic robot simulator. No dependencies, no hardware transport. */
(function (scope) {
  'use strict';
  const PI = Math.PI;
  const clamp = (x,a,b) => Math.max(a,Math.min(b,x));
  const angle = x => Math.atan2(Math.sin(x),Math.cos(x));
  const distance = (a,b) => Math.hypot(a.x-b.x,a.y-b.y,(a.z||0)-(b.z||0));
  const CONFIG = Object.freeze({ l1:.28,l2:.25,tool:.09,shoulder:.34,radius:.265,planningRadius:.30,wheelTrack:.39,wheelRadius:.075 });
  const STOW = Object.freeze([0,1.38,-2.38,-.5707963268]);
  const LIMITS = Object.freeze([[-PI,PI],[-.35,2.65],[-2.95,0],[-3.5,2.2]]);
  const OBSTACLES = Object.freeze([
    {name:'取物台',x:-1.25,y:.96,w:.88,d:.60,h:.34},
    {name:'投放台',x:1.25,y:.98,w:.88,d:.60,h:.34},
    {name:'障碍物',x:0,y:-.12,w:.62,d:.60,h:.48}
  ]);
  function local(base,x,y,z) {
    const c=Math.cos(base.yaw),s=Math.sin(base.yaw);
    return {x:base.x+c*x-s*y,y:base.y+s*x+c*y,z};
  }
  function fk(base,q) {
    const heading=base.yaw+q[0],c=Math.cos(heading),s=Math.sin(heading);
    const p0={x:base.x,y:base.y,z:CONFIG.shoulder};
    let r=CONFIG.l1*Math.cos(q[1]),z=CONFIG.shoulder+CONFIG.l1*Math.sin(q[1]);
    const p1={x:base.x+c*r,y:base.y+s*r,z};
    r+=CONFIG.l2*Math.cos(q[1]+q[2]); z+=CONFIG.l2*Math.sin(q[1]+q[2]);
    const p2={x:base.x+c*r,y:base.y+s*r,z};
    r+=CONFIG.tool*Math.cos(q[1]+q[2]+q[3]);z+=CONFIG.tool*Math.sin(q[1]+q[2]+q[3]);
    return [p0,p1,p2,{x:base.x+c*r,y:base.y+s*r,z}];
  }
  function ik(base,target,pitch=-PI/2) {
    const dx=target.x-base.x,dy=target.y-base.y;
    const r=Math.hypot(dx,dy)-CONFIG.tool*Math.cos(pitch);
    const h=target.z-CONFIG.shoulder-CONFIG.tool*Math.sin(pitch);
    const cosine=(r*r+h*h-CONFIG.l1**2-CONFIG.l2**2)/(2*CONFIG.l1*CONFIG.l2);
    if(!Number.isFinite(cosine)||cosine < -1-1e-8||cosine > 1+1e-8) throw Error('OUT_OF_REACH：目标超出机械臂工作空间');
    const elbow=-Math.acos(clamp(cosine,-1,1));
    const shoulder=Math.atan2(h,r)-Math.atan2(CONFIG.l2*Math.sin(elbow),CONFIG.l1+CONFIG.l2*Math.cos(elbow));
    const q=[angle(Math.atan2(dy,dx)-base.yaw),shoulder,elbow,pitch-shoulder-elbow];
    q.forEach((v,i)=>{if(v<LIMITS[i][0]-1e-8||v>LIMITS[i][1]+1e-8) throw Error('JOINT_LIMIT：关节 '+(i+1)+' 超限');});
    return q;
  }
  function blocked(p,r=CONFIG.planningRadius) {
    if(p.x < -2.35+r||p.x > 2.35-r||p.y < -1.55+r||p.y > 1.65-r) return true;
    return OBSTACLES.some(o=>{
      const dx=Math.max(Math.abs(p.x-o.x)-o.w/2,0),dy=Math.max(Math.abs(p.y-o.y)-o.d/2,0);
      return dx*dx+dy*dy < r*r;
    });
  }
  function segmentFree(a,b,r=CONFIG.planningRadius) {
    const count=Math.max(1,Math.ceil(distance(a,b)/.025));
    for(let i=0;i<=count;i++) if(blocked({x:a.x+(b.x-a.x)*i/count,y:a.y+(b.y-a.y)*i/count},r))return false;
    return true;
  }
  function planPath(start,goal) {
    if(blocked(start)||blocked(goal))throw Error('NAV_INVALID：起点或终点没有足够底盘间隙');
    if(segmentFree(start,goal))return [{x:start.x,y:start.y},{x:goal.x,y:goal.y}];
    const size=.10,nx=48,ny=33;
    const point=id=>({x:-2.35+(id%nx)*size,y:-1.55+Math.floor(id/nx)*size});
    const idFor=p=>clamp(Math.round((p.x+2.35)/size),0,nx-1)+nx*clamp(Math.round((p.y+1.55)/size),0,ny-1);
    const a=idFor(start),b=idFor(goal),open=[a],closed=new Set(),prev=new Map(),cost=new Map([[a,0]]);
    const score=id=>(cost.get(id)??Infinity)+distance(point(id),point(b));
    let found=false;
    while(open.length) {
      open.sort((u,v)=>score(v)-score(u)); const cur=open.pop();
      if(cur===b){found=true;break;}
      if(closed.has(cur))continue;closed.add(cur);
      const cx=cur%nx,cy=Math.floor(cur/nx),p=point(cur);
      for(let dx=-1;dx<=1;dx++)for(let dy=-1;dy<=1;dy++){
        if((!dx&&!dy)||cx+dx<0||cx+dx>=nx||cy+dy<0||cy+dy>=ny)continue;
        const next=cur+dx+dy*nx;
        if(closed.has(next)||!segmentFree(p,point(next)))continue;
        const nc=cost.get(cur)+Math.hypot(dx,dy)*size;
        if(nc<(cost.get(next)??Infinity)){cost.set(next,nc);prev.set(next,cur);open.push(next);}
      }
    }
    if(!found)throw Error('NAV_NO_PATH：没有可行路径');
    const ids=[b];while(ids[ids.length-1]!==a)ids.push(prev.get(ids[ids.length-1]));
    const raw=[{x:start.x,y:start.y},...ids.reverse().map(point),{x:goal.x,y:goal.y}];
    const result=[raw[0]];let i=0;
    while(i<raw.length-1){let j=raw.length-1;while(j>i+1&&!segmentFree(raw[i],raw[j]))j--;if(!segmentFree(raw[i],raw[j]))throw Error('NAV_NO_PATH：网格连接失败');result.push(raw[j]);i=j;}
    return result;
  }
  class Simulation {
    constructor(){this.reset();}
    reset(){
      this.base={x:-1.55,y:-1.02,yaw:0,v:0,w:0,left:0,right:0};
      this.q=[...STOW];this.aperture=.09;this.time=0;this.status='IDLE';this.phase='准备就绪';this.major=0;
      this.logs=[];this.path=[];this.trail=[];this.queue=[];this.index=0;this.active=null;this.held=null;this.selected='red';
      this.objects=[{id:'red',name:'红色方块',color:'#e87768',x:-1.48,y:.76,z:.375,mode:'source'},
        {id:'blue',name:'蓝色方块',color:'#6c9ee4',x:-1.25,y:.76,z:.375,mode:'source'},
        {id:'yellow',name:'黄色方块',color:'#e5be66',x:-1.02,y:.76,z:.375,mode:'source'}];
      this.record('就绪：选择目标，开始搬运。');return this;
    }
    record(message){this.logs.unshift({time:Number(this.time.toFixed(2)),message});this.logs=this.logs.slice(0,80);}
    target(){return this.objects.find(o=>o.id===this.selected);}
    tray(z=.235){return local(this.base,-.15,0,z);}
    tool(){return fk(this.base,this.q)[3];}
    stowed(){return this.q.every((v,i)=>Math.abs(v-STOW[i])<.025);}
    start(id='red'){
      if(this.status==='RUNNING'||this.status==='PAUSED')throw Error('BUSY：请先结束或重置当前任务');
      const object=this.objects.find(o=>o.id===id);
      if(!object||object.mode!=='source')throw Error('TARGET_UNAVAILABLE：目标已经被搬走，请重置');
      if(this.held||this.objects.some(o=>o.mode==='tray'))throw Error('PAYLOAD_OCCUPIED：请先重置未完成任务');
      this.selected=id;this.status='RUNNING';this.index=0;this.active=null;
      const source={x:object.x,y:object.y,z:object.z},drop={x:1.25+(['red','blue','yellow'].indexOf(id)-1)*.19,y:.78,z:.375};
      const pose=(label,target,major)=>({type:'pose',label,target,major});
      const joint=(label,q,major)=>({type:'joint',label,q,major});
      const grip=(label,opening,effect,major)=>({type:'grip',label,opening,effect,major});
      const wait=(label,duration,major)=>({type:'wait',label,duration,major});
      const front=()=>local(this.base,.18,0,.49),trayPre=()=>this.tray(.36);
      this.queue=[
        joint('检查并收拢机械臂',STOW,0),
        {type:'nav',label:'导航到取物台',goal:{x:object.x,y:.32,yaw:PI/2},major:0},wait('底盘停稳与工位对位',.7,1),
        wait('虚拟感知：读取目标几何位置',.8,1),pose('机械臂进入安全过渡位',front,2),
        pose('移动到预抓取位',()=>({...source,z:source.z+.10}),2),grip('张开夹爪',.10,null,2),
        pose('下降接近目标',()=>source,2),grip('闭爪并验证目标距离',.061,'attach',2),wait('确认夹持状态',.45,2),
        pose('抬升目标',()=>({...source,z:source.z+.10}),2),pose('带物收回过渡位',front,3),
        pose('转向车载托盘',trayPre,3),pose('放入车载托盘',()=>this.tray(),3),grip('释放到托盘并固定',.10,'tray',3),
        pose('从托盘退出',trayPre,3),joint('收拢机械臂，允许底盘移动',STOW,3),
        {type:'nav',label:'绕开障碍，运输到投放台',goal:{x:drop.x,y:.34,yaw:PI/2},major:4},wait('投放工位停稳对位',.7,4),
        pose('到托盘预抓位',trayPre,5),pose('从托盘重新抓取',()=>this.tray(),5),grip('闭爪取出托盘物体',.061,'attach',5),
        pose('从托盘抬升',trayPre,5),pose('转向投放台过渡位',front,5),pose('到达预投放位',()=>({...drop,z:drop.z+.10}),5),
        pose('下降到投放位',()=>drop,5),grip('释放目标并核验投放',.10,'deliver',5),pose('退出投放区域',()=>({...drop,z:drop.z+.10}),5),
        pose('机械臂回过渡位',front,6),joint('回到运输位',STOW,6),wait('任务完成核验',.4,6)
      ];
      this.record('任务开始：'+object.name+' → 投放台');return this;
    }
    pause(){if(this.status==='RUNNING'){this.status='PAUSED';this.base.v=0;this.base.w=0;this.base.left=0;this.base.right=0;this.record('任务暂停，保持当前位置。');}}
    resume(){if(this.status==='PAUSED'){this.status='RUNNING';this.record('继续当前任务。');}}
    cancel(){if(this.status==='RUNNING'||this.status==='PAUSED'){this.status='CANCELED';this.phase='已停止，保留物体状态';this.base.v=0;this.base.w=0;this.base.left=0;this.base.right=0;this.path=[];this.record('仿真任务已停止；物体状态保留，可重置。');}}
    fail(message){this.status='FAILED';this.phase=message;this.base.v=0;this.base.w=0;this.base.left=0;this.base.right=0;this.record(message);}
    initAction(a){
      this.phase=a.label;this.major=a.major;this.record(a.label);
      const active={...a,elapsed:0};
      if(a.type==='nav'){
        if(!this.stowed()||this.held)throw Error('INTERLOCK：机械臂未收拢或物体未固定');
        this.path=planPath(this.base,a.goal);active.waypoint=1;
      }
      if(a.type==='joint'||a.type==='pose'){
        active.from=[...this.q];active.to=a.type==='pose'?ik(this.base,a.target()):[...a.q];
        active.duration=Math.max(.25,...active.to.map((v,i)=>Math.abs(v-this.q[i])/1.05));
      }
      if(a.type==='grip'){active.from=this.aperture;active.duration=.6;}
      this.active=active;
    }
    updatePayload(){
      for(const object of this.objects){
        if(object.mode==='held')Object.assign(object,this.tool());
        if(object.mode==='tray')Object.assign(object,this.tray());
      }
    }
    gripEffect(effect){
      if(!effect)return;
      const object=this.target();
      if(effect==='attach'){
        if(!['source','tray'].includes(object.mode)||distance(this.tool(),object)>.025)throw Error('GRASP_FAILED：夹爪未对准目标');
        object.mode='held';this.held=object.id;
      }else if(effect==='tray'){
        if(this.held!==object.id||distance(this.tool(),this.tray())>.025)throw Error('TRAY_FAILED：托盘位置不匹配');
        object.mode='tray';this.held=null;
      }else if(effect==='deliver'){
        if(this.held!==object.id)throw Error('PLACE_FAILED：未持有目标');
        object.mode='delivered';this.held=null;
      }
      this.updatePayload();
    }
    advanceNav(a,dt){
      if(a.waypoint>=this.path.length){
        const error=angle(a.goal.yaw-this.base.yaw);
        if(Math.abs(error)<.012){this.base.yaw=a.goal.yaw;this.base.v=0;this.base.w=0;this.base.left=0;this.base.right=0;this.path=[];return true;}
        this.integrate(0,clamp(error*3,-1.35,1.35),dt);return false;
      }
      const p=this.path[a.waypoint],dx=p.x-this.base.x,dy=p.y-this.base.y,dist=Math.hypot(dx,dy);
      if(dist<.017){a.waypoint++;return false;}
      const error=angle(Math.atan2(dy,dx)-this.base.yaw);
      const v=Math.abs(error)>.30?0:Math.min(.33,dist*2.8)*Math.max(0,Math.cos(error));
      this.integrate(v,clamp(error*4,-1.65,1.65),dt);return false;
    }
    integrate(v,w,dt){
      const yaw=angle(this.base.yaw+w*dt),x=this.base.x+v*Math.cos(this.base.yaw+w*dt/2)*dt,y=this.base.y+v*Math.sin(this.base.yaw+w*dt/2)*dt;
      if(!segmentFree(this.base,{x,y},CONFIG.radius))throw Error('BASE_COLLISION：底盘触及障碍边界');
      Object.assign(this.base,{x,y,yaw,v,w,left:(v-w*CONFIG.wheelTrack/2)/CONFIG.wheelRadius,right:(v+w*CONFIG.wheelTrack/2)/CONFIG.wheelRadius});
      const last=this.trail[this.trail.length-1];if(!last||distance(last,this.base)>.035){this.trail.push({x,y});if(this.trail.length>1200)this.trail.shift();}
    }
    step(dt){
      if(this.status!=='RUNNING')return;
      this.time+=dt;
      try{
        if(!this.active){if(this.index>=this.queue.length){
          if(this.target().mode!=='delivered'||!this.stowed())throw Error('VERIFY_FAILED：任务后置条件未满足');
          this.status='SUCCEEDED';this.phase='搬运完成';this.record('任务成功：目标已投放，机械臂已收拢。');return;
        }this.initAction(this.queue[this.index]);}
        const a=this.active;a.elapsed+=dt;let done=false;
        if(a.type==='nav')done=this.advanceNav(a,dt);
        else if(a.type==='wait')done=a.elapsed>=a.duration;
        else if(a.type==='joint'||a.type==='pose'){
          const t=clamp(a.elapsed/a.duration,0,1),s=t*t*t*(10-15*t+6*t*t);
          this.q=a.from.map((v,i)=>v+(a.to[i]-v)*s);done=t>=1;
        }else if(a.type==='grip'){
          const t=clamp(a.elapsed/a.duration,0,1);this.aperture=a.from+(a.opening-a.from)*t;
          done=t>=1;if(done)this.gripEffect(a.effect);
        }
        this.updatePayload();
        if(done){this.index++;this.active=null;}
      }catch(error){this.fail(error.message);}
    }
    tick(dt){
      if(!Number.isFinite(dt)||dt<0||dt>5)throw Error('Invalid simulation timestep');
      let remaining=dt;while(remaining>1e-9){const t=Math.min(.02,remaining);this.step(t);remaining-=t;}
    }
    manualDrive(v,w,dt){
      if(!['IDLE','SUCCEEDED','CANCELED'].includes(this.status))return false;
      if(!this.stowed()||this.held)return false;
      try{this.integrate(clamp(v,-.25,.25),clamp(w,-1.3,1.3),clamp(dt,0,.05));this.updatePayload();return true;}
      catch(error){this.base.v=0;this.base.w=0;this.base.left=0;this.base.right=0;return false;}
    }
    setJoint(i,value){
      if(!['IDLE','SUCCEEDED','CANCELED'].includes(this.status))return false;
      if(!Number.isInteger(i)||i<0||i>3||!Number.isFinite(value))return false;
      this.q[i]=clamp(value,...LIMITS[i]);this.updatePayload();return true;
    }
    snapshot(){return {version:1,kind:'kinematic-simulation',time:this.time,status:this.status,phase:this.phase,base:{...this.base},joints:[...this.q],aperture:this.aperture,tool:{...this.tool()},objects:this.objects.map(o=>({...o})),events:this.logs.map(o=>({...o}))};}
  }
  const api=Object.freeze({Simulation,CONFIG,STOW,LIMITS,OBSTACLES,fk,ik,local,blocked,segmentFree,planPath,distance,angle,clamp});
  scope.RobotSim=api;
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
})(typeof globalThis!=='undefined'?globalThis:this);
