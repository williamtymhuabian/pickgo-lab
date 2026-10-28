'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const depth=require('../depth_client.js');
const response=value=>({ok:true,json:async()=>value});
test('pixel selection never addresses padding beyond the last image pixel',()=>{
  assert.deepEqual(depth.pixel(320,240),[319,239]);assert.deepEqual(depth.pixel(-2,400),[0,239]);
});
test('invalid and mixed depths are explicit rather than zero distances',()=>{
  assert.match(depth.range_text({mm:650}),/0.650 m/);
  assert.match(depth.range_text({mm:null,reason:'MIXED_SURFACES'}),/混合/);
  assert.match(depth.range_text({mm:null,reason:'NO_VALID_DEPTH'}),/无有效深度/);
});
test('an open operation cancelled before acquisition releases the late device',async()=>{
  const calls=[];let resolveOpen;
  const client=depth.create_client(async(url,options)=>{
    calls.push([url,JSON.parse(options.body)]);
    if(url.endsWith('/open'))return new Promise(resolve=>resolveOpen=resolve);
    return response({opened:false});
  });
  const opening=client.open(),rejected=assert.rejects(opening,/取消/);
  await client.close();resolveOpen(response({token:'late'}));await rejected;
  assert.equal(client.state.token,null);assert.equal(calls.at(-1)[0],'/api/depth/close');
  assert.equal(calls.at(-1)[1].token,'late');
});
test('a measurement from a replaced frame is discarded',async()=>{
  let resolveMeasure;
  const client=depth.create_client(async(url)=>url.endsWith('/open')?response({token:'owner'}):new Promise(resolve=>resolveMeasure=resolve));
  await client.open();client.state.frame='first';const measuring=client.measure([1,2]);
  client.state.frame='second';resolveMeasure(response({frame_id:'first',range:{mm:500}}));
  assert.equal(await measuring,null);
});
test('close invalidates frames and uses a keepalive release request',async()=>{
  let closing;
  const client=depth.create_client(async(url,options)=>{
    if(url.endsWith('/open'))return response({token:'owner'});
    closing=options;return response({opened:false});
  });
  await client.open();client.state.frame='old';await client.close();
  assert.equal(client.state.frame,null);assert.equal(client.state.token,null);assert.equal(closing.keepalive,true);
});
test('point requests refer to the displayed frame, never a newer not-yet-drawn frame',async()=>{
  let payload;
  const client=depth.create_client(async(url,options)=>{
    if(url.endsWith('/open'))return response({token:'owner'});
    payload=JSON.parse(options.body);return response({frame_id:payload.frame_id,range:{mm:500}});
  });
  await client.open();client.state.frame='received-but-not-drawn';
  assert.equal(await client.measure([12,34],undefined,'displayed'),null);
  assert.equal(payload.frame_id,'displayed');
});
