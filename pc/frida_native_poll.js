'use strict';
// 统计 getEvents 真实调用频率（含返回0），判断咕咚是否在主动 poll 传感器
(function(){
  var getEvents = Module.findExportByName('libandroid.so','ASensorEventQueue_getEvents');
  var hasEvent=0, zero=0, total=0;
  var t0=Date.now();
  Interceptor.attach(getEvents, {
    onEnter: function(a){ this.ev=a[1]; this.cap=a[2].toInt32(); },
    onLeave: function(r){
      total++;
      var n=r.toInt32();
      if (n>0){
        hasEvent++;
        if (hasEvent<=10){
          var type=this.ev.add(8).readS32();
          var x=this.ev.add(24).readFloat(), y=this.ev.add(28).readFloat(), z=this.ev.add(32).readFloat();
          console.log('[GETEV+] n='+n+' cap='+this.cap+' type@8='+type+' v='+x.toFixed(2)+','+y.toFixed(2)+','+z.toFixed(2));
        }
      } else { zero++; }
      if (total%200===0){
        var dt=(Date.now()-t0)/1000;
        console.log('[POLL] calls='+total+' rate='+(total/dt).toFixed(1)+'/s  withData='+hasEvent+' zero='+zero+' ('+(zero/total*100).toFixed(0)+'%)');
      }
    }
  });

  // 同时 hook 队列是否注册/启用（attach 晚可能漏掉，仅尝试）
  var enable = Module.findExportByName('libandroid.so','ASensorEventQueue_enableSensor');
  Interceptor.attach(enable,{onEnter:function(a){ console.log('[enable] ASensor*='+a[1]); }});
  console.log('[POLL] installed, sampling 8s...');
})();
