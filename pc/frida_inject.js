'use strict';
// 咕咚加速度计跑步波形注入
// hook: SystemSensorManager$SensorEventQueue.dispatchSensorEvent(handle, values, accuracy, timestamp)
// 仅改写加速度计(handle=0 / type=1) 的 x,y,z，用随硬件 timestamp 累积相位的合成跑步波形。
//
// 可通过 RPC 动态调参：
//   setCadence(spm)  步频
//   setRunning(0/1)  是否注入跑步波形（跑步中开，平时关，恢复静止重力）
//   setAmp(倍数)     波形强度
'use strict';

var CFG = {
  running: 1,        // 1=注入跑步波形, 0=静止(0,0,9.81)
  cadence: 168,      // 步频 spm
  impact: 11.0,      // 着地冲击峰 (m/s^2)
      bounce: 3.2,         // 身体上下振动幅度
      swingX: 5.0,         // 前后(摆臂)幅度
      swingY: 2.6,         // 侧向幅度
      noise: 0.7,          // 高斯噪声强度
      g: 9.81
};

// Box-Muller 高斯噪声
function gauss() {
  var u = 0, v = 0;
  while (u === 0) u = Math.random();
  while (v === 0) v = Math.random();
  return Math.sqrt(-2.0 * Math.log(u)) * Math.cos(2.0 * Math.PI * v);
}

Java.perform(function () {
  var Queue = Java.use('android.hardware.SystemSensorManager$SensorEventQueue');

  Queue.dispatchSensorEvent.overload('int', '[F', 'int', 'long').implementation =
  function (handle, values, accuracy, timestamp) {
    var isAccel = false;
    try {
      // 通过 mSensorsEvents 映射判断传感器类型
      var ev = this.mSensorsEvents.value.get(handle);
      if (ev !== null && ev.sensor.value.getType() === 1) isAccel = true;
    } catch (e) {
      if (handle === 0) isAccel = true; // 兜底：本机加速度计 handle=0
    }

    if (isAccel && values.length >= 3) {
      if (CFG.running === 1) {
        var t = timestamp / 1e9;                 // 秒
        var f = CFG.cadence / 60.0;             // Hz
        var ph = 2.0 * Math.PI * f * t;         // 每步一个周期
        // 着地冲击：每步一个窄脉冲（在 ph=0 处峰值）
        var c = 0.5 - 0.5 * Math.cos(ph);
        var impact = CFG.impact * Math.pow(c, 6);
        var z = CFG.g + impact + CFG.bounce * Math.sin(2 * ph - 0.6);
        var x = CFG.swingX * Math.sin(ph + Math.PI / 2)
              + 0.8 * CFG.swingX * Math.sin(2 * ph + 0.4);
        var y = CFG.swingY * Math.sin(ph + 0.4)
              + 0.5 * CFG.swingY * Math.sin(2 * ph + 1.1);
        var n = CFG.noise;
        values[0] = x + n * gauss();
        values[1] = y + n * gauss();
        values[2] = z + n * gauss();
      } else {
        values[0] = 0.0;
        values[1] = 0.0;
        values[2] = CFG.g;
      }
    }
    return this.dispatchSensorEvent(handle, values, accuracy, timestamp);
  };

  console.log('[INJECT] accelerometer hook installed. cadence=' + CFG.cadence +
              ' running=' + CFG.running);
});

// RPC 动态调参
rpc.exports = {
  setcadence: function (v) { CFG.cadence = Math.max(1, Number(v)); return CFG.cadence; },
  setrunning: function (v) { CFG.running = Number(v) ? 1 : 0; return CFG.running; },
  setamp: function (k) {
    k = Number(k);
    CFG.impact = 11.0 * k; CFG.bounce = 3.2 * k;
    CFG.swingX = 5.0 * k; CFG.swingY = 2.6 * k;
    return k;
  },
  status: function () { return JSON.stringify(CFG); }
};
