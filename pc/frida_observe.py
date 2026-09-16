#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""attach 已运行的咕咚，观察加速度计最终注入值，N 秒后退出（不影响常驻注入器）。
用法: python frida_observe.py [seconds]
"""
import sys, time, subprocess, frida

PKG = "com.codoon.gps"
JS = r"""
Java.perform(function () {
  var Q = Java.use('android.hardware.SystemSensorManager$SensorEventQueue');
  var n = 0;
  Q.dispatchSensorEvent.overload('int','[F','int','long').implementation = function(h,v,a,ts){
    var r = this.dispatchSensorEvent(h,v,a,ts);
    if (h === 0 && n < 25) {
      var mag = Math.sqrt(v[0]*v[0]+v[1]*v[1]+v[2]*v[2]);
      console.log('ACCEL x='+v[0].toFixed(2)+' y='+v[1].toFixed(2)+' z='+v[2].toFixed(2)+' |a|='+mag.toFixed(2));
      n++;
    }
    return r;
  };
  console.log('observer installed');
});
"""

def main():
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 12.0
    dev = frida.get_usb_device(timeout=10)
    # 用 PID attach（名称匹配在该 ROM 不稳定）
    out = subprocess.run(["adb","-s","emulator-5554","shell","pidof",PKG],
                         capture_output=True, text=True, timeout=10)
    pid = int(out.stdout.strip().split()[0])
    print(f"[obs] attach pid={pid}")
    session = dev.attach(pid)
    sc = session.create_script(JS)
    sc.on("message", lambda m,d: print(m.get("payload", m)) if m["type"]=="log" else None)
    sc.load()
    time.sleep(secs)
    session.detach()
    print("[obs] done")

if __name__ == "__main__":
    main()
