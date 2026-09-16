package com.mockgps

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build
import android.util.Log

/**
 * 接收电脑端通过 adb 推送的定位广播。
 *
 * 广播命令示例：
 *   adb shell am broadcast -a com.mockgps.UPDATE_LOCATION \
 *       --ef lat 39.908823 --ef lng 116.397470 \
 *       --ef accuracy 5.0 --ef bearing 90.0 --ef speed 3.33
 */
class LocationUpdateReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        when (intent.action) {
            ACTION_UPDATE -> {
                // 经纬度用字符串传递，避免 float 精度损失
                val latStr = intent.getStringExtra(EXTRA_LAT)
                val lngStr = intent.getStringExtra(EXTRA_LNG)
                val lat = latStr?.toDoubleOrNull() ?: Double.NaN
                val lng = lngStr?.toDoubleOrNull() ?: Double.NaN
                if (lat.isNaN() || lng.isNaN()) {
                    Log.w(TAG, "收到无效坐标: lat=$latStr lng=$lngStr")
                    return
                }
                val accuracy = intent.getFloatExtra(EXTRA_ACCURACY, 5f)
                val bearing = intent.getFloatExtra(EXTRA_BEARING, 0f)
                val speed = intent.getFloatExtra(EXTRA_SPEED, 0f)
                val altitude = intent.getDoubleExtra(EXTRA_ALTITUDE, 0.0)

                ensureServiceRunning(context)
                // 等服务起来后再推送；若已在运行则 instance 非空
                val svc = MockLocationService.instance
                if (svc != null) {
                    svc.pushLocation(lat, lng, accuracy, bearing, speed, altitude)
                } else {
                    // 首次启动可能需要一帧，把坐标暂存，由服务 onStartCommand 处理
                    pendingLocation = doubleArrayOf(lat, lng, accuracy.toDouble(), bearing.toDouble(), speed.toDouble(), altitude)
                }
            }
            ACTION_STOP -> {
                val stopIntent = Intent(context, MockLocationService::class.java)
                context.stopService(stopIntent)
                Log.i(TAG, "已请求停止 MockLocationService")
            }
        }
    }

    private fun ensureServiceRunning(context: Context) {
        if (MockLocationService.instance != null) return
        val serviceIntent = Intent(context, MockLocationService::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            context.startForegroundService(serviceIntent)
        } else {
            context.startService(serviceIntent)
        }
    }

    companion object {
        const val ACTION_UPDATE = "com.mockgps.UPDATE_LOCATION"
        const val ACTION_STOP = "com.mockgps.STOP"
        const val EXTRA_LAT = "lat"
        const val EXTRA_LNG = "lng"
        const val EXTRA_ACCURACY = "accuracy"
        const val EXTRA_BEARING = "bearing"
        const val EXTRA_SPEED = "speed"
        const val EXTRA_ALTITUDE = "altitude"

        @Volatile
        var pendingLocation: DoubleArray? = null
        private const val TAG = "MockGPS"
    }
}
