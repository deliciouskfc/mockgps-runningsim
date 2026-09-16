package com.mockgps

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.widget.Button
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat

class MainActivity : AppCompatActivity() {

    private lateinit var statusText: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        statusText = TextView(this).apply {
            text = buildString {
                appendLine("MockGPS 模拟定位")
                appendLine()
                appendLine("使用步骤：")
                appendLine("1. 开启开发者选项 → 模拟位置应用 → 选择本应用")
                appendLine("2. 授予定位权限（后台定位）")
                appendLine("3. 点击下方「启动服务」")
                appendLine("4. 在电脑端运行 mock_route.py 推送路线")
                appendLine()
                appendLine("状态：未启动")
            }
            setPadding(48, 48, 48, 48)
        }

        val startBtn = Button(this).apply {
            text = "启动服务"
            setOnClickListener { startMockService() }
        }

        val stopBtn = Button(this).apply {
            text = "停止服务"
            setOnClickListener {
                stopService(Intent(this@MainActivity, MockLocationService::class.java))
                Toast.makeText(this@MainActivity, "服务已停止", Toast.LENGTH_SHORT).show()
            }
        }

        val layout = android.widget.LinearLayout(this).apply {
            orientation = android.widget.LinearLayout.VERTICAL
            addView(statusText)
            addView(startBtn)
            addView(stopBtn)
        }
        setContentView(layout)

        requestPermissionsIfNeeded()
        // 打开 App 即自动启动模拟服务（权限已授予时）
        startMockService()
    }

    private fun startMockService() {
        val intent = Intent(this, MockLocationService::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(intent)
        } else {
            startService(intent)
        }
        statusText.text = statusText.text.toString().replace("状态：未启动", "状态：运行中（等待电脑端推送坐标）")
        Toast.makeText(this, "服务已启动", Toast.LENGTH_SHORT).show()
    }

    private fun requestPermissionsIfNeeded() {
        val perms = mutableListOf(
            Manifest.permission.ACCESS_FINE_LOCATION,
            Manifest.permission.ACCESS_COARSE_LOCATION
        )
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            perms.add(Manifest.permission.ACCESS_BACKGROUND_LOCATION)
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            perms.add(Manifest.permission.POST_NOTIFICATIONS)
        }
        val needed = perms.filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }
        if (needed.isNotEmpty()) {
            ActivityCompat.requestPermissions(this, needed.toTypedArray(), 100)
        }
    }
}
