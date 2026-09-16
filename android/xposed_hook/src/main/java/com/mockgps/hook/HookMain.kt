package com.mockgps.hook

import android.location.Location
import android.telephony.CellInfo
import android.telephony.TelephonyManager
import android.net.wifi.ScanResult
import android.net.wifi.WifiManager
import android.os.Build
import android.util.Log
import de.robv.android.xposed.IXposedHookLoadPackage
import de.robv.android.xposed.XC_MethodHook
import de.robv.android.xposed.XposedHelpers
import de.robv.android.xposed.callbacks.XC_LoadPackage

/**
 * MockGPS Hook 模块
 *
 * 两个核心作用：
 * 1. 隐藏模拟定位标记：让 Location.isFromMockProvider() / isMock() 永远返回 false，
 *    使咕咚等运动 App 无法检测到模拟定位。
 * 2. 切断基站 / WiFi 定位源：让 TelephonyManager 的 cell info 和 WifiManager 的
 *    scanResults 返回空，使高德/百度地图等 App 无法用基站或 WiFi 定位到真实位置，
 *    只能使用 GPS（我们已通过 MockGPS 注入模拟坐标）。
 */
class HookMain : IXposedHookLoadPackage {

    private val tag = "MockGPS-Hook"

    override fun handleLoadPackage(lpparam: XC_LoadPackage.LoadPackageParam) {
        hookMockFlag(lpparam.classLoader)
        hookCellInfo(lpparam.classLoader)
        hookWifiScan(lpparam.classLoader)
    }

    // ---------- 1. 隐藏模拟定位标记 ----------

    private fun hookMockFlag(classLoader: ClassLoader) {
        // isFromMockProvider() — Android 8~
        try {
            XposedHelpers.findAndHookMethod(
                Location::class.java, "isFromMockProvider",
                object : XC_MethodHook() {
                    override fun afterHookedMethod(param: MethodHookParam) {
                        param.result = false
                    }
                }
            )
        } catch (e: Throwable) {
            Log.e(tag, "hook isFromMockProvider 失败: " + e.message)
        }

        // isMock() — Android S+
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            try {
                XposedHelpers.findAndHookMethod(
                    Location::class.java, "isMock",
                    object : XC_MethodHook() {
                        override fun afterHookedMethod(param: MethodHookParam) {
                            param.result = false
                        }
                    }
                )
            } catch (e: Throwable) {
                Log.e(tag, "hook isMock 失败: " + e.message)
            }
        }
    }

    // ---------- 2. 切断基站定位源 ----------

    private fun hookCellInfo(classLoader: ClassLoader) {
        // getAllCellInfo() — 返回空列表
        try {
            XposedHelpers.findAndHookMethod(
                TelephonyManager::class.java, "getAllCellInfo",
                object : XC_MethodHook() {
                    override fun afterHookedMethod(param: MethodHookParam) {
                        param.result = emptyList<CellInfo>()
                    }
                }
            )
        } catch (e: Throwable) {
            Log.e(tag, "hook getAllCellInfo 失败: " + e.message)
        }

        // getCellLocation() — 返回 null
        try {
            XposedHelpers.findAndHookMethod(
                TelephonyManager::class.java, "getCellLocation",
                object : XC_MethodHook() {
                    override fun afterHookedMethod(param: MethodHookParam) {
                        param.result = null
                    }
                }
            )
        } catch (e: Throwable) {
            Log.e(tag, "hook getCellLocation 失败: " + e.message)
        }

        // getNeighboringCellInfo() — 返回空列表（旧版 API）
        try {
            XposedHelpers.findAndHookMethod(
                TelephonyManager::class.java, "getNeighboringCellInfo",
                object : XC_MethodHook() {
                    override fun afterHookedMethod(param: MethodHookParam) {
                        param.result = emptyList<Any>()
                    }
                }
            )
        } catch (e: Throwable) {
            Log.e(tag, "hook getNeighboringCellInfo 失败: " + e.message)
        }
    }

    // ---------- 3. 切断 WiFi 定位源 ----------

    private fun hookWifiScan(classLoader: ClassLoader) {
        // getScanResults() — 返回空列表
        try {
            XposedHelpers.findAndHookMethod(
                WifiManager::class.java, "getScanResults",
                object : XC_MethodHook() {
                    override fun afterHookedMethod(param: MethodHookParam) {
                        param.result = emptyList<ScanResult>()
                    }
                }
            )
        } catch (e: Throwable) {
            Log.e(tag, "hook getScanResults 失败: " + e.message)
        }
    }
}
