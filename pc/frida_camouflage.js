'use strict';
// 伪装 BlueStacks 加速度计硬件规格，让咕咚认为其可用于计步；同时监控传感器注册。
// 仅对 type=1 (ACCELEROMETER) 生效。
Java.perform(function(){
  var Sensor = Java.use('android.hardware.Sensor');
  var SM = Java.use('android.hardware.SystemSensorManager');

  function typeOf(self){
    try { return self.getType(); } catch(e){ return -1; }
  }

  Sensor.getMaximumRange.implementation = function(){
    var real = this.getMaximumRange();
    if (typeOf(this) === 1) { console.log('[SPEC] getMaximumRange '+real+' -> 39.2266'); return 39.2266; }
    return real;
  };
  Sensor.getMinDelay.implementation = function(){
    var real = this.getMinDelay();
    if (typeOf(this) === 1) { console.log('[SPEC] getMinDelay '+real+' -> 5000'); return 5000; }
    return real;
  };
  Sensor.getResolution.implementation = function(){
    var real = this.getResolution();
    if (typeOf(this) === 1) { return 0.001197817; }
    return real;
  };
  Sensor.getFifoReservedEventCount.implementation = function(){
    if (typeOf(this) === 1) return 100;
    return this.getFifoReservedEventCount();
  };
  Sensor.getFifoMaxEventCount.implementation = function(){
    if (typeOf(this) === 1) return 1000;
    return this.getFifoMaxEventCount();
  };
  Sensor.getName.implementation = function(){
    if (typeOf(this) === 1) return 'BMI260 Accelerometer';
    return this.getName();
  };
  Sensor.getVendor.implementation = function(){
    if (typeOf(this) === 1) return 'Bosch';
    return this.getVendor();
  };

  function tn(t){var m={1:'ACCEL',2:'MAG',3:'ORIENT',4:'GYRO',5:'LIGHT',9:'GRAVITY',10:'LINACC',11:'ROTVEC',18:'STEP_DET',19:'STEP_CNT'};return m[t]||('T'+t);}
  SM.registerListener.overloads.forEach(function(ov){
    ov.implementation = function(){
      var type=-1, rate=-1;
      for (var i=0;i<arguments.length;i++){
        var a=arguments[i];
        if (a && a.$className==='android.hardware.Sensor') type=a.getType();
        if (typeof a==='number' && rate===-1) rate=a;
      }
      console.log('[REG] sensor='+type+'('+tn(type)+') rate='+rate+' args='+arguments.length);
      return ov.apply(this, arguments);
    };
  });

  console.log('[CAMO] installed');
});
