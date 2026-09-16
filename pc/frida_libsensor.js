'use strict';
(function(){
  function dump(name){
    var m = Process.findModuleByName(name);
    if(!m){ console.log('[M] '+name+' NOT loaded'); return; }
    console.log('[M] '+name+' base='+m.base+' size='+m.size);
    var ex = m.enumerateExports();
    console.log('[M] '+name+' exports='+ex.length);
    ex.forEach(function(e){
      if (/SensorEventQueue|readEvent|getEvents|enableSensor|waitEvent|hasEvents|setEventRate|ASensor/i.test(e.name)){
        console.log('  ['+e.type+'] '+e.name+' @'+e.address);
      }
    });
  }
  dump('libsensor.so');
  dump('libandroid.so');
})();
