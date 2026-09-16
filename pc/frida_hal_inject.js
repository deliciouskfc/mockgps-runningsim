'use strict';
// 直接向 BlueStacks HAL 的 /data/bstfifo 写加速度帧（注入到独立 root 宿主进程）
// 帧格式(逆向自 sensors.default.so)：12 字节 = 3 x int32 LE，单位 = g 的百万分之一
//   HAL输出 = (raw/1e6) * (-9.80665)   =>   raw = round(-value/9.80665 * 1e6)
// 以 50Hz 写跑步波形；HAL 填上时间戳后分发给所有客户端(Java/Native 均覆盖)。
(function(){
  var FIFO = '/data/bstfifo';
  var AT_FDCWD = -100, O_WRONLY = 1;
  var G0 = 9.80665;

  var CFG = { running:1, cadence:168, impact:11.0, bounce:3.2, swingX:5.0, swingY:2.6, noise:0.7 };

  var libc = Process.findModuleByName('libc.so');
  var openat = new NativeFunction(Module.getExportByName('libc.so','openat'),'int',['int','pointer','int','int']);
  var write  = new NativeFunction(Module.getExportByName('libc.so','write'),'long',['int','pointer','long']);
  var close  = new NativeFunction(Module.getExportByName('libc.so','close'),'int',['int']);
  var errnoPtr = new NativeFunction(Module.getExportByName('libc.so','__errno'),'pointer',[]);

  var path = Memory.allocUtf8String(FIFO);
  var buf = Memory.alloc(12);
  var ab = new ArrayBuffer(12);
  var dv = new DataView(ab);
  var fd = -1;
  var frames = 0, t0 = Date.now(); 

  function errno(){ return errnoPtr().readS32(); }
  function openFifo(){
    if (fd >= 0) { try{close(fd);}catch(e){} }
    fd = openat(AT_FDCWD, path, O_WRONLY, 0);
    console.log('[HAL] openat('+FIFO+') = '+fd + (fd<0? (' errno='+errno()) : ''));
    return fd;
  }
  function enc(v){
    var r = Math.round(-v / G0 * 1e6);
    if (r > 2147483647) r = 2147483647;
    if (r < -2147483648) r = -2147483648;
    return r | 0;
  }
  function gauss(){
    var u=0,v=0;
    while(u===0)u=Math.random();
    while(v===0)v=Math.random();
    return Math.sqrt(-2*Math.log(u))*Math.cos(2*Math.PI*v);
  }

  openFifo();

  setInterval(function(){
    var t = (Date.now()-t0)/1000.0;
    var x,y,z;
    if (CFG.running === 1){
      var f = CFG.cadence/60.0;
      var ph = 2*Math.PI*f*t;
      var c = 0.5-0.5*Math.cos(ph);
      z = G0 + CFG.impact*Math.pow(c,6) + CFG.bounce*Math.sin(2*ph-0.6);
      x = CFG.swingX*Math.sin(ph+Math.PI/2) + 0.8*CFG.swingX*Math.sin(2*ph+0.4);
      y = CFG.swingY*Math.sin(ph+0.4) + 0.5*CFG.swingY*Math.sin(2*ph+1.1);
      var n=CFG.noise;
      x += n*gauss(); y += n*gauss(); z += n*gauss();
    } else {
      x=0; y=0; z=G0;
    }
    dv.setInt32(0, enc(x), true);
    dv.setInt32(4, enc(y), true);
    dv.setInt32(8, enc(z), true);
    var u8 = new Uint8Array(ab);
    var arr = [u8[0],u8[1],u8[2],u8[3],u8[4],u8[5],u8[6],u8[7],u8[8],u8[9],u8[10],u8[11]];
    buf.writeByteArray(arr);
    var w = write(fd, buf, 12);
    if (w < 12){
      console.log('[HAL] short/err write='+w+' errno='+errno()+', reopening');
      openFifo();
    }
    frames++;
    if (frames % 250 === 0){
      console.log('[HAL] '+frames+' frames ('+(frames/((Date.now()-t0)/1000)).toFixed(1)+'/Hz) cad='+CFG.cadence+' run='+CFG.running+
        ' last xyz=('+x.toFixed(2)+','+y.toFixed(2)+','+z.toFixed(2)+')');
    }
  }, 20);

  rpc.exports = {
    setcadence:function(v){ CFG.cadence=Math.max(1,Number(v)); return CFG.cadence; },
    setrunning:function(v){ CFG.running=Number(v)?1:0; return CFG.running; },
    status:function(){ return JSON.stringify({fd:fd,frames:frames,cfg:CFG}); }
  };
  console.log('[HAL] writer armed');
})();
