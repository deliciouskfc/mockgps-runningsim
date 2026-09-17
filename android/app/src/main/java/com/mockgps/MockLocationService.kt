package com.mockgps

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.location.Criteria
import android.location.Location
import android.location.LocationManager
import android.os.Build
import android.os.IBinder
import android.os.SystemClock
import android.util.Log
import com.google.android.gms.location.FusedLocationProviderClient
import com.google.android.gms.location.LocationServices
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.ServerSocket
import java.net.Socket
import kotlin.concurrent.thread

class MockLocationService : Service() {

    private lateinit var locationManager: LocationManager

    // 覆盖所有系统定位链路：GPS / NETWORK / FUSED（Android 12+）
    private val providers: List<String> by lazy {
        val list = mutableListOf(
            LocationManager.GPS_PROVIDER,
            LocationManager.NETWORK_PROVIDER
        )
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            list.add(LocationManager.FUSED_PROVIDER)
        }
        list
    }
    private val providerAdded = mutableSetOf<String>()

    // Google Play Services 融合定位客户端（咕咚等 App 读取的位置）
    private var fusedClient: FusedLocationProviderClient? = null
    @Volatile private var fusedMockModeEnabled = false

    // 本地 Socket 服务器：电脑端通过 `adb forward` 直连推送坐标，绕开 MIUI 后台广播冻结
    private var serverSocket: ServerSocket? = null
    private var socketThread: Thread? = null
    @Volatile private var socketRunning = false

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        instance = this
        locationManager = getSystemService(Context.LOCATION_SERVICE) as LocationManager
        startForeground(NOTIFICATION_ID, buildNotification())
        setupTestProviders()
        setupFusedMock()
        startSocketServer()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val pending = LocationUpdateReceiver.pendingLocation
        if (pending != null) {
            LocationUpdateReceiver.pendingLocation = null
            pushLocation(
                lat = pending[0],
                lng = pending[1],
                accuracy = pending[2].toFloat(),
                bearing = pending[3].toFloat(),
                speed = pending[4].toFloat(),
                altitude = pending[5]
            )
        }
        return START_STICKY
    }

    // ---------- 系统 Test Provider 注册 ----------

    private fun setupTestProviders() {
        for (provider in providers) {
            try {
                try { locationManager.removeTestProvider(provider) } catch (_: Exception) {}
                locationManager.addTestProvider(
                    provider,
                    false, false, false, false,
                    true, true, true,
                    Criteria.POWER_LOW,
                    Criteria.ACCURACY_FINE
                )
                locationManager.setTestProviderEnabled(provider, true)
                providerAdded.add(provider)
                Log.i(TAG, "Test provider $provider 已启用")
            } catch (e: SecurityException) {
                Log.e(TAG, "没有模拟定位权限，请在开发者选项中将本应用设为模拟位置应用", e)
            } catch (e: Exception) {
                Log.e(TAG, "设置 test provider $provider 失败", e)
            }
        }
    }

    // ---------- Google Play Services 融合定位 Mock ----------

    private fun setupFusedMock() {
        try {
            fusedClient = LocationServices.getFusedLocationProviderClient(this)
            fusedClient?.setMockMode(true)?.addOnCompleteListener { task ->
                fusedMockModeEnabled = task.isSuccessful
                if (task.isSuccessful) {
                    Log.i(TAG, "FusedLocationProviderClient mock 模式已开启")
                } else {
                    Log.e(TAG, "FusedLocationProviderClient setMockMode 失败", task.exception)
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "初始化 FusedLocationProviderClient 失败（可能未安装 Google Play Services）", e)
        }
    }

    // ---------- 推送定位 ----------

    /**
     * 推送一次模拟定位。同时注入所有 Test Provider + FusedLocationProviderClient，
     * 并尝试反射清除 isFromMockProvider 标记。
     */
    fun pushLocation(lat: Double, lng: Double, accuracy: Float, bearing: Float, speed: Float, altitude: Double = 0.0) {
        if (providerAdded.isEmpty()) {
            setupTestProviders()
        }
        val now = System.currentTimeMillis()
        val elapsedNanos = SystemClock.elapsedRealtimeNanos()

        for (provider in providerAdded) {
            try {
                val location = Location(provider).apply {
                    latitude = lat
                    longitude = lng
                    this.accuracy = accuracy
                    this.bearing = bearing
                    this.speed = speed
                    this.altitude = altitude
                    time = now
                    elapsedRealtimeNanos = elapsedNanos
                }
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                    location.isMock = true
                }
                // 注入后再尝试清除 mock 标记（降低被检测概率）
                sanitizeMockFlag(location)
                locationManager.setTestProviderLocation(provider, location)
            } catch (e: Exception) {
                Log.e(TAG, "setTestProviderLocation($provider) 失败", e)
            }
        }

        // 注入 Google Play Services 融合定位
        pushFusedLocation(lat, lng, accuracy, bearing, speed, altitude, now, elapsedNanos)
    }

    private fun pushFusedLocation(lat: Double, lng: Double, accuracy: Float,
                                  bearing: Float, speed: Float, altitude: Double,
                                  now: Long, elapsedNanos: Long) {
        val client = fusedClient ?: return
        if (!fusedMockModeEnabled) return
        try {
            val loc = Location("fused").apply {
                latitude = lat
                longitude = lng
                this.accuracy = accuracy
                this.bearing = bearing
                this.speed = speed
                this.altitude = altitude
                time = now
                elapsedRealtimeNanos = elapsedNanos
            }
            // 反射清除 mock 标记，降低被检测概率（咕咚等 App 会检查 isFromMockProvider）
            sanitizeMockFlag(loc)
            client.setMockLocation(loc).addOnFailureListener { e ->
                Log.e(TAG, "Fused setMockLocation 失败", e)
            }
        } catch (e: Exception) {
            Log.e(TAG, "Fused setMockLocation 异常", e)
        }
    }

    /**
     * 反射清除 Location 的 mock 标记（字段级，比方法级更深层）。
     * 尝试多种方式：setMock/setIsFromMockProvider 方法，以及 mMock/mIsFromMockProvider 字段。
     * 注意：系统在分发 test provider 位置时可能重新打标，此处仅降低被检测概率。
     */
    private fun sanitizeMockFlag(location: Location) {
        // 方式1：方法反射（Android S+ setMock，旧版 setIsFromMockProvider）
        try {
            val methodName = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) "setMock" else "setIsFromMockProvider"
            Location::class.java.getDeclaredMethod(methodName, Boolean::class.javaPrimitiveType)
                .apply { isAccessible = true }
                .invoke(location, false)
        } catch (_: Exception) {}

        // 方式2：字段反射（直接修改内部字段，绕过方法权限检查）
        val fieldNames = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            listOf("mMock", "mIsFromMockProvider")
        } else {
            listOf("mIsFromMockProvider", "mMock")
        }
        for (name in fieldNames) {
            try {
                val field = Location::class.java.getDeclaredField(name)
                field.isAccessible = true
                field.set(location, false)
            } catch (_: Exception) {}
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        stopSocketServer()
        for (provider in providers) {
            try {
                locationManager.setTestProviderEnabled(provider, false)
                locationManager.removeTestProvider(provider)
            } catch (_: Exception) {
            }
        }
        providerAdded.clear()
        // 关闭 Fused mock 模式
        try { fusedClient?.setMockMode(false) } catch (_: Exception) {}
        instance = null
        Log.i(TAG, "MockLocationService 已停止")
    }

    // ---------- Socket 服务器 ----------

    private fun startSocketServer() {
        if (socketRunning) return
        socketRunning = true
        socketThread = thread(name = "mockgps-socket", isDaemon = true) {
            try {
                val server = ServerSocket(SOCKET_PORT)
                serverSocket = server
                Log.i(TAG, "Socket 服务器已启动，端口 $SOCKET_PORT")
                while (socketRunning) {
                    val client = try {
                        server.accept()
                    } catch (e: Exception) {
                        if (socketRunning) Log.e(TAG, "accept 失败", e)
                        null
                    }
                    if (client != null) {
                        thread(name = "mockgps-client", isDaemon = true) { handleClient(client) }
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Socket 服务器启动失败", e)
            }
        }
    }

    private fun handleClient(client: Socket) {
        try {
            BufferedReader(InputStreamReader(client.getInputStream())).use { reader ->
                var line: String? = null
                while (socketRunning && reader.readLine().also { line = it } != null) {
                    val msg = line!!.trim()
                    if (msg == "QUIT") {
                        Log.i(TAG, "收到 QUIT，停止服务")
                        stopSelf()
                        return
                    }
                    val parts = msg.split(",")
                    if (parts.size < 5) continue
                    try {
                        val lat = parts[0].trim().toDouble()
                        val lng = parts[1].trim().toDouble()
                        val acc = parts[2].trim().toFloat()
                        val bear = parts[3].trim().toFloat()
                        val spd = parts[4].trim().toFloat()
                        // 第 6 字段为海拔（米）；旧版 PC 端只发 5 字段时默认 0
                        val alt = if (parts.size >= 6) parts[5].trim().toDouble() else 0.0
                        pushLocation(lat, lng, acc, bear, spd, alt)
                    } catch (e: Exception) {
                        Log.e(TAG, "解析坐标失败: $line", e)
                    }
                }
            }
        } catch (_: Exception) {
        } finally {
            try { client.close() } catch (_: Exception) {}
        }
    }

    private fun stopSocketServer() {
        socketRunning = false
        try { serverSocket?.close() } catch (_: Exception) {}
        serverSocket = null
        socketThread = null
    }

    private fun buildNotification(): Notification {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "MockGPS 服务",
                NotificationManager.IMPORTANCE_LOW
            )
            getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
        }
        val builder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Notification.Builder(this, CHANNEL_ID)
        } else {
            @Suppress("DEPRECATION")
            Notification.Builder(this)
        }
        return builder
            .setContentTitle("MockGPS 正在运行")
            .setContentText("等待电脑端推送定位...")
            .setSmallIcon(android.R.drawable.ic_menu_mylocation)
            .setOngoing(true)
            .build()
    }

    companion object {
        private const val TAG = "MockGPS"
        private const val CHANNEL_ID = "mockgps_channel"
        private const val NOTIFICATION_ID = 1001

        @Volatile
        var instance: MockLocationService? = null

        const val SOCKET_PORT = 17890
    }
}
