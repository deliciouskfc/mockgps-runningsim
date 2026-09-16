'use strict';
// 探测传感器事件分发链路：找到 dispatchSensorEvent 点 + handle→type 映射
Java.perform(function () {
  // 枚举 SystemSensorManager 内部类
  const loader = Java.classFactory.loader;
  Java.enumerateLoadedClassesSync().forEach(function (n) {
    if (n.indexOf('SensorEventQueue') >= 0 || n.indexOf('SystemSensorManager') >= 0) {
      console.log('[CLASS] ' + n);
    }
  });

  function hookDispatch(className) {
    try {
      const C = Java.use(className);
      const ovs = C.dispatchSensorEvent.overloads;
      ovs.forEach(function (ov) {
        console.log('[FOUND] ' + className + '.dispatchSensorEvent' + ov.argumentTypes.map(function (t) { return t.className; }));
        let __n = 0;
        ov.implementation = function () {
          const handle = arguments[0];
          const vals = arguments[1];
          let s = 'handle=' + handle + ' n=' + (vals ? vals.length : 0);
          if (vals && vals.length >= 3) s += ' v=[' + vals[0].toFixed(2) + ',' + vals[1].toFixed(2) + ',' + vals[2].toFixed(2) + ']';
          // dump 字段找 sensor type
          try {
            const fields = this.getClass().getDeclaredFields();
            for (let i = 0; i < fields.length; i++) {
              const f = fields[i];
              const fn = f.getName();
              if (fn.toLowerCase().indexOf('sensor') >= 0 || fn.toLowerCase().indexOf('handle') >= 0) {
                f.setAccessible(true);
                const v = f.get(this);
                s += ' | ' + fn + '=' + v;
              }
            }
          } catch (e) { s += ' (field err: ' + e + ')'; }
          if (__n < 10) { console.log('[DISPATCH] ' + s); __n++; }
          return ov.apply(this, arguments);
        };
      });
    } catch (e) { console.log('[skip] ' + className + ': ' + e); }
  }

  setTimeout(function () {
    Java.perform(function () { hookDispatch('android.hardware.SystemSensorManager$SensorEventQueue'); });
  }, 2500);
});
