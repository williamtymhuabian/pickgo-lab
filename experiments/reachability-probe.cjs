'use strict';
// 只运行独立仿真实例，不连接网页服务、MCP 或任何实体设备。
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const core = path.resolve(__dirname, '../simulator-core.js');
const S = require(core);
const rows = [];
for (const y of [.76, .86, .96, 1.06, 1.16]) {
  const sim = new S.Simulation();
  sim.objects.find(o => o.id === 'red').y = y;
  sim.start('red');
  let ticks = 0;
  while (sim.status === 'RUNNING' && ticks++ < 20000) sim.tick(.04);
  rows.push({target_y_m:y, parking_y_m:.32, status:sim.status,
    phase:sim.phase, simulation_time_s:Number(sim.time.toFixed(2))});
}
console.log(JSON.stringify({
  experiment:'Only change red target y; fixed timestep 0.04 s; kinematic model only',
  core_sha256:crypto.createHash('sha256').update(fs.readFileSync(core)).digest('hex'),
  rows,
}, null, 2));
