'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const speech=require('../vision_speech.js');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const found=labels=>({found:true,objects:labels.map(label=>({label}))});
test('all 80 object categories have Chinese names',()=>assert.equal(Object.keys(speech.LABELS).length,80));
test('announcements describe unique candidate classes, not duplicate object counts',()=>{
  assert.equal(speech.describe(found(['cup','cup','keyboard']),'segment'),'可能识别到：杯子、键盘。');
  assert.equal(speech.describe(found(['cup','keyboard']),'segment','cup'),'可能识别到：杯子。');
});
test('unrecognized, manual and color modes do not invent object identities',()=>{
  assert.equal(speech.describe({found:false},'objects'),'本帧暂未识别到目标。');
  assert.match(speech.describe({found:true},'manual'),/类别尚未确定/);
  assert.equal(speech.describe({found:true,color:'red'},'color'),'可能识别到红色目标。');
  assert.equal(speech.describe(found(['__proto__','unknown']),'objects'),'本帧没有可播报的类别。');
});
test('continuous announcements require repeated observations and honor cooldown',()=>{
  const gate=speech.create_gate();
  assert.equal(gate.offer('杯子',0,true),false);
  assert.equal(gate.offer('杯子',1000,true),true);
  assert.equal(gate.offer('杯子',8000,true),false);
  assert.equal(gate.offer('杯子',21000,true),true);
  assert.equal(gate.offer('瓶子',22000,true),false);
  assert.equal(gate.offer('瓶子',23000,true),false);
  assert.equal(gate.offer('瓶子',27000,true),true);
});
test('single observations can speak immediately; changed source resets evidence',()=>{
  const gate=speech.create_gate();
  assert.equal(gate.offer('杯子',0),true);
  gate.reset();
  assert.equal(gate.offer('杯子',100,true),false);
  assert.equal(gate.offer('杯子',200,true),true);
});

function browserFixture(playError=null){
  const elements=new Map(),events={},pending=[];let plays=0;
  function element(id){
    if(!elements.has(id))elements.set(id,{checked:false,disabled:false,textContent:'',attrs:{},handlers:{},
      addEventListener(name,fn){this.handlers[name]=fn;},pause(){},load(){},
      removeAttribute(name){delete this.attrs[name];},getAttribute(name){return this.attrs[name]||null;},
      play(){plays++;return playError?Promise.reject(playError):Promise.resolve();}});
    return elements.get(id);
  }
  const document={hidden:false,getElementById:element,addEventListener(name,fn){events[name]=fn;}};
  const sandbox={document,window:{addEventListener(){}},Date,AbortController,setTimeout,clearTimeout,
    fetch(url){if(url.endsWith('/status'))return Promise.resolve({ok:true,json:async()=>({available:true})});return new Promise(resolve=>pending.push(resolve));}};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../vision_speech.js'),'utf8'),sandbox);
  return {panel:sandbox.PickGoSpeech.create_panel(),element,events,document,pending,plays:()=>plays};
}
const tick=()=>new Promise(resolve=>setImmediate(resolve));
test('late audio is discarded after the input source changes',async()=>{
  const b=browserFixture();await tick();
  b.panel.on_result(found(['cup']),{task:'objects',captured_at_ms:Date.now(),continuous:false});
  b.element('tts-current').handlers.click();assert.equal(b.pending.length,1);
  b.panel.reset();b.pending[0]({ok:true,json:async()=>({audio:'data:audio/wav;base64,late'})});await tick();
  assert.equal(b.plays(),0);assert.equal(b.element('tts-current').disabled,true);
});
test('autoplay denial remains visible and audio can be played manually',async()=>{
  const error=Object.assign(new Error('blocked'),{name:'NotAllowedError'}),b=browserFixture(error);await tick();
  b.panel.on_result(found(['cup']),{task:'objects',captured_at_ms:Date.now(),continuous:false});
  b.element('tts-current').handlers.click();b.pending[0]({ok:true,json:async()=>({audio:'data:audio/wav;base64,test'})});await tick();
  assert.match(b.element('tts-status').textContent,/阻止自动播放/);assert.equal(b.plays(),1);
});
test('old frames and hidden pages do not trigger automatic announcements',async()=>{
  const b=browserFixture();await tick();b.element('tts-enabled').checked=true;
  b.panel.on_result(found(['cup']),{task:'objects',captured_at_ms:Date.now()-3000,continuous:false});
  assert.equal(b.pending.length,0);b.document.hidden=true;b.events.visibilitychange();
  assert.equal(b.element('tts-enabled').checked,false);assert.equal(b.element('tts-current').disabled,true);
});
