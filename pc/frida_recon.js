'use strict';
// 咕咚传感器侦察：列出系统传感器、hook 注册与事件回调
function sensorTypeName(t) {
  const names = {1:'ACCELEROMETER',2:'MAGNETIC_FIELD',3:'ORIENTATION',4:'GYROSCOPE',5:'LIGHT',
    9:'GRAVITY',10:'LINEAR_ACCELERATION',11:'ROTATION_VECTOR',15:'GAME_ROTATION_VECTOR',
    18:'STEP_DETECTOR',19:'STEP_COUNTER',20:'GEOMAG_ROTATION_VECTOR',
    31:'HEART_RATE',34:'LOW_LATENCY_OFFBODY',35:'ACCELEROMETER_UNCALIBRATED'};
  return names[t] || ('TYPE_'+t);
}

Java.perform(function () {
  const SM = Java.use('android.hardware.SensorManager');
  const Sensor = Java.use('android.hardware.Sensor');

  // 1) 列出系统所有传感器
  try {
    const ctx = Java.use('android.app.ActivityThread').currentApplication().getApplicationContext();
    const smgr = ctx.getSystemService('sensor');
    const list = smgr.getSensorList(-1); // Sensor.TYPE_ALL = -1
    console.log('[SENSORS] device sensor count =', list.size());
    for (let i = 0; i < list.size(); i++) {
      const s = list.get(i);
      console.log('[SENSOR] type=' + s.getType() + ' (' + sensorTypeName(s.getType()) +
        ') name="' + s.getName() + '" vendor="' + s.getVendor() +
        '" maxDelay=' + s.getMaxDelay() + ' minDelay=' + s.getMinDelay());
    }
  } catch (e) { console.log('[SENSORS] enum failed: ' + e); }

  // 2) hook getDefaultSensor
  SM.getDefaultSensor.overload('int').implementation = function (type) {
    const ret = this.getDefaultSensor(type);
    console.log('[getDefaultSensor] type=' + type + ' (' + sensorTypeName(type) + ') => ' + ret);
    return ret;
  };

  // 3) hook registerListener 多重载
  const overloads = SM.registerListener.overloads;
  overloads.forEach(function (ov) {
    ov.implementation = function () {
      try {
        let type = -1, rate = -1;
        for (let i = 0; i < arguments.length; i++) {
          const a = arguments[i];
          if (a && a.$className === 'android.hardware.Sensor') type = a.getType();
          if (typeof a === 'number' && rate === -1) rate = a;
        }
        console.log('[registerListener] sensor=' + type + ' (' + sensorTypeName(type) +
          ') rate=' + rate + ' args=' + arguments.length);
      } catch (e) {}
      return ov.apply(this, arguments);
    };
  });

  console.log('[RECON] hooks installed, waiting for sensor events...');
});
