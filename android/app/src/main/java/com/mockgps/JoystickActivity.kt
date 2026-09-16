package com.mockgps

import android.Manifest
import android.app.Activity
import android.content.pm.PackageManager
import android.graphics.Color
import android.location.Location
import android.location.LocationManager
import android.os.Bundle
import android.os.Environment
import android.os.SystemClock
import android.view.Gravity
import android.view.View
import android.view.WindowManager
import android.webkit.JavascriptInterface
import android.webkit.WebView
import android.widget.Button
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * 轨迹设计：在高德底图上点选起点 → 自动生成标准 400m 田径场圈
 * （弯道半径 36.5m + 直道 84.39m，周长 ≈ 398m）→ 拖动平移 / 按钮旋转对准跑道 → 保存。
 * 保存格式每行 "纬度,经度"，mock_route.py 可直接循环回放。
 */
class JoystickActivity : Activity() {

    private companion object {
        // 港中深操场中心（初始地图视野）
        const val DEFAULT_LAT = 22.6860
        const val DEFAULT_LNG = 114.2078
    }

    private lateinit var lm: LocationManager
    private lateinit var status: TextView
    private lateinit var btnSave: Button
    private lateinit var webView: WebView
    private var hasRing = false

    /** JS 桥 */
    inner class Bridge {
        @JavascriptInterface
        fun onReady() {
            runOnUiThread {
                webView.evaluateJavascript("if(window.resetMap)resetMap($DEFAULT_LAT,$DEFAULT_LNG);", null)
            }
        }

        @JavascriptInterface
        fun onRing() {
            hasRing = true
            runOnUiThread {
                status.text = "点击可重新选起点 · 拖动平移地图 · ⟳⟲旋转\n对准跑道后点「保存轨迹」"
                btnSave.isEnabled = true
                btnSave.text = "保存轨迹"
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        lm = getSystemService(LOCATION_SERVICE) as LocationManager

        val root = FrameLayout(this)

        webView = WebView(this).apply {
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            // 蓝叠等模拟器 GPU 对 WebView 硬件加速兼容性差，强制软件渲染防引擎崩溃
            setLayerType(View.LAYER_TYPE_SOFTWARE, null)
            setBackgroundColor(Color.parseColor("#E8E8E8"))
            addJavascriptInterface(Bridge(), "AndroidBridge")
            loadUrl("file:///android_asset/joystick_map.html")
        }
        root.addView(webView, FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT))

        val top = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(0xB3222222.toInt())
            setPadding(24, 20, 24, 20)
        }
        status = TextView(this).apply {
            text = "拖动地图找到操场 · 点击跑道选起点（自动生成 400m 圈）\n⟳⟲旋转对准方向，可反复点击微调"
            textSize = 15f
            setTextColor(Color.WHITE)
            gravity = Gravity.CENTER
        }
        btnSave = Button(this).apply {
            text = "保存轨迹"
            textSize = 16f
            isEnabled = false
            setOnClickListener { saveTrack() }
        }
        top.addView(status)
        top.addView(btnSave)
        root.addView(top, FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.WRAP_CONTENT, Gravity.TOP))

        setContentView(root)

        if (checkSelfPermission(Manifest.permission.WRITE_EXTERNAL_STORAGE) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(Manifest.permission.WRITE_EXTERNAL_STORAGE), 102)
        }
    }

    private fun saveTrack() {
        if (!hasRing) return
        webView.evaluateJavascript("window.getTrack()") { result ->
            val data = result?.trim()?.removeSurrounding("\"") ?: ""
            if (data.isBlank()) {
                Toast.makeText(this, "未获取到轨迹", Toast.LENGTH_SHORT).show()
                return@evaluateJavascript
            }
            val pts = data.split(";").filter { it.contains(",") }
            val ts = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.CHINA).format(Date())
            val dir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS)
            if (!dir.exists()) dir.mkdirs()
            val f = File(dir, "track400_$ts.txt")
            try {
                f.bufferedWriter().use { w ->
                    w.write("# 400m跑道轨迹 ${pts.size}点\n")
                    pts.forEach { w.write("$it\n") }
                }
                status.text = "已保存 ${pts.size} 点\n${f.absolutePath}"
                Toast.makeText(this, "已保存到 Download", Toast.LENGTH_LONG).show()
            } catch (e: Exception) {
                status.text = "保存失败：${e.message}"
            }
        }
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == 102 && grantResults.isNotEmpty() && grantResults[0] != PackageManager.PERMISSION_GRANTED) {
            Toast.makeText(this, "存储权限被拒绝，无法保存文件", Toast.LENGTH_LONG).show()
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        webView.destroy()
    }
}
