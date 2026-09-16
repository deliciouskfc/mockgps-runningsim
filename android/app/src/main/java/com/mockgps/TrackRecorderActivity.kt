package com.mockgps

import android.Manifest
import android.app.Activity
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.Typeface
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.Bundle
import android.os.Environment
import android.view.Gravity
import android.view.WindowManager
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * 轨迹记录器：明天带手机去操场走一圈，记录真实 GPS 轨迹。
 * 保存格式：每行 "纬度,经度"（mock_route.py 可直接回放）。
 * 文件保存到 /sdcard/Download/，可微信发送或 adb pull 取回电脑。
 */
class TrackRecorderActivity : Activity(), LocationListener {

    private lateinit var status: TextView
    private lateinit var hint: TextView
    private lateinit var btnMain: Button
    private lateinit var lm: LocationManager
    private var recording = false
    private val points = ArrayList<String>()
    private var startTime = 0L
    private var lastLoc: Location? = null
    private var totalDist = 0f

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        lm = getSystemService(LOCATION_SERVICE) as LocationManager

        val pad = (resources.displayMetrics.density * 16).toInt()
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(pad, pad, pad, pad)
            setBackgroundColor(Color.WHITE)
        }
        val title = TextView(this).apply {
            text = "轨迹记录器"
            textSize = 26f
            setTypeface(null, Typeface.BOLD)
            gravity = Gravity.CENTER
        }
        status = TextView(this).apply {
            text = "未开始记录"
            textSize = 20f
            gravity = Gravity.CENTER
            setPadding(0, pad, 0, pad)
        }
        btnMain = Button(this).apply {
            text = "开始记录"
            textSize = 20f
            setOnClickListener { toggle() }
        }
        hint = TextView(this).apply {
            text = "提示：走完一圈点「停止并保存」，文件保存在 Download 目录。\n回电脑后可 adb pull 取回，或微信发送后转存。"
            textSize = 14f
            gravity = Gravity.CENTER
            setPadding(0, pad, 0, 0)
        }
        root.addView(title)
        root.addView(status)
        root.addView(btnMain)
        root.addView(hint)
        setContentView(root)

        if (checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION)
            != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(
                Manifest.permission.ACCESS_FINE_LOCATION,
                Manifest.permission.ACCESS_COARSE_LOCATION), 100)
        }
    }

    override fun onResume() {
        super.onResume()
        if (checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION)
            == PackageManager.PERMISSION_GRANTED) {
            lm.requestLocationUpdates(LocationManager.GPS_PROVIDER, 1000L, 0f, this)
        }
    }

    override fun onPause() {
        super.onPause()
        lm.removeUpdates(this)
    }

    private fun toggle() {
        if (!recording) {
            points.clear()
            totalDist = 0f
            lastLoc = null
            startTime = System.currentTimeMillis()
            recording = true
            btnMain.text = "停止并保存"
            status.text = "记录中...\n等待 GPS 信号"
        } else {
            recording = false
            stopAndSave()
        }
    }

    private fun stopAndSave() {
        val ts = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.CHINA).format(Date())
        val dir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS)
        if (!dir.exists()) dir.mkdirs()
        val f = File(dir, "track_$ts.txt")
        try {
            f.bufferedWriter().use { w ->
                w.write("# 操场轨迹 ${points.size}点 ${(totalDist / 1000).format(2)}km\n")
                points.forEach { w.write(it + "\n") }
            }
            btnMain.text = "开始记录"
            status.text = "已保存 ${points.size} 个点\n距离 ${(totalDist / 1000).format(2)} km\n\n文件：\n${f.absolutePath}"
            Toast.makeText(this, "已保存到 Download", Toast.LENGTH_LONG).show()
        } catch (e: Exception) {
            status.text = "保存失败：${e.message}"
        }
    }

    override fun onLocationChanged(l: Location) {
        lastLoc?.let { totalDist += it.distanceTo(l) }
        lastLoc = l
        if (recording) {
            points.add("%.7f,%.7f".format(l.latitude, l.longitude))
            val secs = (System.currentTimeMillis() - startTime) / 1000
            status.text = "记录中...\n点数 ${points.size}\n距离 ${(totalDist / 1000).format(2)} km\n用时 ${secs / 60}:${"%02d".format(secs % 60)}\n精度 ${"%.0f".format(l.accuracy)}m"
        }
    }

    private fun Float.format(d: Int) = "%.${d}f".format(this)

    @Deprecated("Deprecated in Java")
    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == 100 && grantResults.isNotEmpty() &&
            grantResults[0] == PackageManager.PERMISSION_GRANTED) {
            onResume()
        } else {
            Toast.makeText(this, "需要定位权限才能记录轨迹", Toast.LENGTH_LONG).show()
        }
    }
}
