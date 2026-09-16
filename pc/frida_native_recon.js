'use strict';
// native 传感器侦察：确认咕咚 NDK 启用的传感器类型 + ASensorEvent 内存布局
function tname(t){var m={1:'ACCEL',4:'GYRO',9:'GRAVITY',10:'LINACC',11:'ROTVEC',18:'STEP_DET',19:'STEP_CNT'};return m[t]||('T'+t);}

function dumpHex(p, len){
  var bytes = new Uint8Array(p.readByteArray(len));
  var lines = [];
  for (var i=0;i<bytes.length;i+=16){
    var hex=[],asc='';
    for (var j=0;j<16 && i+j<bytes.length;j++){
      var b=bytes[i+j]; hex.push(('0'+b.toString(16)).slice(-2));
      asc += (b>=32&&b<127)?String.fromCharCode(b):'.';
    }
    lines.push(('0000'+i.toString(16)).slice(-4)+'  '+hex.join(' ')+'  '+asc);
  }
  return lines.join('\n');
}

(function () {
  var getEvents = Module.findExportByName('libandroid.so','ASensorEventQueue_getEvents');
  var enableSensor = Module.findExportByName('libandroid.so','ASensorEventQueue_enableSensor');
  var getType = Module.findExportByName('libandroid.so','ASensor_getType');
  console.log('[N] getEvents='+getEvents+'  enableSensor='+enableSensor+'  getType='+getType);

  var fGetType = getType ? new NativeFunction(getType,'int',['pointer']) : null;

  if (enableSensor && fGetType){
    Interceptor.attach(enableSensor, {
      onEnter: function(a){
        try { var t=fGetType(a[1]); console.log('[enableSensor] type='+t+' ('+tname(t)+')'); }
        catch(e){ console.log('[enableSensor] err '+e); }
      }
    });
  }

  var shown=0, dumped=false;
  if (getEvents){
    Interceptor.attach(getEvents, {
      onEnter: function(a){ this.ev = a[1]; this.count = a[2].toInt32(); },
      onLeave: function(r){
        var n = r.toInt32();
        if (n <= 0) return;
        if (!dumped){
          console.log('[HEX] n='+n+' count='+this.count);
          console.log(dumpHex(this.ev, 208));
          dumped = true;
        }
        for (var i=0;i<n && shown<20;i++){
          [56,104].forEach(function(stride){
            try {
              var base = this.ev.add(i*stride);
              var type = base.add(8).readS32();
              var ts = base.add(16).readS64();
              var x = base.add(24).readFloat(), y = base.add(28).readFloat(), z = base.add(32).readFloat();
              if (type>=0 && type<40 && isFinite(x) && isFinite(z) && Math.abs(z)<40){
                console.log('[ev s='+stride+'] i='+i+' type='+type+'('+tname(type)+') ts='+ts+' v='+x.toFixed(2)+','+y.toFixed(2)+','+z.toFixed(2));
              }
            } catch(e){}
          }.bind(this));
          shown++;
        }
      }
    });
  }
  console.log('[N] native recon installed');
})();
