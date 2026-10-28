/* Chinese speech of accepted observations; no microphone or cloud TTS. */
(function(root){
'use strict';
const LABELS={person:'人',bicycle:'自行车',car:'汽车',motorcycle:'摩托车',airplane:'飞机',bus:'公交车',train:'火车',truck:'卡车',boat:'船',
  'traffic light':'交通信号灯','fire hydrant':'消防栓','stop sign':'停车标志','parking meter':'停车计时器',bench:'长椅',bird:'鸟',cat:'猫',dog:'狗',horse:'马',sheep:'羊',cow:'牛',elephant:'大象',bear:'熊',zebra:'斑马',giraffe:'长颈鹿',
  backpack:'背包',umbrella:'雨伞',handbag:'手提包',tie:'领带',suitcase:'行李箱',frisbee:'飞盘',skis:'滑雪板',snowboard:'单板滑雪板','sports ball':'球',kite:'风筝','baseball bat':'棒球棒','baseball glove':'棒球手套',skateboard:'滑板',surfboard:'冲浪板','tennis racket':'网球拍',
  bottle:'瓶子','wine glass':'高脚杯',cup:'杯子',fork:'叉子',knife:'刀',spoon:'勺子',bowl:'碗',banana:'香蕉',apple:'苹果',sandwich:'三明治',orange:'橙子',broccoli:'西兰花',carrot:'胡萝卜','hot dog':'热狗',pizza:'披萨',donut:'甜甜圈',cake:'蛋糕',
  chair:'椅子',couch:'沙发','potted plant':'盆栽',bed:'床','dining table':'餐桌',toilet:'马桶',tv:'电视或显示屏',laptop:'笔记本电脑',mouse:'鼠标',remote:'遥控器',keyboard:'键盘','cell phone':'手机',microwave:'微波炉',oven:'烤箱',toaster:'烤面包机',sink:'水槽',refrigerator:'冰箱',book:'书',clock:'时钟',vase:'花瓶',scissors:'剪刀','teddy bear':'玩具熊','hair drier':'吹风机',toothbrush:'牙刷'};
function describe(result,task,preferred){
  if(!result)return '';
  if(!result.found)return '本帧暂未识别到目标。';
  if(task==='manual')return '已提取所选区域的前景，物体类别尚未确定。';
  if(task==='color')return '可能识别到'+({red:'红色',blue:'蓝色',yellow:'黄色'}[result.color]||'指定颜色')+'目标。';
  let labels=[...new Set((result.objects||[]).map(o=>o.label).filter(label=>Object.hasOwn(LABELS,label)))].sort();
  if(preferred&&labels.includes(preferred))labels=[preferred];
  return labels.length?'可能识别到：'+labels.map(label=>LABELS[label]).join('、')+'。':'本帧没有可播报的类别。';
}
function create_gate(){
  let candidate='',hits=0,lastText='',lastTime=-Infinity;
  return {
    offer(text,now,continuous=false){
      if(text===candidate)hits++;else {candidate=text;hits=1;}
      if(!text||(continuous&&hits<2)||now-lastTime<6000||(text===lastText&&now-lastTime<20000))return false;
      lastText=text;lastTime=now;return true;
    },
    reset(){candidate='';hits=0;lastText='';lastTime=-Infinity;}
  };
}
function create_panel(){
  const $=id=>document.getElementById(id),audio=$('tts-audio'),synth=root.speechSynthesis;
  const gate=create_gate();let backend=null,current=null,preferred=null,generation=0,request=null,speaking=false,nativeUtterance=null;
  function status(text){$('tts-status').textContent=text;}
  function nativeVoice(){return synth?.getVoices().find(v=>v.localService&&/^zh(?:-|_)/i.test(v.lang));}
  function update(){
    $('tts-current').disabled=!current||!backend;$('tts-test').disabled=!backend;$('tts-enabled').disabled=!backend;
    $('tts-text').textContent=current?describe(current.result,current.task,preferred):'等待新的识别结果';
  }
  function stop(message='已停止播报'){
    generation++;if(request)request.abort();request=null;audio.pause();audio.removeAttribute('src');audio.load();
    if(synth)synth.cancel();nativeUtterance=null;speaking=false;status(message);
  }
  async function speak(text){
    stop('正在准备语音…');const version=generation;speaking=true;
    try{
      if(backend==='windows-local'){
        request=new AbortController();const active=request,timeout=setTimeout(()=>active.abort(),15000);let result;
        try{
          const response=await fetch('/api/vision/speech',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text}),signal:active.signal});
          result=await response.json();if(!response.ok)throw Error(result.error||'语音合成失败');
        }finally{clearTimeout(timeout);if(request===active)request=null;}
        if(version!==generation)return;audio.src=result.audio;await audio.play();
        if(version===generation)status('正在播报：'+text);
      }else{
        const voice=nativeVoice();if(!voice)throw Error('浏览器没有可用的本地中文语音');
        nativeUtterance=new root.SpeechSynthesisUtterance(text);nativeUtterance.voice=voice;nativeUtterance.lang=voice.lang;
        nativeUtterance.onstart=()=>{if(version===generation)status('正在播报：'+text);};
        nativeUtterance.onend=()=>{if(version===generation){speaking=false;status('播报完成：'+text);}};
        nativeUtterance.onerror=event=>{if(version===generation){speaking=false;status('播报失败：'+event.error);}};
        synth.speak(nativeUtterance);
      }
    }catch(error){
      if(version!==generation)return;speaking=false;
      status(error.name==='NotAllowedError'?'浏览器阻止自动播放，请点击下方音频播放键。':error.name==='AbortError'?'语音合成超时，可重新播报。':'播报失败：'+error.message);
    }
  }
  audio.addEventListener('ended',()=>{speaking=false;status('播报完成');});
  audio.addEventListener('error',()=>{if(audio.getAttribute('src')){speaking=false;status('音频播放失败，请重新播报。');}});
  $('tts-test').addEventListener('click',()=>speak('语音播报已准备好，请把物体放到摄像头前。'));
  $('tts-current').addEventListener('click',()=>{if(current)speak(describe(current.result,current.task,preferred));});
  $('tts-stop').addEventListener('click',()=>{$('tts-enabled').checked=false;stop();});
  $('tts-enabled').addEventListener('change',()=>{gate.reset();if($('tts-enabled').checked)status('自动播报已开启，等待下一次识别。');else stop('自动播报已关闭');});
  function reset(){stop('输入已变化，等待新的识别结果');current=null;preferred=null;gate.reset();update();}
  function begin_frame(){current=null;update();}
  function on_result(result,meta){
    current={result,task:meta.task};if(preferred&&!(result.objects||[]).some(o=>o.label===preferred))preferred=null;update();
    if(!$('tts-enabled').checked||document.hidden||speaking||Date.now()-meta.captured_at_ms>2500)return;
    const text=describe(result,meta.task,preferred);if(gate.offer(text,Date.now(),meta.continuous))speak(text);
  }
  function select(object){preferred=object.label;update();}
  async function connect(){
    try{const response=await fetch('/api/vision/speech/status');if(response.ok&&(await response.json()).available)backend='windows-local';}catch(error){}
    if(!backend&&nativeVoice())backend='browser-local';
    status(backend==='windows-local'?'Windows 本地中文语音就绪':backend?'浏览器本地中文语音就绪':'没有可用的本地中文语音，请检查系统语音组件或重启更新后的服务。');update();
  }
  if(synth?.addEventListener)synth.addEventListener('voiceschanged',()=>{if(!backend&&nativeVoice()){backend='browser-local';status('浏览器本地中文语音就绪');update();}});
  document.addEventListener('visibilitychange',()=>{if(document.hidden){$('tts-enabled').checked=false;reset();}});
  window.addEventListener('pagehide',()=>stop());connect();update();return {on_result,select,reset,begin_frame,preferred_label:()=>preferred};
}
const api={LABELS,describe,create_gate,create_panel};
if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.PickGoSpeech=api;
})(typeof globalThis!=='undefined'?globalThis:this);
