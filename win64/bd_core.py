# -*- coding: utf-8 -*-
"""电池医生 Windows 版 —— 数据层

所有平台相关的能力都集中在这个文件里：WMI 取电池、powercfg 取电池报告、
事件日志取异常关机、netsh 修网络、注册表取启动项与代理设置。

界面层（bd_ui.py）不直接调用系统命令，只调用本文件中的函数，
这样两边可以独立演进。
"""

import ctypes
import json
import os
import re
import shutil
import socket
import string
import subprocess
import sys
import tempfile
import threading
import time

APP_NAME = "电池医生"
VERSION = "1.0-win"
IS_WIN = sys.platform.startswith("win")

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


# --------------------------------------------------------------- 路径
def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def resource_dir():
    """打包成单文件后，随包资源在 _MEIPASS 里"""
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


def data_dir():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    p = os.path.join(base, "PowerWatch")
    try:
        os.makedirs(p, exist_ok=True)
    except Exception:
        p = tempfile.gettempdir()
    return p


def desktop_dir():
    home = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    for p in (os.path.join(home, "Desktop"),
              os.path.join(home, "OneDrive", "Desktop"),
              os.path.join(home, "OneDrive", "桌面"),
              os.path.join(home, "桌面")):
        if os.path.isdir(p):
            return p
    return home


BASE = data_dir()
CSV = os.path.join(BASE, "power.csv")
APPLOG = os.path.join(BASE, "app.log")
INCIDENT = os.path.join(BASE, "incidents.log")
BEAT = os.path.join(BASE, ".heartbeat")
CLEAN = os.path.join(BASE, ".clean_stop")

CSV_HEADER = ("timestamp,iso_time,source,pct,cur_mAh,max_mAh,design_mAh,health_pct,"
              "mA,mV,temp_C,cycle,adapter_id,cpu_limit,charging,note")


# --------------------------------------------------------------- 基础工具
def to_int(s, default=0):
    try:
        return int(float(s))
    except Exception:
        return default


def to_float(s, default=0.0):
    try:
        return float(s)
    except Exception:
        return default


def human(kb):
    if kb < 0:
        return "--"
    if kb >= 1024 * 1024:
        return "%.1f GB" % (kb / 1048576.0)
    if kb >= 1024:
        return "%.0f MB" % (kb / 1024.0)
    return "%d KB" % kb


def dec(raw):
    """Windows 命令行输出编码不统一：先试 UTF-8，再试 GBK"""
    if isinstance(raw, str):
        return raw
    for enc in ("utf-8", "gbk", "mbcs"):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("utf-8", "replace")


def run(args, timeout=15, shell=False):
    try:
        r = subprocess.run(args, capture_output=True, timeout=timeout,
                           shell=shell, creationflags=CREATE_NO_WINDOW)
        return dec(r.stdout), dec(r.stderr), r.returncode
    except subprocess.TimeoutExpired:
        return "", "timeout", 1
    except Exception as e:
        return "", str(e), 1


PS_EXE = None


def _ps_exe():
    global PS_EXE
    if PS_EXE:
        return PS_EXE
    for name in ("powershell.exe", "powershell", "pwsh.exe", "pwsh"):
        p = shutil.which(name)
        if p:
            PS_EXE = p
            break
    if not PS_EXE:
        PS_EXE = "powershell.exe"
    return PS_EXE


def ps(script, timeout=25):
    """执行一段 PowerShell，返回 stdout 文本"""
    pre = ("$ProgressPreference='SilentlyContinue';"
           "$ErrorActionPreference='SilentlyContinue';"
           "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8;")
    args = [_ps_exe(), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
            "-Command", pre + script]
    out, err, rc = run(args, timeout=timeout)
    return out


def ps_json(script, timeout=25, default=None):
    out = ps(script, timeout=timeout).strip()
    if not out:
        return default
    out = out.lstrip("\ufeff")
    try:
        return json.loads(out)
    except Exception:
        # 单对象/多对象差异时兜底：截取最外层 JSON
        m = re.search(r"[\[{].*[\]}]", out, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    return default


def as_list(x):
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def elevate():
    """以管理员身份重新启动自身"""
    try:
        if getattr(sys, "frozen", False):
            exe, params = sys.executable, ""
        else:
            exe = sys.executable
            params = '"%s"' % os.path.join(app_dir(), "main.py")
        ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, None, 1)
        return True
    except Exception:
        return False


def open_path(path):
    try:
        os.startfile(path)  # noqa: 只在 Windows 上存在
        return True
    except Exception:
        return False


def log(text):
    try:
        with open(APPLOG, "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), text))
    except Exception:
        pass


def notify(title, msg):
    """任务栏闪烁 + 提示音。系统通知需要额外组件，这里用最稳的方式"""
    try:
        ctypes.windll.user32.MessageBeep(0x40)
    except Exception:
        pass
    log("[通知] %s: %s" % (title, msg))


# --------------------------------------------------------------- 电池
_REPORT_CACHE = {"t": 0, "design": 0, "full": 0, "cycle": 0, "name": ""}


def battery_report(force=False):
    """powercfg /batteryreport 的 XML 里有设计容量、满充容量和循环次数。
    生成一次需要 1~3 秒，所以缓存 10 分钟。"""
    now = time.time()
    if not force and now - _REPORT_CACHE["t"] < 600:
        return _REPORT_CACHE
    tmp = os.path.join(tempfile.gettempdir(), "bd_battery_report.xml")
    try:
        if os.path.exists(tmp):
            os.remove(tmp)
    except Exception:
        pass
    run(["powercfg", "/batteryreport", "/xml", "/output", tmp], timeout=40, shell=False)
    try:
        with open(tmp, "r", encoding="utf-8", errors="ignore") as f:
            xml = f.read()
    except Exception:
        xml = ""
    m = re.search(r"<Battery>.*?</Battery>", xml, re.S)
    block = m.group(0) if m else xml

    def grab(tag):
        mm = re.search(r"<%s>(\d+)</%s>" % (tag, tag), block)
        return to_int(mm.group(1)) if mm else 0

    _REPORT_CACHE.update({
        "t": now,
        "design": grab("DesignCapacity"),
        "full": grab("FullChargeCapacity"),
        "cycle": grab("CycleCount"),
        "name": (re.search(r"<Id>(.*?)</Id>", block).group(1)
                 if re.search(r"<Id>(.*?)</Id>", block) else ""),
    })
    return _REPORT_CACHE


class Battery:
    """字段名与 Mac 版保持一致，方便界面层复用"""

    def __init__(self):
        self.ok = False
        self.pct = 0
        self.cur = 0          # 当前容量 mWh（界面里当 mAh 展示，单位不同不影响判断）
        self.maxcap = 0
        self.design = 0
        self.health = 0
        self.ma = 0           # 电流 mA（放电为负）
        self.volt = 0         # mV
        self.temp = 0         # 0.1℃
        self.cycle = 0
        self.source = "?"
        self.charging = "No"
        self.adapter = "na"
        self.limit = None
        self.cells = []
        self.imbalance = 0
        self.runtime = -1     # 预计剩余分钟
        self.online = False
        self.has_battery = False
        self.note = ""

    @property
    def temp_c(self):
        return round(self.temp / 100.0, 1)

    @property
    def on_ac(self):
        return self.source == "电源"

    @classmethod
    def read(cls):
        b = cls()
        script = r"""
$w = Get-CimInstance Win32_Battery -EA 0 | Select-Object -First 1
$s = Get-CimInstance -Namespace root/wmi -ClassName BatteryStatus -EA 0 | Select-Object -First 1
$t = Get-CimInstance -Namespace root/wmi -ClassName MSAcpi_ThermalZoneTemperature -EA 0 | Select-Object -First 1
$o = [ordered]@{
  has   = [bool]($w -ne $null)
  pct   = [int]$w.EstimatedChargeRemaining
  stat  = [int]$w.BatteryStatus
  run   = [int]$w.EstimatedRunTime
  volt  = [int]$s.Voltage
  dis   = [int]$s.DischargeRate
  chg   = [int]$s.ChargeRate
  online= [bool]$s.PowerOnline
  rem   = [int]$s.RemainingCapacity
  dwmi  = [int]$s.DesignedCapacity
  fwmi  = [int]$s.FullChargedCapacity
  cycle = [int]$s.CycleCount
  tz    = [int]$t.CurrentTemperature
}
$o | ConvertTo-Json -Compress
"""
        d = ps_json(script, timeout=20, default={}) or {}
        b.has_battery = bool(d.get("has"))
        b.pct = to_int(d.get("pct"))
        stat = to_int(d.get("stat"))          # 1=放电 2=接电 3=充满 4=低电量 5=严重低 6=充电中 7=充电+高 8=充电+低 9=充电+严重低
        b.volt = max(0, to_int(d.get("volt")))
        dis = to_int(d.get("dis"))
        chg = to_int(d.get("chg"))
        b.online = bool(d.get("online")) or stat in (2, 3, 6, 7, 8, 9)
        b.source = "电源" if b.online else "电池"
        b.charging = "Yes" if stat in (6, 7, 8, 9) or chg > 0 else "No"
        b.runtime = to_int(d.get("run"), -1)
        if b.runtime >= 71582788 or b.runtime <= 0:
            b.runtime = -1

        b.cur = to_int(d.get("rem"))
        b.maxcap = to_int(d.get("fwmi"))
        b.design = to_int(d.get("dwmi"))
        b.cycle = to_int(d.get("cycle"))

        rep = battery_report()
        if rep["design"] > 0 and b.design <= 0:
            b.design = rep["design"]
        if rep["full"] > 0 and b.maxcap <= 0:
            b.maxcap = rep["full"]
        if rep["cycle"] > 0 and b.cycle <= 0:
            b.cycle = rep["cycle"]
        if rep["design"] > 0 and b.design <= 0:
            b.design = rep["design"]

        # 电流：mW / mV = mA
        if b.volt > 0:
            if dis > 0:
                b.ma = -int(dis * 1000.0 / b.volt)
            elif chg > 0:
                b.ma = int(chg * 1000.0 / b.volt)

        # 健康度
        if b.maxcap > 0 and b.design > 0:
            b.health = int(b.maxcap * 100 / b.design)
        elif b.design > 0 and b.maxcap > 0:
            b.health = int(b.maxcap * 100 / b.design)

        tz = to_int(d.get("tz"))          # 开尔文 * 10
        if tz > 1000:
            b.temp = int((tz / 10.0 - 273.15) * 100)

        b.adapter = "ok" if b.online else "na"
        b.ok = b.has_battery
        if not b.has_battery:
            b.note = "没有检测到电池（台式机或电池未被系统识别）"
        return b

    def explain(self):
        """返回 (等级, 标题, 说明, 建议列表)"""
        issues = []
        if self.ma < -300 and self.online:
            issues.append(("red", "接着电源，但电却是电池在放"))
        if self.health and self.health < 60:
            issues.append(("red", "电池容量只剩 %d%%，接近寿命终点" % self.health))
        elif self.health and self.health < 80:
            issues.append(("amber", "电池容量剩 %d%%，建议安排更换" % self.health))
        if self.temp and self.temp_c >= 75:
            issues.append(("red", "电池温度 %.0f℃，已经进入危险区间" % self.temp_c))
        elif self.temp and self.temp_c >= 60:
            issues.append(("amber", "电池温度 %.0f℃，偏热" % self.temp_c))
        if not self.on_ac and self.pct and self.pct < 15:
            issues.append(("red", "电量只剩 %d%%，随时可能关机" % self.pct))
        if self.cycle and self.cycle > 800 and (not self.health or self.health < 85):
            issues.append(("amber", "已经充放 %d 次，属于高损耗电池" % self.cycle))

        if not issues:
            if not self.has_battery:
                return ("amber", "这台机器没有可读的电池",
                        "台式机不需要电池诊断。如果你用的是笔记本，"
                        "可能是电池驱动或主板没能上报状态。",
                        ["在设备管理器里看一眼「电池」分类是否有黄色感叹号"])
            return ("green", "一切正常",
                    "供电稳定，电池状态良好。我会每 5 秒看一次，有变化再告诉你。",
                    [])
        level = "red" if any(i[0] == "red" for i in issues) else "amber"
        head = issues[0][1]
        if len(issues) > 1:
            desc = "另外还有 %d 项：%s。" % (len(issues) - 1,
                                          "；".join(t for _, t in issues[1:]))
        else:
            desc = "这一项通常可以处理，先按下面的顺序试一遍。"
        steps = []
        if self.ma < -300 and self.online:
            steps += ["换一个原装充电器再试一次，排除适配器功率不足",
                      "换一个插座，并检查充电线接口是否松动",
                      "电池老化后也会出现「插电仍放电」，建议先看后面的电池容量结论"]
        if self.health and self.health < 80:
            steps.append("电池已老化，建议更换原厂或正规品牌电池")
        if self.temp and self.temp_c >= 60:
            steps += ["垫高机身、清理出风口灰尘，别在床上或沙发上用",
                      "用任务管理器看一眼有没有进程长期占满 CPU"]
        if not self.on_ac and self.pct and self.pct < 15:
            steps.append("先接电源，重要文件随手保存")
        if not steps:
            steps = ["保持出风口通畅，别在被子、沙发等不易散热的地方使用"]
        return (level, head, desc, steps)


# --------------------------------------------------------------- 进程
_TOTAL_RAM = {"v": 0}


def total_ram_mb():
    if _TOTAL_RAM["v"]:
        return _TOTAL_RAM["v"]
    d = ps_json("(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory", 15, 0)
    _TOTAL_RAM["v"] = max(1, to_int(d) // (1024 * 1024))
    return _TOTAL_RAM["v"]


def read_processes(limit=60):
    """返回 (rows, error)；rows = (pid, cpu%, mem%, rss_kb, name, path)"""
    script = r"""
$d = Get-CimInstance Win32_PerfFormattedData_PerfProc_Process -EA 0 |
     Where-Object { $_.Name -ne '_Total' -and $_.Name -ne 'Idle' } |
     Sort-Object PercentProcessorTime -Descending | Select-Object -First %d
$d | ForEach-Object {
  $p = Get-Process -Id $_.IDProcess -EA 0
  [pscustomobject]@{
    pid  = [int]$_.IDProcess
    cpu  = [int]$_.PercentProcessorTime
    rss  = [long]$p.WorkingSet64
    name = if ($p) { $p.ProcessName } else { $_.Name }
    path = if ($p) { $p.Path } else { '' }
  }
} | ConvertTo-Json -Compress
""" % limit
    data = ps_json(script, timeout=25, default=[])
    rows = []
    ram = total_ram_mb()
    for it in as_list(data):
        pid = to_int(it.get("pid"))
        if pid <= 0:
            continue
        rss_kb = to_int(it.get("rss")) // 1024
        mem = round(rss_kb / 1024.0 * 100.0 / ram, 1) if ram else 0.0
        name = (it.get("name") or "?").strip()
        path = (it.get("path") or "").strip()
        rows.append((pid, float(to_int(it.get("cpu"))), mem, rss_kb, name, path))
    rows.sort(key=lambda x: (-x[1], -x[3]))
    if not rows:
        return None, "没能读到进程列表（可能被安全软件拦截）"
    return rows, None


def kill_process(pid):
    out, err, rc = run(["taskkill", "/PID", str(pid), "/F"], timeout=15)
    return rc == 0, (out or err).strip()[:120]


def cpu_load():
    d = ps_json("(Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average",
                12, 0)
    return to_int(d)


def cpu_name():
    return (ps("(Get-CimInstance Win32_Processor | Select-Object -First 1).Name", 12) or "").strip()


# --------------------------------------------------------------- 存储
def du_kb(path, budget=20.0):
    """统计目录大小，超过预算秒数就提前返回已统计部分"""
    p = os.path.expandvars(os.path.expanduser(path))
    if not p or not os.path.exists(p):
        return -1
    total, start = 0, time.time()
    try:
        for root, dirs, files in os.walk(p, onerror=lambda e: None):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                except Exception:
                    pass
            if time.time() - start > budget:
                break
    except Exception:
        return -1
    return total // 1024


def drives():
    """返回 [(盘符, 总GB, 已用GB, 剩余GB, 占用率)]"""
    out = []
    for L in string.ascii_uppercase:
        root = "%s:\\" % L
        if not os.path.exists(root):
            continue
        try:
            t, u, f = shutil.disk_usage(root)
        except Exception:
            continue
        out.append((L, t / 2 ** 30, u / 2 ** 30, f / 2 ** 30,
                    int(u * 100 / t) if t else 0))
    return out


def storage_targets():
    home = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    la = os.environ.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local")
    roaming = os.environ.get("APPDATA") or os.path.join(home, "AppData", "Roaming")
    tmp = os.environ.get("TEMP") or os.path.join(la, "Temp")
    return [
        ("微信聊天记录", os.path.join(home, "Documents", "WeChat Files")),
        ("企业微信", os.path.join(home, "Documents", "WXWork")),
        ("下载", os.path.join(home, "Downloads")),
        ("桌面", os.path.join(home, "Desktop")),
        ("用户临时文件", tmp),
        ("Windows 临时文件", r"C:\Windows\Temp"),
        ("浏览器缓存 Chrome", os.path.join(la, "Google", "Chrome", "User Data", "Default", "Cache")),
        ("浏览器缓存 Edge", os.path.join(la, "Microsoft", "Edge", "User Data", "Default", "Cache")),
        ("应用数据 AppData", la),
        ("漫游数据 Roaming", roaming),
        ("视频", os.path.join(home, "Videos")),
        ("图片", os.path.join(home, "Pictures")),
        ("Docker 镜像", os.path.join(la, "Docker")),
        ("Windows 更新缓存", r"C:\Windows\SoftwareDistribution\Download"),
    ]


def disk_health():
    d = ps_json(r"Get-PhysicalDisk -EA 0 | Select-Object FriendlyName,MediaType,HealthStatus,"
                r"@{n='Size';e={[long]$_.Size}} | ConvertTo-Json -Compress", 20, [])
    out = []
    for it in as_list(d):
        out.append((it.get("FriendlyName") or "磁盘",
                    it.get("MediaType") or "-",
                    it.get("HealthStatus") or "-",
                    to_int(it.get("Size")) / 2 ** 30))
    return out


def clean_temp():
    """清理临时文件，返回 (释放KB, 说明)"""
    freed, removed, failed = 0, 0, 0
    targets = [os.environ.get("TEMP") or "",
               r"C:\Windows\Temp"]
    for t in targets:
        if not t or not os.path.isdir(t):
            continue
        for name in os.listdir(t):
            p = os.path.join(t, name)
            try:
                is_dir = os.path.isdir(p)
                size = du_kb(p, budget=3) if is_dir else os.path.getsize(p) // 1024
                if is_dir:
                    shutil.rmtree(p, ignore_errors=True)
                else:
                    os.remove(p)
                freed += max(0, size)
                removed += 1
            except Exception:
                failed += 1
    return freed, "清理 %d 项，%d 项被占用跳过" % (removed, failed)


# --------------------------------------------------------------- 启动项
def startup_items():
    """返回 [(名称, 命令, 位置, 用户)]"""
    d = ps_json(r"Get-CimInstance Win32_StartupCommand -EA 0 | "
                r"Select-Object Name,Command,Location,User | ConvertTo-Json -Compress", 25, [])
    out = []
    for it in as_list(d):
        out.append(((it.get("Name") or "?").strip(),
                    (it.get("Command") or "").strip(),
                    (it.get("Location") or "").strip(),
                    (it.get("User") or "").strip()))
    seen, uniq = set(), []
    for it in out:
        k = (it[0].lower(), it[1].lower())
        if k in seen:
            continue
        seen.add(k)
        uniq.append(it)
    return uniq


def disable_startup(name, command):
    """把启动项移出注册表 Run 键（改名备份到 REG_BACKUP），返回 (ok, msg)"""
    import winreg
    keys = [(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run"),
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\RunOnce"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\RunOnce")]
    for hive, sub in keys:
        try:
            k = winreg.OpenKey(hive, sub, 0, winreg.KEY_ALL_ACCESS)
        except Exception:
            continue
        try:
            i = 0
            while True:
                try:
                    n, v, _ = winreg.EnumValue(k, i)
                except OSError:
                    break
                i += 1
                if n.lower() == name.lower():
                    winreg.SetValueEx(k, "BD_OFF_" + n, 0, winreg.REG_SZ, v)
                    winreg.DeleteValue(k, n)
                    winreg.CloseKey(k)
                    return True, "已禁用 %s（可用「恢复」找回）" % n
        finally:
            try:
                winreg.CloseKey(k)
            except Exception:
                pass
    return False, "注册表里没找到这一项（可能来自启动文件夹）"


# --------------------------------------------------------------- 关机事件
_EVT = {"t": 0, "data": []}


def shutdown_events(limit=30, force=False):
    """异常关机记录。事件 41 = 断电/掉电导致的非正常关机，这是判断
    「用一会儿就关机」最直接的证据。"""
    now = time.time()
    if not force and now - _EVT["t"] < 120:
        return _EVT["data"]
    n = max(5, int(limit))
    script = r"""
$f = @{LogName='System'; Id=41,6008,1074,1001,109,42}
Get-WinEvent -FilterHashtable $f -MaxEvents %d -EA 0 | ForEach-Object {
  [pscustomobject]@{
    id   = [int]$_.Id
    time = $_.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss')
    provider = $_.ProviderName
    msg  = (($_.Message -split "`r?`n")[0])
  }
} | ConvertTo-Json -Compress
""" % n
    d = ps_json(script, timeout=40, default=[])
    out = []
    for it in as_list(d):
        out.append({"id": to_int(it.get("id")),
                    "time": it.get("time") or "",
                    "provider": it.get("provider") or "",
                    "msg": (it.get("msg") or "")[:180]})
    _EVT.update({"t": now, "data": out})
    return out


def event_name(eid):
    return {
        41: ("red", "非正常断电", "电脑没走正常关机流程就断电了 —— 电池、供电或主板保护"),
        6008: ("red", "上次关机是意外的", "系统记录到上次关机未正常完成"),
        1074: ("info", "正常关机/重启", "有程序或用户触发了关机"),
        109: ("amber", "内核发起关机", "内核主动断电，常见于过热保护或驱动异常"),
        42: ("info", "进入睡眠", "系统进入睡眠状态"),
        1001: ("amber", "蓝屏记录", "系统崩溃并重启"),
    }.get(eid, ("info", "系统事件", ""))


def last_boot():
    d = ps_json(r"$o=Get-CimInstance Win32_OperatingSystem;"
                r"[pscustomobject]@{boot=$o.LastBootUpTime.ToString('yyyy-MM-dd HH:mm:ss');"
                r"up=[int]((Get-Date)-$o.LastBootUpTime).TotalMinutes} | ConvertTo-Json -Compress", 15, {})
    return d.get("boot", ""), to_int(d.get("up"))


# --------------------------------------------------------------- 电源与散热
def power_scheme():
    out, _, _ = run(["powercfg", "/getactivescheme"], 12)
    m = re.search(r"\((.*?)\)", out or "")
    guid = re.search(r"([0-9a-fA-F-]{36})", out or "")
    name = m.group(1) if m else "--"
    # 中文系统输出形如：电源方案 GUID: xxx  (平衡)
    return name.strip(), guid.group(1) if guid else ""


def fast_startup():
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                           r"SYSTEM\CurrentControlSet\Control\Session Manager\Power")
        v, _ = winreg.QueryValueEx(k, "HiberbootEnabled")
        return bool(v)
    except Exception:
        return False


def thermal_limit():
    """CPU 是否被降频：当前频率 / 最大频率"""
    d = ps_json(r"$c=Get-CimInstance Win32_Processor | Select-Object -First 1;"
                r"[pscustomobject]@{cur=[int]$c.CurrentClockSpeed;max=[int]$c.MaxClockSpeed} "
                r"| ConvertTo-Json -Compress", 12, {})
    cur, mx = to_int(d.get("cur")), to_int(d.get("max"))
    if mx > 0 and cur > 0:
        return int(cur * 100 / mx)
    return None


# --------------------------------------------------------------- 网络
NET_CHECKS = [("wifi", "网络连接"), ("signal", "信号质量"), ("ip", "IP 地址"),
              ("gateway", "默认网关"), ("dns", "域名解析"),
              ("internet", "外网连通"), ("proxy", "系统代理"),
              ("hosts", "hosts 文件")]

DNS_SUGGEST = ["223.5.5.5", "119.29.29.29"]


def net_cmd(args, timeout=15):
    out, err, rc = run(args, timeout=timeout, shell=False)
    return (out + "\n" + err).strip(), rc


def _net_fallback_ipconfig():
    """老系统没有 Get-NetIPConfiguration 时，退回解析 ipconfig 输出"""
    d = {"adapter": "", "type": "", "ssid": "", "signal": 0,
         "ip": "", "gw": "", "dns": [], "mac": ""}
    out, _ = net_cmd(["ipconfig", "/all"], 20)
    cur, grab_dns = "", False
    for line in out.splitlines():
        s = line.strip()
        if not s:
            grab_dns = False
            continue
        if line and not line.startswith(" ") and s.endswith(":") and "Windows" not in s:
            cur = s.rstrip(":")
            grab_dns = False
            if d["ip"]:
                continue
            d["adapter"] = cur
            continue
        if not d["adapter"] or cur != d["adapter"]:
            continue
        low = s.lower()
        if ("ipv4" in low or "IPv4 地址" in s) and ":" in s and not d["ip"]:
            val = s.split(":", 1)[1].strip()
            if "(" in val:
                val = val.split("(")[0].strip()
            d["ip"] = val
        elif ("默认网关" in s or "default gateway" in low) and not d["gw"]:
            val = s.split(":", 1)[-1].strip()
            if val and val[0].isdigit():
                d["gw"] = val.split()[0]
        elif "物理地址" in s or "physical address" in low:
            d["mac"] = s.split(":")[-1].strip()[-17:]
        elif "dns 服务器" in s.lower() or "dns servers" in low:
            val = s.split(":", 1)[-1].strip()
            if val and val.replace(".", "").isdigit():
                d["dns"].append(val)
            grab_dns = True
        elif grab_dns and s.replace(".", "").replace(":", "").isdigit():
            d["dns"].append(s)
    if "无线" in d["adapter"] or "Wi-Fi" in d["adapter"] or "WLAN" in d["adapter"]:
        d["type"] = "无线"
    elif d["adapter"]:
        d["type"] = "有线"
    return d


def net_basic():
    d = {"adapter": "", "type": "", "ssid": "", "signal": 0,
         "ip": "", "gw": "", "dns": [], "mac": ""}
    raw = ps(r"""
$c = Get-NetIPConfiguration -EA 0 | Where-Object { $_.NetAdapter.Status -eq 'Up' } | Select-Object -First 1
if ($c) {
  "$($c.InterfaceAlias)|$($c.NetAdapter.InterfaceDescription)|$(($c.IPv4Address.IPAddress) -join ',')|$(($c.IPv4DefaultGateway.NextHop) -join ',')|$(($c.DNSServer.ServerAddresses) -join ',')|$($c.NetAdapter.MacAddress)"
}
""", 20).strip()
    if raw and "|" in raw:
        parts = raw.split("|")
        while len(parts) < 6:
            parts.append("")
        d["adapter"], desc, ip, gw, dns, mac = parts[:6]
        d["type"] = "无线" if ("Wi" in desc or "Wireless" in desc or "802.11" in desc
                              or "WLAN" in desc) else "有线"
        d["ip"] = ip.split(",")[0].strip()
        d["gw"] = gw.split(",")[0].strip()
        d["dns"] = [x.strip() for x in dns.split(",") if x.strip()]
        d["mac"] = mac.strip()

    out, _ = net_cmd(["netsh", "wlan", "show", "interfaces"], 12)
    ssid, sig = "", 0
    for line in (out or "").splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k, v = k.strip(), v.strip()
        if k.upper() == "SSID" and v:
            ssid = v
        if k in ("信号", "Signal") and "%" in v:
            sig = to_int(v.replace("%", ""))
    if not d["adapter"]:
        fb = _net_fallback_ipconfig()
        fb["ssid"], fb["signal"] = ssid, sig
        return fb
    d["ssid"], d["signal"] = ssid or d["ssid"], sig
    return d


def port_open(host, port, timeout=3):
    try:
        with socket.create_connection((host, port), timeout):
            return True
    except Exception:
        return False


def dns_probe(name="www.baidu.com"):
    t = time.time()
    try:
        socket.getaddrinfo(name, 443)
        return int((time.time() - t) * 1000), True
    except Exception:
        return -1, False


def ping_avg(host, count=2):
    out, _ = net_cmd(["ping", "-n", str(count), "-w", "1500", host], 12)
    for line in out.splitlines():
        low = line.lower()
        if ("平均" in line or "average" in low) and "=" in line:
            tail = line.split("=")[-1].strip().replace("ms", "").strip()
            return to_int(tail, -1)
    return -1


def proxy_state():
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                           r"Software\Microsoft\Windows\CurrentVersion\Internet Settings")
        en, _ = winreg.QueryValueEx(k, "ProxyEnable")
        srv = ""
        try:
            srv, _ = winreg.QueryValueEx(k, "ProxyServer")
        except Exception:
            pass
        return bool(en), (srv or "")
    except Exception:
        return False, ""


def set_proxy_off():
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                           r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
                           0, winreg.KEY_ALL_ACCESS)
        winreg.SetValueEx(k, "ProxyEnable", 0, winreg.REG_DWORD, 0)
        winreg.CloseKey(k)
        return True
    except Exception:
        return False


def hosts_path():
    return os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                        "System32", "drivers", "etc", "hosts")


def hosts_suspicious():
    p = hosts_path()
    hits, total = [], 0
    try:
        with open(p, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                s = line.split("#")[0].strip()
                if not s or len(s.split()) < 2:
                    continue
                total += 1
                ip, host = s.split()[0], s.split()[1].lower()
                if ip in ("0.0.0.0", "127.0.0.1") and not host.startswith("localhost"):
                    hits.append(host)
    except Exception:
        return 0, []
    return total, hits[:8]


def set_dns(adapter, servers):
    """改 DNS 需要管理员权限"""
    ok = True
    msgs = []
    cmds = [["netsh", "interface", "ip", "set", "dns", "name=%s" % adapter,
             "static", servers[0], "primary"]]
    if len(servers) > 1:
        cmds.append(["netsh", "interface", "ip", "add", "dns", "name=%s" % adapter,
                     servers[1], "index=2"])
    for c in cmds:
        out, rc = net_cmd(c, 20)
        if rc != 0:
            ok = False
            msgs.append(out[:100])
    return ok, "; ".join(msgs)


def flush_dns():
    out, rc = net_cmd(["ipconfig", "/flushdns"], 20)
    return rc == 0, out[:120]


def renew_ip(adapter):
    net_cmd(["ipconfig", "/release"], 25)
    out, rc = net_cmd(["ipconfig", "/renew"], 45)
    return rc == 0, out[:120]


def reset_winsock():
    out, rc = net_cmd(["netsh", "winsock", "reset"], 30)
    return rc == 0, out[:160]


def reset_tcpip():
    out, rc = net_cmd(["netsh", "int", "ip", "reset"], 30)
    return rc == 0, out[:160]


def restart_adapter(adapter):
    out = ps("Restart-NetAdapter -Name '%s' -Confirm:$false" % adapter.replace("'", "''"), 40)
    return "error" not in (out or "").lower()


def battery_report_html():
    """生成官方电池报告，返回文件路径"""
    out = os.path.join(desktop_dir(), "电池报告-%s.html" % time.strftime("%Y%m%d-%H%M"))
    run(["powercfg", "/batteryreport", "/output", out], 45)
    return out if os.path.exists(out) else ""
