#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""电池医生 Battery Doctor — Mac 电池与性能体检工具"""

import concurrent.futures
import csv
import datetime
import glob
import json
import math
import os
import plistlib
import queue
import re
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
import urllib.request
from tkinter import ttk, messagebox

APP_NAME = "电池医生"
VERSION = "3.7"

BASE = os.path.expanduser("~/Library/Logs/PowerWatch")
CSV = os.path.join(BASE, "power.csv")
INC = os.path.join(BASE, "incidents.log")
BEAT = os.path.join(BASE, ".heartbeat")
CLEAN = os.path.join(BASE, ".clean_stop")
APPLOG = os.path.join(BASE, "app.log")
BACKUP = os.path.expanduser("~/Library/.batterydoctor-backup")

FONT = "PingFang SC"
MONO = "Menlo"

# 柔和、低刺激的配色：只有真正严重的问题才用暖红
P = {
    "bg":       "#F6F6F3",
    "sidebar":  "#EEEEE9",
    "sb_hover": "#E5E5DE",
    "card":     "#FFFFFF",
    "card2":    "#FBFBF9",
    "hover":    "#F7F7F3",
    "line":     "#E6E6DF",
    "line2":    "#EFEFE9",
    "text":     "#1C1C1E",
    "text2":    "#4A4A4E",
    "muted":    "#8B8B90",
    "faint":    "#AFAFB4",
    "track":    "#ECECE6",
    "accent":   "#2F7D66",
    "accent2":  "#276A57",
    "accent_soft": "#E9F3EF",
    "green":    "#2F7D66",
    "green_soft": "#EAF4F0",
    "green_line": "#CBE3DA",
    "amber":    "#A9721C",
    "amber_soft": "#FBF2E1",
    "amber_line": "#EBD9B7",
    "red":      "#B8554A",
    "red_soft":  "#FBEBE8",
    "red_line":  "#F0CDC7",
    "blue":     "#3D6C97",
    "blue_soft": "#EDF2F8",
}

USER_AGENTS = [
    "cn.macx.MacAppBoxHelper.plist",
    "com.adobe.AAM.Updater-1.0.plist",
    "com.google.keystone.agent.plist",
    "com.google.keystone.xpcservice.plist",
    "com.antssWu.shadowsocksX-NG.http.plist",
    "com.antssWu.shadowsocksX-NG.local.plist",
    "com.yicheng.ShadowsocksX-R.local.plist",
    "org.getlantern.plist",
    "org.virtualbox.vboxwebsrv.plist",
]

SYSTEM_AGENTS = [
    "/Library/LaunchDaemons/com.teamviewer.Helper.plist",
    "/Library/LaunchDaemons/com.teamviewer.teamviewer_service.plist",
    "/Library/LaunchAgents/com.teamviewer.teamviewer.plist",
    "/Library/LaunchAgents/com.teamviewer.teamviewer_desktop.plist",
    "/Library/LaunchDaemons/com.citrix.ctxusbd.plist",
    "/Library/LaunchDaemons/com.citrix.ctxworkspaceupdater.plist",
    "/Library/LaunchAgents/com.citrix.AuthManager_Mac.plist",
    "/Library/LaunchAgents/com.citrix.ReceiverHelper.plist",
    "/Library/LaunchAgents/com.citrix.ServiceRecords.plist",
    "/Library/LaunchAgents/com.citrix.safariadapter.plist",
    "/Library/LaunchDaemons/us.zoom.ZoomDaemon.plist",
    "/Library/LaunchDaemons/com.adobe.SwitchBoard.plist",
    "/Library/LaunchDaemons/com.microsoft.teams.TeamsUpdaterDaemon.plist",
    "/Library/LaunchDaemons/org.virtualbox.startup.plist",
    "/Library/LaunchDaemons/com.BlueStacks.AppPlayer.bstservice_helper.plist",
    "/Library/LaunchDaemons/com.netease.nemu.startup.plist",
]

STORAGE_TARGETS = [
    ("微信数据", "~/Library/Containers/com.tencent.xinWeChat"),
    ("企业微信", "~/Library/Containers/com.tencent.WeWorkMac"),
    ("Docker", "~/Library/Containers/com.docker.docker"),
    ("用户缓存", "~/Library/Caches"),
    ("下载", "~/Downloads"),
    ("应用程序支持", "~/Library/Application Support"),
    ("文档", "~/Documents"),
    ("废纸篓", "~/.Trash"),
    ("系统日志", "~/Library/Logs"),
    ("Xcode 数据", "~/Library/Developer"),
]

CSV_HEADER = ("timestamp,iso_time,source,pct,cur_mAh,max_mAh,design_mAh,health_pct,"
              "mA,mV,temp_C,cycle,adapter_id,cpu_limit,charging,note")


# ----------------------------------------------------------------- 基础工具
def run_cmd(args, timeout=8):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return r.stdout
    except Exception:
        return ""


def to_int(s, default=0):
    try:
        return int(s)
    except Exception:
        return default


def human(kb):
    if kb >= 1024 * 1024:
        return "%.1f GB" % (kb / 1048576.0)
    if kb >= 1024:
        return "%.0f MB" % (kb / 1024.0)
    return "%d KB" % kb


def round_rect(c, x1, y1, x2, y2, r, **kw):
    """在 Canvas 上画圆角矩形，返回 item id"""
    r = min(r, abs(x2 - x1) / 2.0, abs(y2 - y1) / 2.0)
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
           x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
           x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return c.create_polygon(pts, smooth=True, **kw)


def walk(widget):
    yield widget
    for ch in widget.winfo_children():
        for w in walk(ch):
            yield w


def recolor(widget, new_bg, only=None):
    for w in walk(widget):
        try:
            cur = w.cget("bg")
        except Exception:
            continue
        if only is None or cur in only:
            try:
                w.configure(bg=new_bg)
            except Exception:
                pass


def bind_all(widget, seq, fn):
    for w in walk(widget):
        w.bind(seq, fn)


# ----------------------------------------------------------------- 数据读取
def _dict_body(text, key):
    """取出 ioreg 里某个嵌套字典的完整 {...} 内容（按大括号配对，支持嵌套）。
    ioreg 会把 AdapterDetails、BatteryData、ChargerData 打成一行，直接用正则找
    "Voltage" 会先命中充电器的 20V，必须限定在对应的字典里取。"""
    i = text.find('"%s" = {' % key)
    if i < 0:
        i = text.find('"%s"={' % key)
    if i < 0:
        return ""
    start = text.find("{", i)
    if start < 0:
        return ""
    depth = 0
    for k in range(start, len(text)):
        ch = text[k]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:k + 1]
    return ""


class Battery:
    def __init__(self):
        self.ok = False
        self.pct = self.cur = self.maxcap = self.design = 0
        self.health = 0
        self.ma = self.volt = self.temp = 0
        self.cycle = 0
        self.source = "?"
        self.charging = "No"
        self.adapter = "na"
        self.limit = None
        self.cells = []
        self.imbalance = 0
        # ---- 对标 coconutBattery / HWiNFO 的深度字段
        self.qmax = []          # 每节电芯自己学到的容量（mAh）
        self.soc = 0            # 电量计报的 StateOfCharge
        self.name = ""          # 电池芯片型号
        self.serial = ""        # 电池序列号
        self.vendor = ""        # 电芯厂商代码
        self.chg_v = 0          # 充电电压 mV
        self.chg_a = 0          # 充电电流 mA
        self.sys_power = 0      # 系统功耗 mW
        self.adapter_w = 0      # 充电器标称功率 W
        self.ncr = 0            # 不允许充电的原因码
        self.fail_status = 0    # PermanentFailureStatus

    @property
    def temp_c(self):
        return round(self.temp / 100.0, 1)

    @property
    def on_ac(self):
        return self.source == "电源"

    @property
    def cell_min(self):
        return min(self.cells) if self.cells else 0

    @property
    def cell_max(self):
        return max(self.cells) if self.cells else 0

    @property
    def qmax_avg(self):
        return int(sum(self.qmax) / len(self.qmax)) if self.qmax else 0

    @property
    def health_qmax(self):
        """电芯自己学到的容量换算出的健康度"""
        if self.design > 0 and self.qmax_avg > 0:
            return int(self.qmax_avg * 100 / self.design)
        return 0

    @property
    def watts(self):
        """真实功率（W）：充电看充电回路，放电看电池输出"""
        if self.charging == "Yes" and self.chg_v > 0 and self.chg_a > 0:
            return round(self.chg_v * self.chg_a / 1e6, 1)
        if not self.on_ac and self.ma < -30:
            return round(self.volt * abs(self.ma) / 1e6, 1)
        return 0.0

    @property
    def runtime_min(self):
        """预计续航（分钟）；充电时返回充满还需多久"""
        try:
            if self.charging == "Yes" and self.chg_a > 50:
                left = max(0, self.maxcap - self.cur)
                return int(left * 60 / self.chg_a)
            if not self.on_ac and self.ma < -80 and self.cur > 0:
                return int(self.cur * 60 / abs(self.ma))
        except Exception:
            pass
        return 0

    @classmethod
    def read(cls):
        b = cls()
        text = run_cmd(["/usr/sbin/ioreg", "-rn", "AppleSmartBattery", "-w0"])
        if not text:
            return b

        def grab(key, default=0):
            m = re.search(r'"%s"\s*=\s*(\d+)' % re.escape(key), text)
            return to_int(m.group(1), default) if m else default

        # 关键：Voltage / DesignCapacity / CycleCount 在嵌套字典里也有，
        # 尤其是 AdapterDetails 的 "Voltage"=20000（充电器电压），必须先切出电池字典
        body = _dict_body(text, "BatteryData")
        chg = _dict_body(text, "ChargerData")
        adp = _dict_body(text, "AdapterDetails")

        def g(body_text, key, default=0):
            m = re.search(r'"%s"\s*=\s*(\d+)' % re.escape(key), body_text or "")
            return to_int(m.group(1), default) if m else default

        b.cur = grab("AppleRawCurrentCapacity") or g(body, "CurrentCapacity")
        b.maxcap = grab("AppleRawMaxCapacity") or grab("MaxCapacity")
        b.design = g(body, "DesignCapacity") or grab("DesignCapacity")
        b.volt = g(body, "Voltage") or grab("Voltage")
        b.temp = grab("Temperature")
        b.cycle = g(body, "CycleCount") or grab("CycleCount")
        b.ma = grab("InstantAmperage") or g(body, "Amperage")

        m = re.search(r'"ExternalConnected"\s*=\s*(\w+)', text)
        b.source = "电源" if (m and m.group(1) == "Yes") else "电池"
        m = re.search(r'"IsCharging"\s*=\s*(\w+)', text)
        b.charging = m.group(1) if m else "No"
        m = re.search(r'"AdapterID"\s*=\s*(\d+)', text)
        b.adapter = m.group(1) if m else "na"

        if b.ma > 2 ** 63:
            b.ma -= 2 ** 64

        m = re.search(r'"CellVoltage"\s*=\s*\(([\d,\s]+)\)', body or text)
        if m:
            b.cells = [to_int(x.strip()) for x in m.group(1).split(",") if x.strip()]
            if len(b.cells) >= 2:
                b.imbalance = max(b.cells) - min(b.cells)

        # 电芯自己学到的容量：这是判断「真老化」还是「电量计失准」的关键
        m = re.search(r'"Qmax"\s*=\s*\(([\d,\s]+)\)', body or text)
        if m:
            b.qmax = [to_int(x.strip()) for x in m.group(1).split(",") if x.strip()]

        def grabn(key, default=0):
            mm = re.search(r'"%s"\s*=\s*(\d+)' % re.escape(key), text)
            return to_int(mm.group(1), default) if mm else default

        def grabs(key, default=""):
            mm = re.search(r'"%s"\s*=\s*"([^"]*)"' % re.escape(key), text)
            return mm.group(1) if mm else default

        b.soc = g(body, "StateOfCharge")
        b.chg_v = g(chg, "ChargingVoltage")
        b.chg_a = g(chg, "ChargingCurrent")
        b.ncr = g(chg, "NotChargingReason")
        b.sys_power = g(body, "SystemPower")
        b.adapter_w = g(adp, "Watts")
        b.adapter = str(g(adp, "AdapterID", to_int(b.adapter, 0) if b.adapter != "na" else 0)
                        or b.adapter)
        b.fail_status = grabn("PermanentFailureStatus")
        b.name = grabs("DeviceName")
        b.serial = grabs("Serial")
        b.vendor = grabs("Manufacturer")

        if b.maxcap > 0:
            b.pct = int(b.cur * 100 / b.maxcap)
        if b.design > 0 and b.maxcap > 0:
            b.health = int(b.maxcap * 100 / b.design)

        out = run_cmd(["/usr/bin/pmset", "-g", "therm"], 4)
        m = re.search(r"CPU_Speed_Limit\s*=\s*(\d+)", out)
        b.limit = to_int(m.group(1)) if m else None

        b.ok = True
        return b

    # ---- 用「人话」描述问题：返回 (等级, 标题, 说明, 建议列表)
    def explain(self):
        issues = []
        discharge = self.on_ac and self.ma < -300
        no_adapter = self.adapter == "0" and self.on_ac
        gap = 0
        if self.qmax_avg and self.maxcap:
            gap = int(abs(self.qmax_avg - self.maxcap) * 100 / max(1, self.qmax_avg))
        # 电芯自报容量和系统报的容量打架时，以「读数可能失准」优先，别急着说电池报废
        contradiction = gap >= 25 and self.health_qmax >= 75

        if discharge:
            issues.append(("red", "电源接上了，但电并不是它在供"))
        if no_adapter:
            issues.append(("red", "系统认不出这个充电器"))
        if contradiction:
            issues.append(("amber", "容量读数对不上：电芯说 %d%%，系统说 %d%%"
                           % (self.health_qmax, self.health)))
        elif self.health and self.health < 60:
            issues.append(("red", "电池容量只剩 %d%%，接近寿命终点" % self.health))
        elif self.health and self.health < 80:
            issues.append(("amber", "电池容量剩 %d%%，系统建议维修" % self.health))
        if self.imbalance > 100:
            issues.append(("amber", "三节电芯电压不齐，差 %d mV" % self.imbalance))
        if self.limit is not None and self.limit < 80:
            issues.append(("amber", "CPU 被限制在 %d%% 的速度" % self.limit))
        if not self.on_ac and self.pct < 20:
            issues.append(("red", "电量只剩 %d%%，随时可能关机" % self.pct))

        if not issues:
            return ("green", "一切正常",
                    "供电稳定，电池状态良好。你可以放心继续使用，"
                    "我会在后台每 5 秒看一眼，有变化再告诉你。",
                    [])

        level = "red" if any(i[0] == "red" for i in issues) else "amber"
        head = issues[0][1]
        if len(issues) > 1:
            rest = "；".join(t for _, t in issues[1:])
            desc = "另外还有 %d 项：%s。" % (len(issues) - 1, rest)
        elif contradiction:
            desc = ("电芯自己学到的容量是每节 %d mAh，系统却只认 %d mAh —— 同一个电池不可能"
                    "同时是这两个状态。先别急着买电池，按下面两步走。" % (self.qmax_avg, self.maxcap))
        else:
            desc = "这一项可以修好，不必紧张，按下面的建议先试一次。"

        steps = []
        if discharge or no_adapter:
            steps = ["换一个原装 85W MagSafe 2 充电器再试一次",
                     "换一个插座或换一条电源线，排除接触不良",
                     "都不行就检查机身充电口（DC-in 小板），这是 2015 款的常见故障"]
        if contradiction:
            steps.append("先做一次电池校准（「电池详情」页有向导），让电量计重新学一遍容量——免费")
            steps.append("校准后容量仍停在 %d mAh，再换电池；跳到 8000 mAh 以上就不用换" % self.maxcap)
        elif self.health and self.health < 80:
            steps.append("电池已老化，建议更换原装或正规品牌电池")
        if self.limit is not None and self.limit < 80:
            steps.append("CPU 降频多由供电不足引起，修好供电后会自行恢复")
        if not steps:
            steps = ["保持通风，别在被子、沙发等不易散热的地方使用",
                     "定期回到本页看看，有异常我会记下断电前的数据"]
        return (level, head, desc, steps)


# ----------------------------------------------------------------- 深度分析
def machine_model():
    """机型标识，如 MacBookPro11,4"""
    return (run_cmd(["/usr/sbin/sysctl", "-n", "hw.model"], 4) or "Mac").strip()


def csv_rows(limit=0):
    rows = []
    try:
        with open(CSV, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                rows.append(r)
    except Exception:
        return []
    return rows[-limit:] if limit else rows


def incident_list():
    """从 incidents.log 解析出 [(时间, 中断分钟)]"""
    out = []
    try:
        with open(INC, encoding="utf-8") as f:
            for line in f:
                m = re.match(r"=== 异常断电 (\S+ \S+)（中断 (\d+) 秒）", line.strip())
                if m:
                    out.append((m.group(1), int(to_int(m.group(2))) // 60))
    except Exception:
        pass
    return out


def drain_stats():
    """从历史采样里算出使用强度：放电电流、每小时掉电、插电放电样本、降频样本"""
    rows = csv_rows()
    st = {"samples": len(rows), "days": 0, "avg_ma": 0, "max_ma": 0,
          "drop_per_hour": 0.0, "ac_discharge": 0, "throttled": 0}
    if not rows:
        return st
    times, ma_list, drops = [], [], []
    prev = None
    for r in rows:
        try:
            ts = to_int(r.get("timestamp"))
            ma = to_int(r.get("mA"))
            pct = to_int(r.get("pct"))
            src = (r.get("source") or "").strip()
            lim = (r.get("cpu_limit") or "").strip()
            note = (r.get("note") or "")
        except Exception:
            continue
        if ts:
            times.append(ts)
        if "AC_BUT_DISCHARGING" in note:
            st["ac_discharge"] += 1
        if lim.isdigit() and to_int(lim) < 80:
            st["throttled"] += 1
        if src == "BAT" and ma < -50:
            ma_list.append(abs(ma))
        if prev and prev[1] == "BAT" and src == "BAT":
            dt = ts - prev[0]
            if 0 < dt <= 600 and prev[2] >= pct:
                drops.append((prev[2] - pct) * 3600.0 / dt)
        prev = (ts, src, pct)
    if times:
        st["days"] = round((max(times) - min(times)) / 86400.0, 2)
    if ma_list:
        # 用中位数而不是平均值：偶尔一次满载会把平均值带偏，中位数才代表「平时」
        ma_list.sort()
        st["avg_ma"] = ma_list[len(ma_list) // 2]
        st["max_ma"] = ma_list[-1]
        st["bat_samples"] = len(ma_list)
    if drops:
        st["drop_per_hour"] = round(sum(drops) / len(drops), 1)
    return st


def capacity_verdict(b):
    """把「设计容量 / 电芯学到的容量 / 系统报的容量」三个口径摆在一起判断。
    返回 (级别, 标题, 说明, 建议列表)"""
    if not b.ok or b.maxcap <= 0 or b.design <= 0:
        return ("info", "容量数据不足",
                "系统没有给出完整的容量信息，暂时无法判断是电芯衰减还是读数问题。", [])

    health_sys = b.health
    health_q = b.health_qmax
    gap = 0
    if b.qmax_avg:
        gap = int(abs(b.qmax_avg - b.maxcap) * 100 / max(1, b.qmax_avg))

    if b.qmax_avg and gap >= 25 and health_q >= 75:
        ratio = b.maxcap / float(b.design)
        detail = ("电芯自己学到的容量是每节 %d mAh（约出厂设计的 %d%%），"
                  "但系统报的满充容量只有 %d mAh（%d%%）。两个数差了 %d%%，"
                  "同一个电池不可能同时是这两个状态。" % (b.qmax_avg, health_q, b.maxcap, health_sys, gap))
        if 0.40 <= ratio <= 0.62:
            detail += ("\n而且 %d mAh 差不多正好是设计值的一半——这很像"
                       "「三组电芯里有一组的并联单元没在出力」的典型读数，"
                       "也可能是电量计把容量记错了。" % b.maxcap)
        else:
            detail += "\n这更像是电量计（电量计芯片的容量记忆）失准，而不是电芯真的老化了。"
        return ("amber",
                "电芯说还有 %d%%，系统却只认 %d%%" % (health_q, health_sys),
                detail,
                ["先花 0 元做一次校准（右上角「校准向导」），让电量计重新学一遍容量",
                 "校准后回本页看「系统认的容量」有没有跳上去——跳到 8000 mAh 以上就是读数问题，不用花钱",
                 "若校准两次仍是 %d mAh，再按硬件问题处理：查电芯组与电池管理板，最后才换整块电池" % b.maxcap])

    if health_sys < 80:
        return ("amber", "电池确实衰减了：容量剩 %d%%" % health_sys,
                "系统报的满充容量 %d mAh，出厂设计 %d mAh，属于正常老化范围之外的损耗。"
                % (b.maxcap, b.design),
                ["换一块原装或正规品牌电池是最直接的办法",
                 "换之前先看「循环次数」：%d 次，正常应该在 500 次以上才降到这个容量" % b.cycle])

    return ("green", "容量读数一致，没有矛盾",
            "系统报的容量 %d mAh 与电芯学到的 %s 基本吻合，健康度 %d%%。"
            % (b.maxcap, ("%d mAh" % b.qmax_avg) if b.qmax_avg else "（未提供）", health_sys),
            ["保持现在的使用习惯即可，没必要刻意做什么"])


FAULT_CODES = {
    "BD-01": ("接电源但电池在放电", "red"),
    "BD-02": ("充电器未被系统识别（AdapterID=0）", "red"),
    "BD-03": ("容量报值与电芯实测容量相差 25% 以上", "amber"),
    "BD-04": ("电芯之间电压偏差超过 50 mV", "amber"),
    "BD-05": ("CPU 被供电不足限制降频", "amber"),
    "BD-06": ("存在非正常断电记录", "red"),
    "BD-07": ("电池健康度低于 80%", "amber"),
    "BD-08": ("电池管理芯片报告永久性故障", "red"),
}


def fault_codes(b, stats=None):
    """返回本次体检命中的故障码列表 [(code, 说明, 级别)]"""
    hits = []
    if b.on_ac and b.ma < -300:
        hits.append(("BD-01", FAULT_CODES["BD-01"][0] + "（%d mA）" % b.ma, "red"))
    if b.adapter == "0":
        hits.append(("BD-02", FAULT_CODES["BD-02"][0], "red"))
    if b.qmax_avg and b.maxcap:
        if abs(b.qmax_avg - b.maxcap) * 100 / max(1, b.qmax_avg) >= 25:
            hits.append(("BD-03", FAULT_CODES["BD-03"][0] + "（%d vs %d mAh）"
                         % (b.maxcap, b.qmax_avg), "amber"))
    if b.imbalance > 50:
        hits.append(("BD-04", FAULT_CODES["BD-04"][0] + "（%d mV）" % b.imbalance, "amber"))
    if b.limit is not None and b.limit < 80:
        hits.append(("BD-05", FAULT_CODES["BD-05"][0] + "（限制在 %d%%）" % b.limit, "amber"))
    inc = incident_list()
    if inc:
        hits.append(("BD-06", FAULT_CODES["BD-06"][0] + "（%d 次，最近 %s）"
                     % (len(inc), inc[-1][0]), "red"))
    if b.health and b.health < 80:
        hits.append(("BD-07", FAULT_CODES["BD-07"][0] + "（%d%%）" % b.health, "amber"))
    if b.fail_status:
        hits.append(("BD-08", FAULT_CODES["BD-08"][0] + "（status=%d）" % b.fail_status, "red"))
    return hits


def workorder_text(b, stats=None):
    """生成一页纸维修单：给售后 / 维修店看的证据与判断"""
    stats = stats or drain_stats()
    inc = incident_list()
    hits = fault_codes(b, stats)
    lines = [
        "电池医生 · 硬件故障送修单",
        "生成时间：%s" % time.strftime("%Y-%m-%d %H:%M"),
        "=" * 46,
        "【送修原因】%s" % ("使用中反复自动关机 / 断电" if inc else "电池状态异常"),
        "",
        "【机器与电池】",
        "  机型：%s        系统：macOS %s"
        % (machine_model(), (run_cmd(["/usr/bin/sw_vers", "-productVersion"], 4) or "?").strip()),
        "  电池型号：%s    序列号：%s" % (b.name or "—", b.serial or "—"),
        "  电芯厂商：%s    循环次数：%d" % (b.vendor or "—", b.cycle),
        "  出厂设计容量：%d mAh" % b.design,
        "  系统报的满充容量：%d mAh（健康度 %d%%）" % (b.maxcap, b.health),
        "  电芯学到的容量 Qmax：%s mAh（换算健康度 %s）"
        % ("/".join(map(str, b.qmax)) or "未提供",
           ("%d%%" % b.health_qmax) if b.qmax_avg else "—"),
        "  电芯电压：%s mV（偏差 %d mV）"
        % ("/".join(map(str, b.cells)) or "—", b.imbalance),
        "  温度 %.1f ℃   当前电流 %+d mA   电压 %d mV" % (b.temp_c, b.ma, b.volt),
        "  充电器：%s（标称 %s W）"
        % (("ID %s" % b.adapter) if b.adapter != "0" else "未被识别",
           b.adapter_w or "—"),
        "",
        "【命中的故障码】",
    ]
    if hits:
        for code, desc, _lv in hits:
            lines.append("  %s  %s" % (code, desc))
    else:
        lines.append("  无")

    lines += ["", "【非正常断电记录】共 %d 次" % len(inc)]
    for ts, mins in inc[-4:]:
        lines.append("  · %s（中断约 %d 分钟）" % (ts, mins))
    if not inc:
        lines.append("  · 无")

    lines += [
        "",
        "【使用强度】",
        "  采样 %d 条，覆盖 %.1f 天" % (stats.get("samples", 0), stats.get("days", 0)),
        "  电池供电时平均放电电流 %d mA（峰值 %d mA）"
        % (stats.get("avg_ma", 0), stats.get("max_ma", 0)),
        "  插着电源却在放电的采样：%d 条" % stats.get("ac_discharge", 0),
    ]

    lines += ["", "【判断与建议的处理顺序（从便宜到贵）】"]
    order = []
    if any(h[0] in ("BD-01", "BD-02") for h in hits):
        order += ["换一个原装 85W MagSafe 2 电源适配器交叉验证（借用即可）",
                  "检查机身 DC-in 充电口小板是否有氧化、松动、虚焊"]
    if any(h[0] == "BD-03" for h in hits):
        order += ["先做电池校准（完全放电到自动关机 → 连续充 8 小时 → 静置 2 小时），再看容量是否回升"]
    if any(h[0] in ("BD-03", "BD-07") for h in hits):
        order += ["更换电池总成（原装或正规品牌），并要求保留旧件以便核验"]
    if any(h[0] == "BD-08" for h in hits):
        order += ["电池管理板报永久性故障，只能更换电池总成"]
    if not order:
        order = ["按常规检测流程检查供电与散热"]
    for i, s in enumerate(order, 1):
        lines.append("  %d. %s" % (i, s))

    lines += [
        "",
        "【给维修人员的说明】",
        "  · 断电发生在插着电源、正在充电的状态下（见上表最后采样），"
        "软件层无内核崩溃或过热记录，怀疑供电链路或电池管理板。",
        "  · 以上数据由本机持续采样得到，原始数据可要求机主提供 CSV。",
        "",
        "本单由「电池医生」自动生成，仅作现象记录与排查参考，不构成检测结论。",
    ]
    return "\n".join(lines)


def read_processes():
    """返回 (rows, error)。rows 元素为 (pid, cpu, mem, rss_kb, name, fullcmd)"""
    try:
        r = subprocess.run(["/bin/ps", "-Ao", "pid,pcpu,pmem,rss,comm", "-r"],
                           capture_output=True, text=True, timeout=10)
    except PermissionError:
        return None, "系统策略禁止读取进程列表（请从访达直接打开本应用）"
    except Exception as e:
        return None, "读取失败：%s" % e
    if r.returncode != 0 or not r.stdout.strip():
        return None, (r.stderr or "ps 无输出").strip()[:160]

    rows = []
    for line in r.stdout.splitlines()[1:]:
        parts = line.split(None, 4)
        if len(parts) < 5:
            continue
        pid, cpu, mem, rss, cmd = parts
        if to_int(pid) <= 0:
            continue
        m = re.search(r"/([^/]+)\.app/", cmd)
        if m:
            name = m.group(1)
        else:
            name = os.path.basename(cmd.split(" ")[0]) or cmd[:40]
        rows.append((to_int(pid), float(cpu), float(mem), to_int(rss), name, cmd))
    return rows, None


def read_instant_cpu(n=36):
    """用 top 的第二个采样点取瞬时 CPU 占用，返回 (rows, error)"""
    try:
        r = subprocess.run(["/usr/bin/top", "-l", "2", "-n", str(n), "-o", "cpu",
                            "-stats", "pid,cpu,mem,command", "-s", "1"],
                           capture_output=True, text=True, timeout=25)
    except Exception as e:
        return None, "读取失败：%s" % e
    if r.returncode != 0 or not r.stdout.strip():
        return None, (r.stderr or "top 无法运行").strip()[:140]

    blocks, cur = [], None
    for line in r.stdout.splitlines():
        if line.startswith("PID"):
            if cur:
                blocks.append(cur)
            cur = []
        elif cur is not None and line.strip():
            cur.append(line)
    if cur:
        blocks.append(cur)
    if not blocks:
        return None, "无法解析 top 输出"

    rows = []
    for line in blocks[-1]:
        parts = line.split(None, 3)
        if len(parts) < 4:
            continue
        pid, cpu, mem, cmd = parts
        if not pid.isdigit():
            continue
        m = re.search(r"/([^/]+)\.app/", cmd)
        name = m.group(1) if m else os.path.basename(cmd.split(" ")[0]) or cmd[:40]
        try:
            rows.append((int(pid), float(cpu), float(mem), 0, name, cmd))
        except ValueError:
            continue
    if not rows:
        return None, "top 没有返回进程数据"
    rows.sort(key=lambda x: -x[1])
    return rows, None


def _num(token):
    """top 的数值可能带 K/M/G 后缀或结尾加号"""
    t = token.strip().rstrip("+").replace(",", "")
    mult = 1.0
    if t and t[-1] in "KkMmGgTt":
        mult = {"k": 1e3, "m": 1e6, "g": 1e9, "t": 1e12}[t[-1].lower()]
        t = t[:-1]
    try:
        return float(t) * mult
    except ValueError:
        return 0.0


def parse_top_blocks(text):
    """把 top 输出切成若干采样块，每块是 [(pid, [数值列...])]"""
    blocks, cur = [], None
    for line in text.splitlines():
        if line.startswith("PID"):
            if cur:
                blocks.append(cur)
            cur = []
        elif cur is not None and line.strip():
            cur.append(line)
    if cur:
        blocks.append(cur)
    out = []
    for blk in blocks:
        items = []
        for line in blk:
            parts = line.split()
            if len(parts) >= 2 and parts[0].isdigit():
                items.append((int(parts[0]), [_num(x) for x in parts[1:]], line))
        if items:
            out.append(items)
    return out


def read_energy(n=36):
    """按 CPU 周期数排「谁最耗电」。cycles 是 CPU 实际执行周期，比 CPU 占比更接近真实能耗。
    返回 (rows, err, meta)"""
    try:
        r = subprocess.run(["/usr/bin/top", "-l", "2", "-n", str(n), "-o", "cycles",
                            "-stats", "pid,cycles,cpu,command", "-s", "1"],
                           capture_output=True, text=True, timeout=30)
    except Exception as e:
        return None, "读取失败：%s" % e, {}
    if r.returncode != 0 or not r.stdout.strip():
        return None, (r.stderr or "top 无法运行").strip()[:140], {}

    blocks = parse_top_blocks(r.stdout)
    if not blocks:
        return None, "这台系统不支持 CPU 周期统计", {}
    last = blocks[-1]
    prev = {p: v[0] for p, v, _ in blocks[-2]} if len(blocks) >= 2 else {}

    rows, total = [], 0.0
    for pid, vals, line in last:
        if len(vals) < 2:
            continue
        cyc, cpu = vals[0], vals[1]
        if prev.get(pid):
            d = cyc - prev[pid]
            if d > 0:
                cyc = d
        cmd = " ".join(line.split()[3:]) or line
        m = re.search(r"/([^/]+)\.app/", cmd)
        name = m.group(1) if m else (os.path.basename(cmd.split(" ")[0]) or cmd[:30])
        total += cyc
        rows.append((pid, cpu, cyc, 0, name[:40], cmd))
    if not rows:
        return None, "top 没有返回周期数据", {}
    rows.sort(key=lambda x: -x[2])
    return rows, None, {"total": total, "mode": "cycles"}


def du_kb(path):
    p = os.path.expanduser(path)
    if not os.path.exists(p):
        return -1
    out = run_cmd(["/usr/bin/du", "-skx", p], timeout=180)
    try:
        return to_int(out.split()[0], -1)
    except Exception:
        return -1


SCAN_FILE = os.path.join(BASE, ".scan.json")
SCAN_FRESH = 120        # 比这还新：连后台刷新都省了
SCAN_TTL = 6 * 3600     # 比这更旧：不拿缓存糊弄人，直接重扫


def human_ago(ts):
    if not ts:
        return "未知时间"
    d = max(0, int(time.time() - ts))
    if d < 60:
        return "刚刚"
    if d < 3600:
        return "%d 分钟前" % (d // 60)
    if d < 86400:
        return "%d 小时前" % (d // 3600)
    return "%d 天前" % (d // 86400)


def scan_all(workers=3):
    """并行统计各目录大小。du 是独立进程、各自遍历，SSD 上并行比串行快 2-3 倍。"""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    out, jobs = [], {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for name, path in STORAGE_TARGETS:
            jobs[ex.submit(du_kb, path)] = (name, path)
        for fut in as_completed(jobs):
            name, path = jobs[fut]
            try:
                kb = fut.result()
            except Exception:
                kb = -1
            if kb >= 0:
                out.append((name, os.path.expanduser(path), kb))
    out.sort(key=lambda x: -x[2])
    return out


def scan_cache_read():
    try:
        with open(SCAN_FILE, encoding="utf-8") as f:
            d = json.load(f)
        items = [(i["name"], i["path"], int(i["kb"])) for i in (d.get("items") or [])]
        if not items:
            return None
        return {"ts": int(d.get("ts") or 0), "items": items}
    except Exception:
        return None


def scan_cache_write(items):
    try:
        with open(SCAN_FILE, "w", encoding="utf-8") as f:
            json.dump({"ts": int(time.time()),
                       "items": [{"name": n, "path": p, "kb": int(k)}
                                 for n, p, k in items]}, f)
    except Exception:
        pass


def scan_cache_drop():
    try:
        os.remove(SCAN_FILE)
    except Exception:
        pass


# ----------------------------------------------------------------- 控件
class Card(tk.Frame):
    """白底卡片：1px 细边 + 内边距"""

    def __init__(self, master, pad=16, bg=None, line=None, **kw):
        self.c_bg = bg or P["card"]
        super().__init__(master, bg=self.c_bg, highlightthickness=1,
                         highlightbackground=line or P["line"],
                         highlightcolor=line or P["line"], bd=0, **kw)
        self.body = tk.Frame(self, bg=self.c_bg)
        self.body.pack(fill="both", expand=True, padx=pad, pady=pad)


class RButton(tk.Canvas):
    """圆角按钮，支持 primary / secondary / ghost / danger 四种样式"""

    STYLES = {
        "primary":   (P["accent"], P["accent2"], "#FFFFFF"),
        "secondary": ("#F2F2EC", "#E7E7DF", P["text"]),
        "ghost":     (P["card"], "#F4F4EF", P["text2"]),
        "danger":    (P["red_soft"], "#F5DCD8", P["red"]),
    }
    # 描边是「看起来像按钮」的关键：纯白底无边框在白卡片上等于隐形
    OUTLINES = {
        "primary":   P["accent2"],
        "secondary": "#DBDBD1",
        "ghost":     P["line"],
        "danger":    P["red_line"],
    }

    def __init__(self, master, text, command, kind="secondary", height=32,
                 size=12, padx=16, bg=None, width=None):
        self.parent_bg = bg or self._bg_of(master)
        self.fill, self.fill_hover, self.fg = self.STYLES.get(kind, self.STYLES["secondary"])
        self.text = text
        self.command = command
        self.kind = kind
        self.enabled = True
        self.size = size
        f = tkfont.Font(family=FONT, size=size,
                        weight="bold" if kind == "primary" else "normal")
        self.w = width or (f.measure(text) + padx * 2)
        super().__init__(master, width=self.w, height=height, bg=self.parent_bg,
                         highlightthickness=0, bd=0, cursor="pointinghand")
        self._draw()
        self.bind("<Button-1>", self._click)
        self.bind("<Enter>", lambda e: self._fill(self.fill_hover))
        self.bind("<Leave>", lambda e: self._fill(self.fill))
        self.bind("<ButtonRelease-1>", lambda e: self._fill(self.fill_hover))

    @staticmethod
    def _bg_of(master):
        try:
            return master.cget("bg")
        except Exception:
            return P["bg"]

    def _body(self, fill):
        h = to_int(self.cget("height"))
        self.delete("all")
        r = min(9, (h - 2) / 2.0)
        round_rect(self, 0, 1, self.w, h - 1, r, fill=fill,
                   outline=self.OUTLINES.get(self.kind, P["line"]),
                   width=1 if self.enabled else 0)
        self.create_text(self.w / 2, h / 2, text=self.text, fill=self.fg,
                         font=(FONT, self.size, "bold" if self.kind == "primary" else "normal"))

    def _draw(self):
        self._body(self.fill)

    def _fill(self, color):
        if not self.enabled:
            return
        self._body(color)

    def _click(self, _):
        if self.enabled and self.command:
            self.command()

    def set_text(self, text, width=None):
        self.text = text
        if width:
            self.w = width
            self.configure(width=width)
        self._draw()

    def set_enabled(self, on):
        self.enabled = on
        self.configure(cursor="pointinghand" if on else "arrow")
        self.fg = self.STYLES.get(self.kind)[2] if on else P["faint"]
        self._draw()


class Chip(tk.Frame):
    """小圆角标签，用于状态/计数"""

    def __init__(self, master, text="", fg=None, bg=None, dot=None, size=10):
        bg = bg or P["card2"]
        super().__init__(master, bg=bg, highlightthickness=0)
        self.cv = tk.Canvas(self, height=22, bg=bg, highlightthickness=0,
                            width=max(28, tkfont.Font(family=FONT, size=size).measure(text) + 28))
        self.cv.pack()
        self.size = size
        self.dot = dot
        self.text = text
        self.fg = fg or P["muted"]
        self.bg = bg
        self._draw()

    def _draw(self):
        c = self.cv
        c.delete("all")
        w = to_int(self.cv.cget("width"))
        round_rect(c, 0, 1, w, 21, 10, fill=self.bg, outline="")
        x = 10
        if self.dot:
            c.create_oval(x, 8, x + 6, 14, fill=self.dot, outline="")
            x += 11
        c.create_text(x, 11, text=self.text, anchor="w", fill=self.fg,
                      font=(FONT, self.size))

    def set(self, text, fg=None, bg=None, dot=None):
        self.text = text
        if fg:
            self.fg = fg
        if bg:
            self.bg = bg
            self.configure(bg=bg)
            self.cv.configure(bg=bg)
        if dot is not None:
            self.dot = dot
        self.cv.configure(width=max(28, tkfont.Font(family=FONT, size=self.size).measure(text) + 28))
        self._draw()


class NavItem(tk.Frame):
    def __init__(self, master, text, key, command):
        super().__init__(master, bg=P["sidebar"], height=38, cursor="pointinghand")
        self.pack_propagate(False)
        self.key = key
        self.command = command
        self.bar = tk.Frame(self, bg=P["sidebar"], width=3)
        self.bar.pack(side="left", fill="y")
        self.lbl = tk.Label(self, text=text, bg=P["sidebar"], fg=P["text2"],
                            font=(FONT, 12), anchor="w", padx=14)
        self.lbl.pack(side="left", fill="both", expand=True)
        for w in (self, self.lbl):
            w.bind("<Button-1>", lambda e: self.command(self.key))
            w.bind("<Enter>", self._enter)
            w.bind("<Leave>", self._leave)

    def _enter(self, _):
        if self.bar.cget("bg") == P["sidebar"]:
            self._paint(P["sb_hover"])

    def _leave(self, _):
        if self.bar.cget("bg") == P["sidebar"]:
            self._paint(P["sidebar"])

    def _paint(self, bg, fg=None):
        self.configure(bg=bg)
        self.lbl.configure(bg=bg)
        if fg:
            self.lbl.configure(fg=fg)
        self.bar.configure(bg=fg if fg else bg)

    def set_active(self, on):
        if on:
            self._paint(P["card"])
            self.lbl.configure(fg=P["accent"], font=(FONT, 12, "bold"))
            self.bar.configure(bg=P["accent"])
        else:
            self._paint(P["sidebar"])
            self.lbl.configure(fg=P["text2"], font=(FONT, 12))
            self.bar.configure(bg=P["sidebar"])


class MetricCard(Card):
    """指标卡片：标签 / 数值 / 一行说明"""

    def __init__(self, master, label, hint="", pad=14):
        super().__init__(master, pad=0)
        inner = tk.Frame(self, bg=P["card"])
        inner.pack(fill="both", expand=True, padx=pad, pady=pad - 2)
        self.name = tk.Label(inner, text=label, bg=P["card"], fg=P["muted"],
                             font=(FONT, 10), anchor="w")
        self.name.pack(anchor="w")
        self.val = tk.Label(inner, text="--", bg=P["card"], fg=P["text"],
                            font=(FONT, 16, "bold"), anchor="w")
        self.val.pack(anchor="w", pady=(1, 2))
        self.hint = tk.Label(inner, text=hint, bg=P["card"], fg=P["faint"],
                             font=(FONT, 9), anchor="w", justify="left",
                             wraplength=170)
        self.hint.pack(anchor="w", fill="x")
        # 说明文字跟着自身宽度换行，窄窗口下不会顶出去
        def _fit(e, lb=self.hint):
            want = max(90, e.width - 4)
            if abs(want - to_int(lb.cget("wraplength"))) >= 4:
                lb.configure(wraplength=want)
        self.hint.bind("<Configure>", _fit)

    def set(self, text, color=None, hint=None):
        self.val.configure(text=text, fg=color or P["text"])
        if hint is not None:
            self.hint.configure(text=hint)


class RowList(tk.Frame):
    """可滚动列表：行由 builder 创建，支持悬停、选中、双击、空状态"""

    def __init__(self, master, builder, key_of, on_select=None, on_activate=None,
                 bg=None, empty="暂无数据"):
        self.list_bg = bg or P["card"]
        super().__init__(master, bg=self.list_bg)
        self.builder = builder
        self.key_of = key_of
        self.on_select = on_select
        self.on_activate = on_activate
        self.empty = empty

        self.canvas = tk.Canvas(self, bg=self.list_bg, highlightthickness=0, bd=0)
        self.vs = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self._on_scroll)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=self.list_bg)
        self.win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", self._inner_cfg)
        self.canvas.bind("<Configure>", self._canvas_cfg)
        self.canvas.bind("<MouseWheel>", self._wheel)
        self.inner.bind("<MouseWheel>", self._wheel)

        self.items = []
        self.rows = {}
        self.sel = None
        self._empty_lbl = None

    # --- 滚动
    def _on_scroll(self, first, last):
        self.vs.set(first, last)
        if float(first) <= 0.001 and float(last) >= 0.999:
            self.vs.pack_forget()
        else:
            if not self.vs.winfo_ismapped():
                self.vs.pack(side="right", fill="y")

    def _inner_cfg(self, _):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _canvas_cfg(self, e):
        self.canvas.itemconfigure(self.win, width=e.width)

    def _wheel(self, e):
        if self.canvas.bbox("all") and \
                self.canvas.bbox("all")[3] > self.canvas.winfo_height():
            self.canvas.yview_scroll(-1 * int(e.delta), "units")

    # --- 数据
    def set_items(self, items):
        self.items = items
        for w in list(self.inner.winfo_children()):
            w.destroy()
        self.rows.clear()
        self._empty_lbl = None

        if not items:
            self._empty_lbl = tk.Label(self.inner, text=self.empty, bg=self.list_bg,
                                       fg=P["faint"], font=(FONT, 12), pady=30)
            self._empty_lbl.pack(fill="x")
            return

        keys = [self.key_of(i) for i in items]
        if self.sel not in keys:
            self.sel = None

        for i, item in enumerate(items):
            key = self.key_of(item)
            row = tk.Frame(self.inner, bg=self.list_bg)
            row.pack(fill="x")
            self.builder(row, item, i)
            self.rows[key] = row
            self._bind(row, key)
            if i < len(items) - 1:
                sep = tk.Frame(self.inner, bg=P["line2"], height=1)
                sep.pack(fill="x")
            if key == self.sel:
                self._mark(row, True)

    def _bind(self, row, key):
        def click(_):
            self.sel = key
            for k, r in self.rows.items():
                self._mark(r, k == key)
            if self.on_select:
                self.on_select(key)

        def enter(_):
            if self.sel != key:
                recolor(row, P["hover"], only=(self.list_bg, P["card"], P["card2"]))

        def leave(_):
            if self.sel != key:
                recolor(row, self.list_bg, only=(P["hover"],))

        for w in walk(row):
            w.bind("<Button-1>", click, add="+")
            w.bind("<Enter>", enter, add="+")
            w.bind("<Leave>", leave, add="+")
            if self.on_activate:
                w.bind("<Double-1>", lambda e, k=key: self.on_activate(k), add="+")
            try:
                w.configure(cursor="pointinghand")
            except Exception:
                pass

    def _mark(self, row, on):
        # 选中态只用底色区分，避免插入竖条导致行内元素抖动
        recolor(row, P["accent_soft"] if on else self.list_bg,
                only=(self.list_bg, P["hover"], P["accent_soft"]))

    def selected_key(self):
        return self.sel


class Ring(tk.Canvas):
    """电量圆环"""

    def __init__(self, master, size=176):
        super().__init__(master, width=size, height=size, bg=P["card"],
                         highlightthickness=0)
        self.size = size

    def draw(self, pct, health, level_color):
        c = self
        c.delete("all")
        s = self.size
        cx = cy = s / 2.0
        w = 13
        r = s / 2.0 - w / 2 - 8
        c.create_oval(cx - r, cy - r, cx + r, cy + r, outline=P["track"], width=w)
        ext = -359.99 * max(0, min(100, pct)) / 100.0
        if abs(ext) > 1:
            c.create_arc(cx - r, cy - r, cx + r, cy + r, start=90, extent=ext,
                         style="arc", outline=level_color, width=w)
            for ang in (90.0, 90.0 + ext):
                a = math.radians(ang)
                px, py = cx + r * math.cos(a), cy - r * math.sin(a)
                c.create_oval(px - w / 2.0, py - w / 2.0, px + w / 2.0, py + w / 2.0,
                              fill=level_color, outline="")
        c.create_text(cx, cy - 12, text="%d%%" % pct, fill=P["text"],
                      font=(FONT, 34, "bold"))
        c.create_text(cx, cy + 18, text="当前电量", fill=P["muted"], font=(FONT, 10))
        c.create_text(cx, cy + 38, text="健康 %d%%" % health, fill=level_color,
                      font=(FONT, 11, "bold"))


# ----------------------------------------------------------------- 网络诊断
AIRPORT = ("/System/Library/PrivateFrameworks/Apple80211.framework/"
           "Resources/airport")
NET_BACKUP = os.path.join(BACKUP, "net-last.json")
DNS_SUGGEST = ["223.5.5.5", "223.6.6.6"]
HTTP_TEST = "http://connect.rom.miui.com/generate_204"
HTTPS_TEST = "https://www.apple.com/library/test/success.html"

NET_CHECKS = [("wifi", "Wi-Fi 连接"), ("signal", "信号质量"), ("ip", "IP 地址"),
              ("gateway", "默认网关"), ("dns", "域名解析"),
              ("internet", "外网连通"), ("proxy", "系统代理"),
              ("hosts", "hosts 文件")]

NET_COLORS = {"ok": P["green"], "warn": P["amber"], "fail": P["red"],
              "skip": P["faint"], "run": P["faint"]}
NET_GLYPH = {"ok": "✓", "warn": "!", "fail": "×", "skip": "–", "run": ""}

PROXY_KINDS = (("webproxy", "HTTP"), ("securewebproxy", "HTTPS"),
               ("socksfirewallproxy", "SOCKS"))


def net_cmd(args, timeout=10):
    """执行命令，返回 stdout+stderr —— networksetup 的报错写在 stderr"""
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return ((r.stdout or "") + (r.stderr or "")).strip()
    except Exception as e:
        return "ERROR: %s" % e


def port_open(port, timeout=0.4):
    if not port:
        return False
    try:
        s = socket.create_connection(("127.0.0.1", int(port)), timeout)
        s.close()
        return True
    except Exception:
        return False


def port_owner(port):
    out = net_cmd(["/usr/sbin/lsof", "-nP", "-iTCP:%d" % int(port),
                   "-sTCP:LISTEN"], 4)
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2:
            return parts[0]
    return ""


def http_probe(url, proxy=None, timeout=7):
    """返回 (HTTP 状态码, 秒)。status=0 表示根本连不上"""
    args = ["/usr/bin/curl", "-s", "-o", "/dev/null",
            "-w", "%{http_code} %{time_total}", "--max-time", str(timeout)]
    if proxy:
        args += ["-x", proxy]
    args.append(url)
    out = net_cmd(args, timeout + 4)
    parts = out.split()
    if len(parts) == 2:
        try:
            return int(parts[0]), float(parts[1])
        except Exception:
            pass
    return 0, 0.0


def ping_avg(host, count=2):
    if not host:
        return None
    out = net_cmd(["/sbin/ping", "-c", str(count), "-t", "2", host], 8)
    m = re.search(r"=\s*[\d.]+/([\d.]+)/", out)
    return float(m.group(1)) if m else None


def dns_probe(name="www.apple.com"):
    """返回 (是否解析成功, 毫秒, 解析到的 IP)"""
    t0 = time.time()
    out = net_cmd(["/usr/bin/nslookup", name], 6)
    ms = int((time.time() - t0) * 1000)
    low = out.lower()
    if not out or "can't find" in low or "nxdomain" in low or "timed out" in low:
        return False, ms, ""
    addrs = re.findall(r"^Address:\s*([0-9a-fA-F.:]+)", out, re.M)
    real = addrs[1:] if len(addrs) > 1 else []
    return bool(real), ms, (real[-1] if real else "")


def hosts_suspicious():
    """找出 hosts 里被指向本机/黑洞的域名（排除 localhost 一类）"""
    bad = []
    whitelist = ("localhost", "localhost.localdomain", "ip6-localhost",
                 "ip6-loopback", "broadcasthost", "local")
    try:
        with open("/etc/hosts", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.split("#")[0].strip()
                if not line:
                    continue
                parts = line.split()
                if len(parts) < 2 or parts[0] not in ("127.0.0.1", "0.0.0.0", "::1"):
                    continue
                for host in parts[1:]:
                    if host.lower() not in whitelist:
                        bad.append(host)
    except Exception:
        pass
    return bad


def read_net_basic():
    """读一次网络基础状态（几秒内完成，不阻塞界面由调用方保证）"""
    d = {"dev": "", "service": "", "ip": "", "mask": "", "router": "",
         "dns": [], "dns_auto": True, "ssid": "", "rssi": None, "noise": None,
         "rate": None, "channel": "", "proxy_on": False, "proxy_list": [],
         "proxy_host": "", "proxy_port": 0}

    out = net_cmd(["/sbin/route", "-n", "get", "default"], 6)
    m = re.search(r"interface:\s*(\S+)", out)
    d["dev"] = m.group(1) if m else ""
    m = re.search(r"gateway:\s*(\S+)", out)
    d["router"] = m.group(1) if m else ""

    if d["dev"]:
        order = net_cmd(["/usr/sbin/networksetup", "-listnetworkserviceorder"], 8)
        cur = ""
        for line in order.splitlines():
            line = line.strip()
            mm = re.match(r"^\(\d+\)\s*(.+)$", line)
            if mm:
                cur = mm.group(1).strip()
            elif d["dev"] and ("Device: %s)" % d["dev"]) in line:
                d["service"] = cur
                break

    svc = d["service"] or "Wi-Fi"
    for line in net_cmd(["/usr/sbin/networksetup", "-getinfo", svc], 8).splitlines():
        if line.startswith("IP address:"):
            d["ip"] = line.split(":", 1)[1].strip()
        elif line.startswith("Subnet mask:"):
            d["mask"] = line.split(":", 1)[1].strip()
        elif line.startswith("Router:"):
            d["router"] = line.split(":", 1)[1].strip() or d["router"]

    for line in net_cmd(["/usr/sbin/networksetup", "-getdnsservers", svc], 8).splitlines():
        s = line.strip()
        if s and re.match(r"^[0-9a-fA-F:.]+$", s) and re.search(r"[0-9]", s):
            d["dns"].append(s)
    d["dns_auto"] = not d["dns"]

    if d["dev"]:
        out = net_cmd(["/usr/sbin/networksetup", "-getairportnetwork", d["dev"]], 6)
        m = re.search(r"Current Wi-Fi Network:\s*(.+)$", out, re.M)
        if m:
            d["ssid"] = m.group(1).strip()
        if os.path.exists(AIRPORT):
            for line in net_cmd([AIRPORT, "-I"], 6).splitlines():
                k, _, v = line.partition(":")
                k, v = k.strip(), v.strip()
                if k == "agrCtlRSSI":
                    d["rssi"] = to_int(v, 0)
                elif k == "agrCtlNoise":
                    d["noise"] = to_int(v, 0)
                elif k == "lastTxRate":
                    d["rate"] = to_int(v, 0)
                elif k == "channel":
                    d["channel"] = v

    for kind, label in PROXY_KINDS:
        out = net_cmd(["/usr/sbin/networksetup", "-get" + kind, svc], 6)
        en = re.search(r"Enabled:\s*(\w+)", out)
        if en and en.group(1) == "Yes":
            host = re.search(r"Server:\s*(\S*)", out)
            port = re.search(r"Port:\s*(\d+)", out)
            d["proxy_list"].append((label,
                                    host.group(1) if host else "",
                                    to_int(port.group(1), 0) if port else 0))
    d["proxy_on"] = bool(d["proxy_list"])
    if d["proxy_list"]:
        d["proxy_host"] = d["proxy_list"][0][1]
        d["proxy_port"] = d["proxy_list"][0][2]
    return d


def save_net_backup(d):
    """改动前把 DNS 与代理设置存一份，方便一键还原"""
    os.makedirs(BACKUP, exist_ok=True)
    data = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "service": d.get("service") or "Wi-Fi",
            "dns": list(d.get("dns", [])),
            "proxies": [{"label": k, "host": h, "port": p}
                        for k, h, p in d.get("proxy_list", [])]}
    try:
        with open(NET_BACKUP, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        return True
    except Exception:
        return False


def load_net_backup():
    try:
        with open(NET_BACKUP, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


class NetScan:
    """一次完整网络体检：逐项产出结果，调用方可边算边显示"""

    def __init__(self, on_check=None, on_done=None):
        self.on_check = on_check
        self.on_done = on_done
        self.info = {}
        self.checks = []
        self.gw_ms = None
        self.dns_ms = None
        self.net_ms = None
        self.proxy_ok = None

    def _emit(self, key, state, value, detail):
        item = {"key": key, "state": state, "value": value, "detail": detail}
        self.checks.append(item)
        if self.on_check:
            try:
                self.on_check(item)
            except Exception:
                pass

    def run(self):
        d = read_net_basic()
        self.info = d
        self._c_wifi(d)
        self._c_signal(d)
        self._c_ip(d)
        self._c_gateway(d)
        self._c_dns(d)
        self._c_internet(d)
        self._c_proxy(d)
        self._c_hosts(d)
        if self.on_done:
            self.on_done(self)

    # ---- 各项检查
    def _c_wifi(self, d):
        if d["ssid"]:
            ch = d["channel"].split(",")[0] if d["channel"] else ""
            band = "5 GHz" if to_int(ch, 0) >= 36 else ("2.4 GHz" if ch else "未知频段")
            self._emit("wifi", "ok", d["ssid"],
                       "%s · %s · 信道 %s" % (d["service"] or "Wi-Fi", band, ch or "?"))
        elif d["ip"]:
            self._emit("wifi", "ok", d["service"] or "已连接",
                       "通过 %s 连接（有线或共享网络）" % (d["dev"] or "接口"))
        else:
            self._emit("wifi", "fail", "未连接",
                       "没有可用的网络，请先连上 Wi-Fi 或插上网线")

    def _c_signal(self, d):
        if d["rssi"] is None:
            self._emit("signal", "skip", "不适用", "有线连接不需要评估无线信号")
            return
        rssi, noise = d["rssi"], d["noise"] or -90
        snr = rssi - noise
        rate = d["rate"] or 0
        if rssi >= -60:
            state, word = "ok", "很好"
        elif rssi >= -70:
            state, word = "ok", "良好"
        elif rssi >= -78:
            state, word = "warn", "偏弱"
        else:
            state, word = "fail", "很差"
        self._emit("signal", state, "%d dBm · %s" % (rssi, word),
                   "信噪比 %d dB，协商速率 %d Mbps%s"
                   % (snr, rate, "，离路由器近一点会更快" if state != "ok" else ""))

    def _c_ip(self, d):
        ip = d["ip"]
        if not ip:
            self._emit("ip", "fail", "未获取",
                       "没有拿到 IP 地址，通常是路由器 DHCP 没响应，或需要手动配置")
        elif ip.startswith("169.254."):
            self._emit("ip", "fail", ip,
                       "这是系统自动分配的临时地址，说明 DHCP 请求没有得到回应")
        elif ip.startswith("127."):
            self._emit("ip", "warn", ip, "地址异常（指向本机），请检查网络配置")
        else:
            self._emit("ip", "ok", ip, "子网掩码 %s · 网关 %s" % (d["mask"] or "?", d["router"] or "?"))

    def _c_gateway(self, d):
        if not d["router"]:
            self._emit("gateway", "warn", "未设置", "没有默认网关，可能无法访问外网")
            return
        ms = ping_avg(d["router"])
        self.gw_ms = ms
        if ms is None:
            self._emit("gateway", "fail", d["router"] + " 无响应",
                       "路由器不通。先看路由器电源/指示灯，再考虑重启 Wi-Fi")
        elif ms > 80:
            self._emit("gateway", "warn", "%.0f ms" % ms,
                       "网关 %s 响应偏慢，局域网可能被占用带宽" % d["router"])
        else:
            self._emit("gateway", "ok", "%.0f ms" % ms,
                       "网关 %s 响应正常" % d["router"])

    def _c_dns(self, d):
        okp, ms, addr = dns_probe()
        self.dns_ms = ms
        servers = d["dns"] or ["路由器默认"]
        label = "、".join(servers[:2])
        if not okp:
            self._emit("dns", "fail", "解析失败",
                       "DNS 服务器（%s）无法把域名翻译成 IP，网页会打不开，"
                       "但微信、QQ 这类直连 IP 的应用可能还是好的" % label)
        elif ms > 900:
            self._emit("dns", "warn", "%d ms" % ms,
                       "解析偏慢（%s），换一组公共 DNS 通常能明显改善" % label)
        else:
            self._emit("dns", "ok", "%d ms" % ms, "%s → %s" % (label, addr))

    def _c_internet(self, d):
        code, secs = http_probe(HTTP_TEST)
        self.net_ms = int(secs * 1000) if code else None
        if code in (200, 204):
            self._emit("internet", "ok", "%d ms" % int(secs * 1000),
                       "直连外网成功，网页可以正常打开")
            return
        code2, secs2 = http_probe(HTTPS_TEST)
        if code2 in (200, 204):
            self._emit("internet", "warn", "%d ms" % int(secs2 * 1000),
                       "直连测试不通，但访问 Apple 站点正常，可能是测试地址被网络策略拦截")
            return
        if d["proxy_on"] and port_open(d["proxy_port"]):
            pcode, psecs = http_probe(HTTPS_TEST,
                                      proxy="http://127.0.0.1:%d" % d["proxy_port"])
            self.proxy_ok = pcode in (200, 204)
            if self.proxy_ok:
                self._emit("internet", "warn", "仅代理可达",
                           "直连不通，走代理才通（%d ms）。如果浏览器能上网就属于正常"
                           % int(psecs * 1000))
                return
        self._emit("internet", "fail", "不通",
                   "外网连不上。依次看：网关是否通、DNS 是否正常、是否需要代理")

    def _c_proxy(self, d):
        if not d["proxy_on"]:
            self._emit("proxy", "ok", "未启用", "所有流量直连，没有代理干扰")
            return
        host, port = d["proxy_host"], d["proxy_port"]
        detail = "、".join("%s %s:%d" % (k, h, p) for k, h, p in d["proxy_list"])
        if not port or not port_open(port):
            self._emit("proxy", "fail", "%s:%d 无监听" % (host, port),
                       "系统把网页请求都转给这个端口，但没有任何程序在那里监听。"
                       "Wi-Fi 是好的，网页却一个都打不开——这是最常见的原因")
            return
        owner = port_owner(port)
        if self.proxy_ok is None:
            code, secs = http_probe(HTTPS_TEST, proxy="http://127.0.0.1:%d" % port)
            self.proxy_ok = code in (200, 204)
            self.proxy_ms = int(secs * 1000) if code else None
        if self.proxy_ok:
            self._emit("proxy", "ok", "%s:%d" % (host, port),
                       "%s 正在监听，代理转发正常%s"
                       % (owner or "本机程序",
                          "（%d ms）" % getattr(self, "proxy_ms", 0)
                          if getattr(self, "proxy_ms", None) else ""))
        else:
            self._emit("proxy", "warn", "%s:%d 转发失败" % (host, port),
                       "%s 在监听，但请求转发不出去。可以试着重启代理软件或换节点"
                       % (owner or "本机程序"))

    def _c_hosts(self, d):
        bad = hosts_suspicious()
        if bad:
            show = "、".join(bad[:3]) + ("…" if len(bad) > 3 else "")
            self._emit("hosts", "warn", "%d 条指向本机" % len(bad),
                       "%s —— 这些域名被固定到本机，永远不会访问真实服务器。"
                       "如果是你自己加的规则就没问题" % show)
        else:
            self._emit("hosts", "ok", "无异常", "没有把域名劫持到本机的条目")

    # ---- 结论
    def verdict(self):
        c = {x["key"]: x for x in self.checks}
        d = self.info
        proxy = c.get("proxy", {})
        ip = c.get("ip", {})
        gw = c.get("gateway", {})
        dns = c.get("dns", {})
        net = c.get("internet", {})
        sig = c.get("signal", {})
        hosts = c.get("hosts", {})

        if proxy.get("state") == "fail":
            return ("red", "系统代理指向了一个不存在的端口",
                    "Wi-Fi、IP、DNS 都是通的，问题出在代理：系统把网页请求转给 "
                    "%s:%d，但那个端口上没有任何程序在跑。多半是代理软件（Clash 之类）"
                    "关掉了，系统代理设置却还留着——于是每个网站都打不开。"
                    % (d["proxy_host"], d["proxy_port"]),
                    ["点「关闭系统代理」立刻恢复上网",
                     "或者重新打开你的代理软件，它一般会自动接管这个端口",
                     "想长期直连，在系统设置的「网络 → 代理」里关掉"])

        if ip.get("state") == "fail":
            return ("red", "这台 Mac 还没拿到 IP 地址",
                    "路由器没有把地址发给你，或者网线/Wi-Fi 认证没通过。"
                    "看起来像「连上了但不通」，其实就是没进入局域网。",
                    ["先点「续租 IP 地址」让它重新申请一次",
                     "不行就重启路由器，或忘记这个 Wi-Fi 后重连",
                     "公司网络可能需要先打开认证页面"])

        if gw.get("state") == "fail":
            return ("red", "连上了 Wi-Fi，但走不出路由器",
                    "网关 %s 完全无响应。你的电脑和路由器之间的这一段断了，"
                    "所以 DNS 和外网都跟着失败。" % (d["router"] or "未知"),
                    ["点「一键修复联网」，它会尝试重启 Wi-Fi 链路",
                     "看一眼路由器指示灯，或者直接重启路由器",
                     "换一个 Wi-Fi（比如手机热点）验证是不是路由器的问题"])

        if dns.get("state") == "fail":
            return ("red", "域名解析失败，所以网站都打不开",
                    "网络本身是通的，但 DNS 服务器没法把网址翻译成 IP。"
                    "典型表现：微信能用、浏览器什么都打不开。",
                    ["点「DNS 换为阿里」，改用 223.5.5.5 再试",
                     "顺手点一下「刷新 DNS 缓存」",
                     "如果换了还不行，可能是路由器把 DNS 劫持到了失效地址"])

        if net.get("state") == "fail":
            return ("red", "外网连不上",
                    "局域网这一段没查出明显问题，但访问公网失败。"
                    "可能是运营商故障、校园网/公司网需要认证，或者流量被防火墙拦了。",
                    ["换一个网站或手机热点交叉验证",
                     "如果必须要认证，先在浏览器里打开登录页",
                     "检查是否有 VPN / 防火墙软件接管了流量"])

        if net.get("state") == "warn":
            return ("amber", "能上网，但只有走代理才通",
                    "直连测试失败，通过代理可以正常访问。"
                    "如果你一直开着代理软件，这就是正常状态，不用管。",
                    ["不需要处理，浏览器走代理本来就正常",
                     "如果哪天代理软件关了，网页会全部打不开——到本页点一下就能看出来"])

        if sig.get("state") in ("warn", "fail"):
            return ("amber", "网络能用，但 Wi-Fi 信号偏弱",
                    "信号 %s，离路由器有点远。信号弱时速度慢、还容易掉线，"
                    "在电池供电时也会更费电。" % sig.get("value", ""),
                    ["尽量靠近路由器，或减少中间的墙体遮挡",
                     "优先连 5 GHz（近距离更快），远距离改连 2.4 GHz",
                     "如果一直很差，考虑加一个 Mesh 节点"])

        if hosts.get("state") == "warn":
            return ("amber", "网络正常，但 hosts 里有本机劫持条目",
                    "%s。这些域名被固定指向本机，不会访问真实服务器。"
                    "通常是你自己或某个开发工具加的。" % hosts.get("detail", ""),
                    ["如果这些域名你不需要访问，可以忽略",
                     "想恢复的话，编辑 /etc/hosts 把那几行删掉即可",
                     "本页不会自动改 hosts，避免误删你自己的规则"])

        gw_txt = "%.0f ms" % self.gw_ms if self.gw_ms else "—"
        return ("green", "网络状态良好",
                "已连接 %s，网关 %s、域名解析 %s、外网访问 %s。"
                "没有发现代理残留或 DNS 异常。"
                % (d["ssid"] or d["service"] or "网络", gw_txt,
                   ("%d ms" % self.dns_ms) if self.dns_ms is not None else "—",
                   (("%d ms" % self.net_ms) if self.net_ms else "正常")),
                [])


class NetRepairDialog(tk.Toplevel):
    """一键修复联网：逐项检查并处理，每一步都说清楚改了什么"""

    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.title("修复联网")
        self.configure(bg=P["card"])
        self.transient(app.root)
        self.resizable(False, False)
        self.info = {}
        self.fixed_proxy = False
        self.fixed_dns = False
        self.dry = bool(os.environ.get("BD_DRY"))
        self.counts = {"ok": 0, "warn": 0, "info": 0, "fail": 0}
        self.q = queue.Queue()
        self._alive = True

        head = tk.Frame(self, bg=P["card"])
        head.pack(fill="x", padx=24, pady=(20, 6))
        tk.Label(head, text="修复联网", bg=P["card"], fg=P["text"],
                 font=(FONT, 17, "bold")).pack(anchor="w")
        tk.Label(head, text="按「先查后改」的顺序处理：代理残留、DNS 失效、IP 租约、"
                            "Wi-Fi 链路。改之前会备份，随时能还原。",
                 bg=P["card"], fg=P["muted"], font=(FONT, 11), justify="left",
                 wraplength=600).pack(anchor="w", pady=(3, 0))

        self.prog = tk.Canvas(self, height=6, bg=P["card"], highlightthickness=0)
        self.prog.pack(fill="x", padx=24, pady=(14, 6))
        self.prog.bind("<Configure>", lambda e: self._draw_prog())
        self._ratio = 0.0

        body = tk.Frame(self, bg=P["card"])
        body.pack(fill="both", expand=True, padx=24, pady=(2, 0))
        self.steps = [
            ("备份当前网络配置", self._step_backup),
            ("检查系统代理", self._step_proxy),
            ("检查域名解析", self._step_dns),
            ("刷新 DNS 缓存", self._step_flush),
            ("检查 IP 地址租约", self._step_ip),
            ("重启 Wi-Fi 链路", self._step_wifi),
            ("复测网络连通性", self._step_retest),
            ("给出结论", self._step_verdict),
        ]
        self.rows = [StepRow(body, t) for t, _f in self.steps]

        self.verdict = tk.Frame(self, bg=P["green_soft"], highlightthickness=1,
                                highlightbackground=P["green_line"])
        self.verdict.pack(fill="x", padx=24, pady=(10, 0))
        self.verdict_lbl = tk.Label(self.verdict, text="正在处理，请稍候…",
                                    bg=P["green_soft"], fg=P["text2"],
                                    font=(FONT, 11), anchor="w", justify="left",
                                    wraplength=590)
        self.verdict_lbl.pack(fill="x", padx=14, pady=10)

        foot = tk.Frame(self, bg=P["card"])
        foot.pack(fill="x", padx=24, pady=(12, 18))
        RButton(foot, "关闭", self._close, "primary").pack(side="right")
        self.btn_undo = RButton(foot, "还原修复前", self._restore, "secondary")
        self.btn_undo.set_enabled(False)
        self.btn_undo.pack(side="right", padx=8)
        RButton(foot, "重新诊断", self._rediagnose, "ghost").pack(side="left")

        self.update_idletasks()
        w, h = 660, 640
        r = app.root
        self.geometry("%dx%d+%d+%d" % (
            w, h,
            r.winfo_rootx() + (r.winfo_width() - w) // 2,
            r.winfo_rooty() + max(20, (r.winfo_height() - h) // 3)))
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(180, self._start)
        self.after(80, self._poll)

    def _draw_prog(self):
        c = self.prog
        c.delete("all")
        w = c.winfo_width() or 580
        round_rect(c, 0, 0, w, 6, 3, fill=P["track"], outline="")
        if self._ratio > 0:
            round_rect(c, 0, 0, max(6, w * self._ratio), 6, 3,
                       fill=P["accent"], outline="")

    def _set_prog(self, ratio):
        self._ratio = max(0.0, min(1.0, ratio))
        self._draw_prog()

    def _start(self):
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        total = len(self.steps)
        for i, (_t, fn) in enumerate(self.steps):
            self.q.put(("start", i, None, None))
            try:
                state, detail = fn()
            except Exception as e:
                state, detail = "fail", "执行出错：%s" % e
            self.q.put(("row", i, state, detail))
            self.q.put(("prog", (i + 1) / float(total), None, None))
        self.q.put(("done", None, None, None))

    def _poll(self):
        if not self._alive:
            return
        try:
            while True:
                kind, i, state, detail = self.q.get_nowait()
                if kind == "start":
                    self.rows[i].set("run", "正在处理…")
                elif kind == "row":
                    self.rows[i].set(state, detail)
                    self.counts[state] = self.counts.get(state, 0) + 1
                elif kind == "prog":
                    self._set_prog(i)
                elif kind == "done":
                    self._finish()
        except queue.Empty:
            pass
        except Exception:
            pass
        if self._alive:
            try:
                self.after(80, self._poll)
            except Exception:
                pass

    # ---- 各步骤
    def _svc(self):
        return self.info.get("service") or "Wi-Fi"

    def _step_backup(self):
        self.info = read_net_basic()
        if self.dry:
            return "info", "演练模式：不写入备份与配置"
        if save_net_backup(self.info):
            return "ok", "已保存到 ~/Library/.batterydoctor-backup/net-last.json"
        return "warn", "备份写入失败，后续改动仍可手动还原"

    def _step_proxy(self):
        d = self.info or read_net_basic()
        if not d["proxy_on"]:
            return "ok", "系统没有启用代理，流量直连"
        host, port = d["proxy_host"], d["proxy_port"]
        if port and port_open(port):
            code, secs = http_probe(HTTPS_TEST, proxy="http://127.0.0.1:%d" % port)
            owner = port_owner(port) or "本机程序"
            if code in (200, 204):
                return "ok", "代理 %s:%d 正常（%s，%d ms）" % (
                    host, port, owner, int(secs * 1000))
            return "warn", "%s:%d 在监听但转发失败（HTTP %d），建议重启代理软件" % (
                host, port, code)
        if self.dry:
            return "ok", "演练：本应关闭指向 %s:%d 的失效代理" % (host, port)
        for kind, _label in PROXY_KINDS:
            net_cmd(["/usr/sbin/networksetup", "-set%sstate" % kind, self._svc(), "off"], 12)
        net_cmd(["/usr/sbin/networksetup", "-setautoproxystate", self._svc(), "off"], 12)
        self.fixed_proxy = True
        return "ok", "代理指向 %s:%d 但没程序在监听，已关闭系统代理，恢复直连" % (host, port)

    def _step_dns(self):
        d = self.info or read_net_basic()
        okp, ms, addr = dns_probe()
        if okp and ms <= 900:
            return "ok", "解析正常（%d ms，%s）" % (ms, addr)
        if self.dry:
            return "ok", "演练：本应把 DNS 改为 %s" % "、".join(DNS_SUGGEST)
        net_cmd(["/usr/sbin/networksetup", "-setdnsservers", self._svc()]
                + DNS_SUGGEST, 12)
        net_cmd(["/usr/bin/dscacheutil", "-flushcache"], 8)
        ok2, ms2, addr2 = dns_probe()
        self.fixed_dns = True
        if ok2:
            return "ok", "原来 %d ms 解析不出来，已改用 %s，现在 %d ms（%s）" % (
                ms, "、".join(DNS_SUGGEST), ms2, addr2)
        return "warn", "换了 DNS 仍然失败，问题可能在路由器或运营商一侧"

    def _step_flush(self):
        out = net_cmd(["/usr/bin/dscacheutil", "-flushcache"], 8)
        hup = net_cmd(["/usr/bin/killall", "-HUP", "mDNSResponder"], 6)
        if "not permitted" in hup or "No matching processes" in hup:
            return "ok", "解析缓存已清空（系统解析器需重启才彻底刷新，一般不必）"
        if "ERROR" in out:
            return "warn", "刷新缓存失败：%s" % out
        return "ok", "解析缓存已刷新"

    def _step_ip(self):
        d = self.info or read_net_basic()
        ip = d["ip"]
        if ip and not ip.startswith("169.254."):
            return "ok", "IP %s 有效，无需续租" % ip
        if self.dry:
            return "ok", "演练：本应让 %s 重新申请 DHCP" % (d["dev"] or "接口")
        dev = d["dev"] or "en0"
        out = net_cmd(["/usr/sbin/ipconfig", "set", dev, "DHCP"], 20)
        time.sleep(3)
        d2 = read_net_basic()
        if d2["ip"] and not d2["ip"].startswith("169.254."):
            self.info = d2
            return "ok", "已重新申请地址，新 IP 是 %s" % d2["ip"]
        return "fail", "续租失败（需要管理员）：终端执行 sudo ipconfig set %s DHCP" % dev

    def _step_wifi(self):
        d = self.info or read_net_basic()
        ms = ping_avg(d["router"])
        if ms is not None:
            return "ok", "网关可达（%.0f ms），不需要重启 Wi-Fi" % ms
        if not d["dev"].startswith("en") or d["ssid"] == "":
            return "warn", "网关不通，但当前不是 Wi-Fi 连接，没法用重启 Wi-Fi 修复"
        if self.dry:
            return "ok", "演练：本应关闭再打开 Wi-Fi"
        net_cmd(["/usr/sbin/networksetup", "-setairportpower", d["dev"], "off"], 12)
        time.sleep(2)
        net_cmd(["/usr/sbin/networksetup", "-setairportpower", d["dev"], "on"], 12)
        time.sleep(6)
        self.info = read_net_basic()
        ms2 = ping_avg(self.info["router"])
        if ms2 is not None:
            return "ok", "已重启 Wi-Fi，网关恢复（%.0f ms）" % ms2
        return "warn", "重启后网关仍无响应，问题更可能在路由器一侧"

    def _step_retest(self):
        code, secs = http_probe(HTTP_TEST)
        if code in (200, 204):
            return "ok", "网页访问正常（%d ms）" % int(secs * 1000)
        code2, secs2 = http_probe(HTTPS_TEST)
        if code2 in (200, 204):
            return "ok", "网页访问正常（%d ms）" % int(secs2 * 1000)
        okp, ms, _addr = dns_probe()
        if okp:
            return "warn", "DNS 已经能解析，但网页访问仍失败，可能是防火墙或代理规则"
        return "fail", "仍然不通，建议换个网络（手机热点）交叉验证"

    def _step_verdict(self):
        fixed = []
        if self.fixed_proxy:
            fixed.append("清掉了失效的系统代理")
        if self.fixed_dns:
            fixed.append("换了可用的 DNS")
        okc = self.counts.get("ok", 0)
        warnc = self.counts.get("warn", 0)
        failc = self.counts.get("fail", 0)
        if fixed:
            text = "已修复：%s。上面各项是修复后的复测结果。" % "、".join(fixed)
            if warnc or failc:
                text += "仍有 %d 项需要留意，可点「重新诊断」再看一次。" % (warnc + failc)
        elif failc:
            text = "有 %d 项没能自动修好，通常是路由器或运营商侧的硬件问题。" % failc
        elif warnc:
            text = "能连上网，但有 %d 项需要留意，具体见上面每一行的说明。" % warnc
        else:
            text = "网络各项检查都正常，不需要修复。"
        self.verdict_lbl.configure(text=text)
        if fixed:
            self.btn_undo.set_enabled(True)
        return "ok", "结论已生成"

    def _restore(self):
        cfg = load_net_backup()
        if not cfg:
            messagebox.showinfo("没有备份", "没有找到修复前的备份，无法还原。")
            return
        svc = cfg.get("service") or "Wi-Fi"
        dns = cfg.get("dns") or []
        if dns:
            net_cmd(["/usr/sbin/networksetup", "-setdnsservers", svc] + dns, 12)
        else:
            net_cmd(["/usr/sbin/networksetup", "-setdnsservers", svc, "Empty"], 12)
        for p in cfg.get("proxies") or []:
            kind = dict((v, k) for k, v in PROXY_KINDS).get(p.get("label"))
            if not kind:
                continue
            net_cmd(["/usr/sbin/networksetup", "-set" + kind, svc,
                     p.get("host", ""), str(p.get("port", 0))], 12)
            net_cmd(["/usr/sbin/networksetup", "-set%sstate" % kind, svc, "on"], 12)
        net_cmd(["/usr/bin/dscacheutil", "-flushcache"], 8)
        self.verdict_lbl.configure(
            text="已还原到修复前的设置（DNS 与代理）。Wi-Fi 开关状态不会还原。")
        self.app.add_event("网络设置已还原到修复前。", "info")
        if hasattr(self.app, "start_net_scan"):
            self.app.start_net_scan()

    def _rediagnose(self):
        self.app.start_net_scan()
        self._close()

    def _finish(self):
        self._set_prog(1.0)

    def _close(self):
        self._alive = False
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()
        if hasattr(self.app, "start_net_scan"):
            try:
                self.app.start_net_scan()
            except Exception:
                pass


# ----------------------------------------------------------------- 通知 / 导出 / 保养 / 清理
CARE_FILE = os.path.join(BASE, ".care.json")
DAILY_FILE = os.path.join(BASE, ".daily.json")
DAILY_PLIST = os.path.expanduser(
    "~/Library/LaunchAgents/com.local.batterydoctor.daily.plist")
LOGIN_PLIST = os.path.expanduser(
    "~/Library/LaunchAgents/com.local.batterydoctor.login.plist")

# 存储页给出的可清理候选（只报告，不删除）
CLEANUP_ADVICE = [
    ("可再生缓存", "~/Library/Caches",
     "关闭相关应用后整个目录都可以删除，重新打开会自动重建"),
    ("废纸篓", "~/.Trash",
     "清空废纸篓立即释放，删除前快速过一眼有没有误删的东西"),
    ("iOS 设备备份", "~/Library/Application Support/MobileSync/Backup",
     "旧 iPhone 的整机备份，一台动辄几十 GB，不用旧机可直接删"),
    ("Docker 数据", "~/Library/Containers/com.docker.docker",
     "在终端执行 docker system prune 清理镜像，别直接删文件"),
    ("系统日志", "~/Library/Logs",
     "保留最近一个月即可，旧日志可删"),
]


CHARGE_FILE = os.path.join(BASE, ".charge.json")


def _find_bclm():
    """找 bclm（Intel 机型靠写 SMC 的 BCLM 键限制充电上限）"""
    for p in ("/usr/local/bin/bclm", "/opt/homebrew/bin/bclm", "/usr/bin/bclm"):
        if os.path.exists(p):
            return p
    return None


def bclm_read():
    """读当前充电上限；没装工具返回 None"""
    exe = _find_bclm()
    if not exe:
        return None
    try:
        r = subprocess.run([exe, "read"], capture_output=True, text=True, timeout=10)
        m = re.search(r"(\d{2,3})", (r.stdout or "") + " " + (r.stderr or ""))
        if m:
            v = int(m.group(1))
            if 20 <= v <= 100:
                return v
    except Exception:
        pass
    return None


def bclm_write(pct):
    """写充电上限。要 root，用系统密码框提权；用户取消时返回明确原因。"""
    exe = _find_bclm()
    if not exe:
        return False, "还没安装限充工具"
    cmd = "%s %d" % (exe, int(pct))
    try:
        r = subprocess.run(["/usr/bin/osascript", "-e",
                            'do shell script "%s" with administrator privileges' % cmd],
                           capture_output=True, text=True, timeout=180)
    except Exception as e:
        return False, str(e)
    if r.returncode == 0:
        return True, ""
    msg = (r.stderr or "").strip()
    if "-128" in msg or "User canceled" in msg:
        return False, "已取消（没有输入密码）"
    return False, msg.replace("\n", " ")[:120] or "执行失败"


def charge_stats():
    """从 power.csv 统计最近 14 天的充电习惯，给出 0-100 的评分"""
    out = {"ready": False, "samples": 0, "days": 0, "ac_ratio": 0.0,
           "full_ac_ratio": 0.0, "hot_min": 0, "deep_times": 0,
           "chg_min": 0, "avg_chg_w": 0.0, "score": 0, "advice": []}
    rows = []
    try:
        with open(CSV, encoding="utf-8", errors="replace") as f:
            for r in csv.DictReader(f):
                rows.append(r)
    except Exception:
        return out
    if not rows:
        return out
    cut = time.time() - 14 * 86400
    rows = [r for r in rows if to_int(r.get("timestamp"), 0) >= cut]
    n = len(rows)
    if n < 30:
        return out
    ac = full_ac = hot = chg = deep = 0
    watts = []
    prev_deep = False
    for r in rows:
        pct = to_int(r.get("pct"), 0)
        try:
            temp = float(r.get("temp_C") or 0)
        except Exception:
            temp = 0.0
        on_ac = (r.get("source") == "AC")
        charging = (r.get("charging") == "Yes")
        if on_ac:
            ac += 1
            if pct >= 95:
                full_ac += 1
        if charging:
            chg += 1
            if temp >= 40:
                hot += 1
            try:
                w = abs(float(r.get("mA") or 0)) * float(r.get("mV") or 0) / 1e6
                if 0.5 < w < 100:
                    watts.append(w)
            except Exception:
                pass
        is_deep = pct <= 10
        if is_deep and not prev_deep:
            deep += 1
        prev_deep = is_deep

    span = 0
    try:
        span = (to_int(rows[-1].get("timestamp")) - to_int(rows[0].get("timestamp"))) / 86400.0
    except Exception:
        pass
    out.update({
        "ready": True, "samples": n, "days": round(span, 1),
        "ac_ratio": ac * 1.0 / n, "full_ac_ratio": full_ac * 1.0 / n,
        "hot_min": int(hot * 5 / 60), "chg_min": int(chg * 5 / 60),
        "deep_times": deep,
        "avg_chg_w": round(sum(watts) / len(watts), 1) if watts else 0.0,
    })

    score = 100
    adv = []
    if out["full_ac_ratio"] >= 0.5:
        score -= 28
        adv.append("大部分时间都停在满电插着电，这是容量掉得最快的一种用法。")
    elif out["full_ac_ratio"] >= 0.25:
        score -= 14
        adv.append("有相当长时间是满电插着电，能设个 80% 上限会好很多。")
    elif out["full_ac_ratio"] >= 0.1:
        score -= 6
    if out["hot_min"] >= 30:
        score -= 22
        adv.append("有 %d 分钟是在 40℃ 以上充电，高温加充电对电芯最伤。"
                   % out["hot_min"])
    elif out["hot_min"] >= 10:
        score -= 10
        adv.append("有 %d 分钟高温充电，尽量别边充边跑重负载。" % out["hot_min"])
    elif out["hot_min"] >= 3:
        score -= 4
    if out["deep_times"] >= 3:
        score -= 10
        adv.append("近两周有 %d 次把电用到 10%% 以下，深度放电会加速老化。"
                   % out["deep_times"])
    elif out["deep_times"] >= 1:
        score -= 4
    out["score"] = max(0, min(100, score))
    out["advice"] = adv
    return out


def notify(title, msg):
    """发一条 macOS 系统通知"""
    try:
        t = title.replace('"', "'").replace("\\", "")
        m = msg.replace('"', "'").replace("\\", "")
        subprocess.run(["/usr/bin/osascript", "-e",
                        'display notification "%s" with title "%s" sound name "Ping"'
                        % (m, t)], capture_output=True, timeout=8)
        return True
    except Exception:
        return False


def _bin(name):
    for d in ("/usr/sbin", "/usr/bin", "/sbin", "/bin"):
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    return name


# ----------------------------------------------------------------- 检查更新
# 全程序只有两个地方会发网络请求：网络诊断（你点才发）、检查更新（你点才发，
# 或者你自己在弹窗里勾了「每周自动看一眼」）。除此之外一个连接都不会建。
UPDATE_URL = "https://v5pc.com/battery/version.json"
UPDATE_CFG = os.path.join(BASE, ".update.json")
UPDATE_AUTO_DAYS = 7


def ver_tuple(s):
    """把 "3.6" / "v3.6.1" 变成可比较的元组"""
    out = []
    for part in re.split(r"[.\-+]", str(s).strip().lstrip("vV")):
        out.append(to_int(part, 0))
    while len(out) < 3:
        out.append(0)
    return tuple(out[:3])


def update_cfg_read():
    try:
        with open(UPDATE_CFG, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def update_cfg_write(**kw):
    d = update_cfg_read()
    d.update(kw)
    try:
        os.makedirs(BASE, exist_ok=True)
        with open(UPDATE_CFG, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
    except Exception:
        pass
    return d


def update_check(timeout=8):
    """问一次版本清单，返回 {ok, info} 或 {ok:False, err}"""
    try:
        req = urllib.request.Request(UPDATE_URL, headers={
            "User-Agent": "BatteryDoctor/%s" % VERSION,
            "Cache-Control": "no-cache"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        if not isinstance(data, dict) or not data.get("version"):
            return {"ok": False, "err": "服务器返回的格式看不懂"}
        data["current"] = VERSION
        data["newer"] = ver_tuple(data["version"]) > ver_tuple(VERSION)
        update_cfg_write(last_check=int(time.time()))
        return {"ok": True, "info": data}
    except Exception as e:
        return {"ok": False, "err": "%s" % e}


def update_download(url, out_path, progress=None, timeout=60):
    """把 dmg 下到本地，边下边报进度（0~1）"""
    req = urllib.request.Request(url, headers={
        "User-Agent": "BatteryDoctor/%s" % VERSION})
    with urllib.request.urlopen(req, timeout=timeout) as r, \
            open(out_path, "wb") as f:
        total = to_int(r.headers.get("Content-Length"), 0)
        got = 0
        while True:
            chunk = r.read(262144)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            if progress and total:
                progress(min(1.0, got / float(total)))
    return out_path


def text_to_pdf(text, out_path):
    """纯文本 → PDF（cupsfilter，已验证可嵌入 PingFang 中文字体）"""
    import tempfile
    fd, tmp = tempfile.mkstemp(suffix=".txt")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    try:
        r = subprocess.run([_bin("cupsfilter"), "-m", "application/pdf", tmp],
                           capture_output=True, timeout=60)
    finally:
        try:
            os.unlink(tmp)
        except Exception:
            pass
    if r.returncode != 0 or not r.stdout:
        raise RuntimeError("cupsfilter 转换失败 (rc=%d)" % r.returncode)
    with open(out_path, "wb") as f:
        f.write(r.stdout)
    return out_path


def canvas_to_png(canvas, out_path):
    """Tk 画布 → PNG。注意：PostScript 会丢中文，调用方需用 ASCII 标签绘制"""
    import tempfile
    ps = canvas.postscript()
    fd, tmp = tempfile.mkstemp(suffix=".ps")
    with os.fdopen(fd, "w") as f:
        f.write(ps)
    pdf_tmp = tmp + ".pdf"
    try:
        r = subprocess.run([_bin("pstopdf"), tmp, "-o", pdf_tmp],
                           capture_output=True, timeout=30)
        if r.returncode != 0:
            raise RuntimeError("pstopdf 失败")
        r = subprocess.run([_bin("sips"), "-s", "format", "png", pdf_tmp,
                            "--out", out_path], capture_output=True, timeout=30)
        if r.returncode != 0:
            raise RuntimeError("sips 转换失败")
    finally:
        for p in (tmp, pdf_tmp):
            try:
                os.unlink(p)
            except Exception:
                pass
    return out_path


def _care_state():
    try:
        with open(CARE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _care_save(d):
    try:
        with open(CARE_FILE, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
    except Exception:
        pass


def daily_checkup():
    """无头模式：每天定时体检，有问题才发系统通知，结果写 .daily.json"""
    issues = []
    b = Battery.read()
    if not b.ok:
        issues.append("读不到电池信息，接口可能被系统限制")
    else:
        if b.on_ac and b.ma < -300:
            issues.append("插着电源却在放电（%d mA）" % b.ma)
        if b.adapter == "0":
            issues.append("充电器无法被系统识别")
        if b.health and b.health < 80:
            issues.append("电池健康度只剩 %d%%" % b.health)
        if b.qmax_avg and b.maxcap and b.health_qmax >= 75:
            if abs(b.qmax_avg - b.maxcap) * 100 / max(1, b.qmax_avg) >= 25:
                issues.append("容量读数矛盾：系统 %d mAh，电芯实测 %d mAh（建议做一次校准）"
                              % (b.maxcap, b.qmax_avg))
        if b.imbalance > 150:
            issues.append("电芯电压失衡 %d mV" % b.imbalance)
        if b.limit is not None and b.limit < 80:
            issues.append("CPU 被限速到 %d%%" % b.limit)
    try:
        st = os.statvfs("/")
        free_kb = st.f_bavail * st.f_frsize // 1024
        total_kb = st.f_blocks * st.f_frsize // 1024
        if total_kb and 100.0 * free_kb / total_kb < 15:
            issues.append("磁盘可用空间不足 15%%（剩 %s）" % human(free_kb))
    except Exception:
        pass
    inc_n = 0
    if os.path.exists(INC):
        try:
            inc_n = open(INC, encoding="utf-8").read().count("=== 异常断电")
        except Exception:
            pass
    prev = {}
    try:
        with open(DAILY_FILE, encoding="utf-8") as f:
            prev = json.load(f)
    except Exception:
        pass
    new_inc = inc_n - prev.get("incidents", 0)
    if new_inc > 0:
        issues.append("新增 %d 次异常断电记录（详情见 incidents.log）" % new_inc)
    try:
        with open(DAILY_FILE, "w", encoding="utf-8") as f:
            json.dump({"ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                       "incidents": inc_n, "issues": issues},
                      f, ensure_ascii=False)
    except Exception:
        pass
    try:
        with open(APPLOG, "a", encoding="utf-8") as f:
            f.write("%s 每日体检：%s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"),
                                          "；".join(issues) or "一切正常"))
    except Exception:
        pass
    if issues:
        notify("电池医生 · 每日体检发现 %d 个问题" % len(issues),
               "；".join(issues[:3]) + ("…等" if len(issues) > 3 else ""))


def install_daily_agent():
    """写 LaunchAgent plist 并注册到 launchd，返回错误信息或 None"""
    py = sys.executable or "python3"
    src_path = os.path.abspath(__file__)
    plist = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.local.batterydoctor.daily</string>
    <key>ProgramArguments</key>
    <array>
        <string>%s</string>
        <string>%s</string>
        <string>--daily</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key><integer>9</integer>
        <key>Minute</key><integer>0</integer>
    </dict>
    <key>StandardOutPath</key><string>%s</string>
    <key>StandardErrorPath</key><string>%s</string>
</dict>
</plist>
""" % (py, src_path, os.path.join(BASE, "daily.out.log"), os.path.join(BASE, "daily.err.log"))
    os.makedirs(os.path.dirname(DAILY_PLIST), exist_ok=True)
    with open(DAILY_PLIST, "w", encoding="utf-8") as f:
        f.write(plist)
    subprocess.run(["/bin/launchctl", "unload", DAILY_PLIST],
                   capture_output=True, timeout=10)
    r = subprocess.run(["/bin/launchctl", "load", DAILY_PLIST],
                       capture_output=True, timeout=10)
    if r.returncode != 0:
        return "launchctl load 失败：%s" % r.stderr.decode(errors="ignore")[:200]
    return None

def _xml_esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def login_plist(py, script):
    """登录自启的 LaunchAgent 内容。
    注意：写进 ~/Library/LaunchAgents 后系统在下次登录时自动加载，
    这里不调 launchctl load —— 否则会立刻再开一个实例。"""
    return """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.local.batterydoctor.login</string>
    <key>ProgramArguments</key>
    <array>
        <string>%s</string>
        <string>%s</string>
        <string>--autostart</string>
    </array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><false/>
    <key>ProcessType</key><string>Interactive</string>
    <key>LimitLoadToSessionType</key><string>Aqua</string>
</dict>
</plist>
""" % (_xml_esc(py), _xml_esc(script))


def login_agent_on():
    return os.path.exists(LOGIN_PLIST)


def install_login_agent():
    """返回错误信息或 None"""
    py = sys.executable or "/usr/bin/python3"
    script = os.path.abspath(__file__)
    try:
        os.makedirs(os.path.dirname(LOGIN_PLIST), exist_ok=True)
        tmp = LOGIN_PLIST + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(login_plist(py, script))
        r = subprocess.run(["/usr/bin/plutil", "-lint", tmp],
                           capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            os.remove(tmp)
            return "生成的配置文件不合法：%s" % (r.stdout or r.stderr)[:160]
        os.replace(tmp, LOGIN_PLIST)
        return None
    except Exception as e:
        return str(e)


def uninstall_login_agent():
    try:
        subprocess.run(["/bin/launchctl", "unload", LOGIN_PLIST],
                       capture_output=True, timeout=10)
    except Exception:
        pass
    try:
        if os.path.exists(LOGIN_PLIST):
            os.remove(LOGIN_PLIST)
        return None
    except Exception as e:
        return str(e)


# ----------------------------------------------------------------- 磁盘清理
TRASH_DIR = os.path.expanduser("~/.Trash")

# 清理项定义
#   mode = "purge"  直接删除：可再生的数据，系统/应用会自动重建
#   mode = "trash"  移到废纸篓：可恢复，但要清空废纸篓才真正腾出空间
#   days / exts     可选筛选：只处理 N 天前的文件 / 只处理这些扩展名
#   risk            safe 安全 · care 需确认 · danger 含个人数据
CLEAN_ITEMS = [
    {"key": "caches", "name": "用户缓存", "mode": "purge", "risk": "safe",
     "paths": ["~/Library/Caches"], "default": True,
     "desc": "各应用的临时数据，重开应用会自动重建。极少数应用可能需要重新登录。"},
    {"key": "logs", "name": "系统日志", "mode": "purge", "risk": "safe",
     "paths": ["~/Library/Logs"], "days": 30, "default": True,
     "desc": "只删 30 天前的记录，最近的留着，出问题时还能查。"},
    {"key": "crashes", "name": "崩溃与诊断报告", "mode": "purge", "risk": "safe",
     "paths": ["~/Library/Logs/DiagnosticReports",
               "~/Library/Application Support/CrashReporter"],
     "days": 7, "default": True,
     "desc": "应用崩溃时留下的报告，超过一周的基本没有参考价值。"},
    {"key": "xcode_dd", "name": "Xcode 编译缓存", "mode": "purge", "risk": "safe",
     "paths": ["~/Library/Developer/Xcode/DerivedData"], "default": True,
     "desc": "编译中间产物，删掉后第一次编译会慢一些，之后照常。"},
    {"key": "mail_att", "name": "邮件附件副本", "mode": "purge", "risk": "safe",
     "paths": ["~/Library/Containers/com.apple.mail/Data/Library/Mail Downloads"],
     "default": True,
     "desc": "打开邮件时落地的附件副本，原件仍在邮件服务器上。"},
    {"key": "chrome_clone", "name": "Chrome 临时签名副本", "mode": "purge",
     "risk": "safe",
     "globs": ["/var/folders/*/*/T/com.google.Chrome.code_sign_clone",
               "/var/folders/*/*/X/com.google.Chrome.code_sign_clone"],
     "default": True,
     "desc": "Chrome 每次启动都会在系统临时目录里留一份自己的完整副本，每份 1.3G，"
             "攒几份就能吃掉 9G。退出 Chrome 再清最干净——浏览器开着时删掉也占着空间。"
             "删了不影响 Chrome，只是下次启动会重建。"},
    {"key": "trash", "name": "废纸篓", "mode": "purge", "risk": "care",
     "paths": ["~/.Trash"], "default": False,
     "desc": "清空后无法恢复。动手前建议在访达里过一眼，确认没有误删的东西。"},
    {"key": "dl_installers", "name": "下载里的旧安装包", "mode": "trash",
     "risk": "care", "paths": ["~/Downloads"], "days": 30,
     "exts": (".dmg", ".pkg", ".zip", ".iso", ".xip"), "default": False,
     "desc": "只挑 30 天没动过的安装包移到废纸篓。文档、图片、视频一概不碰。"},
    {"key": "xcode_arch", "name": "Xcode 归档包", "mode": "trash", "risk": "care",
     "paths": ["~/Library/Developer/Xcode/Archives"], "default": False,
     "desc": "每次上架留下的整包，含调试符号。已上线的项目可删，删了不能再从里面导出。"},
    {"key": "ios_support", "name": "iOS 真机支持文件", "mode": "trash", "risk": "care",
     "paths": ["~/Library/Developer/Xcode/iOS DeviceSupport"], "default": False,
     "desc": "连 iPhone 调试时生成的符号文件，删掉后重新连一次会自动重建。"},
    {"key": "ios_backup", "name": "iPhone / iPad 备份", "mode": "trash",
     "risk": "danger",
     "paths": ["~/Library/Application Support/MobileSync/Backup"], "default": False,
     "desc": "整机备份，一台几十 GB。删了就没法从这台 Mac 恢复手机，确认别处还有备份再动。"},
]


def path_size(path):
    """递归累加字节数：不跟随符号链接，读不到就跳过"""
    total = 0
    stack = [path]
    while stack:
        p = stack.pop()
        try:
            st = os.lstat(p)
        except OSError:
            continue
        if stat.S_ISLNK(st.st_mode):
            continue
        if stat.S_ISREG(st.st_mode):
            # 按磁盘块算，和 du 的口径一致，扫描与清理的数字才不会打架
            total += getattr(st, "st_blocks", 0) * 512 or st.st_size
        elif stat.S_ISDIR(st.st_mode):
            try:
                with os.scandir(p) as it:
                    for e in it:
                        stack.append(e.path)
            except OSError:
                pass
    return total


def _walk_old(path, days=0, exts=None, limit=300000):
    """返回 [(文件路径, 字节数)]：早于 days 天、扩展名匹配的文件"""
    cutoff = time.time() - days * 86400 if days else 0
    out, n, stack = [], 0, [path]
    while stack and n < limit:
        p = stack.pop()
        try:
            with os.scandir(p) as it:
                for e in it:
                    n += 1
                    if n >= limit:
                        break
                    try:
                        if e.is_dir(follow_symlinks=False):
                            stack.append(e.path)
                            continue
                        if not e.is_file(follow_symlinks=False):
                            continue
                        st = e.stat()
                    except OSError:
                        continue
                    if cutoff and st.st_mtime > cutoff:
                        continue
                    if exts and not e.name.lower().endswith(tuple(exts)):
                        continue
                    out.append((e.path, getattr(st, "st_blocks", 0) * 512 or st.st_size))
        except OSError:
            pass
    return out


def clean_scan(it):
    """估算一项能腾出多少。

    返回 (KB, 文件数, 状态)：
      ok      正常统计
      empty   目录在，但里面是空的
      missing 根本没有这个目录
      denied  目录在，但系统不让读（需要「完全磁盘访问权限」）
    """
    kb, files = 0, 0
    seen = False
    denied = False
    days, exts = it.get("days"), it.get("exts")
    # globs：路径带随机后缀、没法写死的那种（如 Chrome 的临时签名副本）
    for g in it.get("globs") or []:
        for gp in glob.glob(os.path.expanduser(g)):
            if not os.path.isdir(gp):
                continue
            seen = True
            kb += du_kb(gp)
            files += 1
    for raw in (it.get("paths") or []):
        p = os.path.expanduser(raw)
        if not os.path.isdir(p):
            continue
        seen = True
        if days or exts:
            for _f, sz in _walk_old(p, days or 0, exts):
                kb += sz // 1024
                files += 1
        else:
            try:
                entries = os.listdir(p)
            except OSError:
                # 连列目录都不让 —— 典型是需要「完全磁盘访问权限」
                denied = True
                continue
            d = du_kb(p)
            kb += d if d > 0 else 0
            files += len(entries)
    if not seen:
        return 0, 0, "missing"
    if kb <= 0:
        return 0, 0, "denied" if (denied and not files) else "empty"
    return kb, files, "denied" if denied else "ok"


_CLEAN_MEMO = {}


def clean_scan_cached(it, ttl=600):
    """同一项 10 分钟内不重复统计——清理窗口关掉再打开就不用再等一遍"""
    key = (it.get("name"), tuple(it.get("paths") or ()),
           it.get("days"), tuple(it.get("exts") or ()),
           tuple(it.get("globs") or ()))
    now = time.time()
    hit = _CLEAN_MEMO.get(key)
    if hit and now - hit[0] < ttl:
        return hit[1]
    res = clean_scan(it)
    _CLEAN_MEMO[key] = (now, res)
    return res


def clean_memo_clear():
    _CLEAN_MEMO.clear()


def _rm_path(p):
    """删掉一个文件或整个目录，返回是否真的没了

    大目录交给系统 /bin/rm -rf（C 实现，比 Python 逐个 unlink 快好几倍）；
    rm 失败或残留时再用 shutil.rmtree 兜底一次。
    """
    try:
        if os.path.islink(p) or os.path.isfile(p):
            os.remove(p)
        else:
            run_cmd(["/bin/rm", "-rf", "--", p], timeout=3600)
            if os.path.lexists(p):
                shutil.rmtree(p, ignore_errors=True)
        return not os.path.lexists(p)
    except Exception:
        return False


def _to_trash(p):
    """移到废纸篓（同卷 rename，很快），重名自动加序号。
    实在移不动（权限、跨卷）就退回 Finder——Finder 放的才带「放回原处」。"""
    if not os.path.lexists(p):
        return True
    if os.path.dirname(os.path.abspath(p)) == TRASH_DIR:
        return _rm_path(p)
    base = os.path.basename(p.rstrip("/")) or "item"
    stamp = time.strftime("%m%d-%H%M%S")
    dst = os.path.join(TRASH_DIR, "%s %s" % (base, stamp))
    n = 2
    while os.path.exists(dst):
        dst = os.path.join(TRASH_DIR, "%s %s-%d" % (base, stamp, n))
        n += 1
    try:
        os.makedirs(TRASH_DIR, exist_ok=True)
        shutil.move(p, dst)
        return True
    except Exception:
        pass
    # 退回 Finder 试试
    try:
        esc = p.replace("\\", "\\\\").replace('"', '\\"')
        subprocess.run(["/usr/bin/osascript", "-e",
                        'tell application "Finder" to delete POSIX file "%s"' % esc],
                       capture_output=True, timeout=20)
    except Exception:
        return False
    return not os.path.lexists(p)


def clean_apply(it, dry=False, progress=None):
    """执行一项清理。返回 {freed, moved, removed, failed}（单位 KB）

    progress(path) 在每删一个目标前被调用——弹窗用它刷"已删多少项"的实时反馈。
    """
    res = {"freed": 0, "moved": 0, "removed": 0, "failed": 0}
    mode = it.get("mode", "purge")
    days, exts = it.get("days"), it.get("exts")
    for g in it.get("globs") or []:
        for gp in glob.glob(os.path.expanduser(g)):
            if not os.path.isdir(gp):
                continue
            gkb = du_kb(gp)
            if dry:
                ok = True
            elif mode == "trash":
                ok = _to_trash(gp)
            else:
                ok = _rm_path(gp)
            if not ok:
                res["failed"] += 1
                continue
            res["removed"] += 1
            if mode == "trash":
                res["moved"] += gkb
            else:
                res["freed"] += gkb
    for raw in (it.get("paths") or []):
        p = os.path.expanduser(raw)
        if not os.path.isdir(p):
            continue
        if days or exts:
            targets = _walk_old(p, days or 0, exts)
        else:
            targets = []
            try:
                with os.scandir(p) as it2:
                    for e in it2:
                        targets.append((e.path, path_size(e.path)))
            except OSError:
                continue
        for path, size in targets:
            if progress:
                try:
                    progress(path)
                except Exception:
                    pass
            kb = size // 1024
            if dry:
                ok = True
            elif mode == "trash":
                ok = _to_trash(path)
            else:
                ok = _rm_path(path)
            if not ok:
                res["failed"] += 1
                continue
            res["removed"] += 1
            if mode == "trash":
                res["moved"] += kb
            else:
                res["freed"] += kb
    return res


def clean_summary(res):
    """把执行结果翻成人话"""
    parts = []
    if res.get("freed"):
        parts.append("释放 %s" % human(res["freed"]))
    if res.get("moved"):
        parts.append("%s 移到废纸篓" % human(res["moved"]))
    if res.get("failed"):
        parts.append("%d 项被系统保护、已跳过" % res["failed"])
    return "、".join(parts) if parts else "没有需要清理的内容"

# ----------------------------------------------------------------- 应用卸载
# 只扫这几个地方。/System/Applications 里的都是系统自带，碰不得。
APP_SCAN_DIRS = ["/Applications", os.path.expanduser("~/Applications"),
                 os.path.expanduser("~/Desktop")]
# 电池医生自己不进列表，免得把自己卸了
APP_SELF_IDS = ("com.local.batterydoctor",)
# 系统关键程序，删了系统会出问题
APP_PROTECTED = {
    "com.apple.Safari",
    "com.apple.finder",
    "com.apple.dock",
    "com.apple.systempreferences",
    "com.apple.loginwindow",
    "com.apple.WindowManager",
    "com.apple.notificationcenterui",
    "com.apple.CoreServices",
    "com.apple.pkg",
}


def _app_plist(path):
    """读 .app 里的 Info.plist，读不到就返回空 dict"""
    try:
        with open(os.path.join(path, "Contents", "Info.plist"), "rb") as f:
            d = plistlib.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _dir_kb(path):
    """目录实际占盘大小（KB）。
    借系统的 du 来算——自己遍历要几十秒，du 快了约 80 倍。
    du 报的是实际块数，稀疏文件不会被算成满尺寸。"""
    try:
        out = subprocess.run(["/usr/bin/du", "-sk", path],
                             capture_output=True, text=True, timeout=180).stdout
    except Exception:
        return 0
    out = out.strip()
    if not out:
        return 0
    return to_int(out.split()[0])


def _last_used(path):
    """最近一次打开时间，说人话。Spotlight 没索引到就返回空串。"""
    try:
        out = subprocess.run(
            ["/usr/bin/mdls", "-raw", "-name", "kMDItemLastUsedDate", path],
            capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return ""
    if not out or out == "(null)":
        return ""
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", out)
    if not m:
        return ""
    try:
        d = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except Exception:
        return ""
    diff = (datetime.date.today() - d).days
    if diff <= 0:
        return "今天"
    if diff == 1:
        return "昨天"
    if diff < 7:
        return "%d 天前" % diff
    if diff < 30:
        return "%d 周前" % (diff // 7)
    if diff < 365:
        return "%d 个月前" % (diff // 30)
    return "%d 年前" % (diff // 365)


def _running_pids(app_path):
    """这个应用有没有正在运行的进程"""
    try:
        out = subprocess.run(
            ["/usr/bin/pgrep", "-f", os.path.join(app_path, "Contents") + "/"],
            capture_output=True, text=True, timeout=6).stdout
        return [x for x in out.split() if x.strip()]
    except Exception:
        return []


def _leftover_candidates(meta):
    """卸载后可能残留的目录/文件。
    这些多半是配置和用户数据，删了找不回来，所以单独一层确认。"""
    home = os.path.expanduser("~")
    name = os.path.basename(meta["path"])
    if name.endswith(".app"):
        name = name[:-4]
    bid = meta.get("bundle_id") or ""
    lib = os.path.join(home, "Library")
    out, seen = [], set()

    def add(p, label):
        p = os.path.expanduser(p)
        if p in seen:
            return
        seen.add(p)
        if os.path.lexists(p):
            out.append((p, label))

    for base, sub in (("Application Support", name), ("Application Support", bid),
                      ("Caches", name), ("Caches", bid),
                      ("Containers", bid), ("Group Containers", bid),
                      ("Logs", name), ("HTTPStorages", bid), ("WebKit", bid)):
        if sub:
            add(os.path.join(lib, base, sub), "%s/%s" % (base, sub))
    if bid:
        add(os.path.join(lib, "Preferences", bid + ".plist"), "Preferences")
    add(os.path.join(lib, "Saved Application State", name + ".savedState"),
        "Saved Application State")
    return out


def _can_remove(path):
    """能不能删——看父目录有没有写权限，不是看文件属主。
    /Applications 是 drwxrwxr-x root admin，admin 组成员就能删掉里面的东西，
    哪怕那个 app 本身是 root 拥有的。"""
    try:
        return os.access(os.path.dirname(path), os.W_OK)
    except Exception:
        return False


def scan_apps():
    """列出可卸载的应用。
    系统自带的、删不动的、电池医生自己都不列。"""
    out, seen = [], set()
    for d in APP_SCAN_DIRS:
        if not os.path.isdir(d):
            continue
        try:
            names = sorted(os.listdir(d))
        except OSError:
            continue
        for n in names:
            if not n.endswith(".app"):
                continue
            p = os.path.join(d, n)
            if p in seen or not os.path.isdir(p) or os.path.islink(p):
                continue
            seen.add(p)
            if not _can_remove(p):
                continue
            info = _app_plist(p)
            bid = info.get("CFBundleIdentifier") or ""
            if bid in APP_SELF_IDS or bid in APP_PROTECTED:
                continue
            out.append({
                "path": p,
                "name": (info.get("CFBundleDisplayName")
                         or info.get("CFBundleName") or n[:-4]),
                "version": (info.get("CFBundleShortVersionString")
                            or info.get("CFBundleVersion") or ""),
                "bundle_id": bid,
                "size": 0,
                "last_used": "",
                "running": False,
                "leftovers": [],
                "leftover_kb": 0,
            })
    return out


def enrich_apps(apps, on_one=None):
    """补齐大小、最后使用时间、残留清单、运行状态。
    都是慢操作（遍历目录、问 Spotlight），放后台线程并行跑。"""
    def work(a):
        try:
            a["size"] = _dir_kb(a["path"])
        except Exception:
            a["size"] = 0
        try:
            a["last_used"] = _last_used(a["path"])
        except Exception:
            a["last_used"] = ""
        try:
            a["leftovers"] = _leftover_candidates(a)
            a["running"] = bool(_running_pids(a["path"]))
        except Exception:
            a["leftovers"] = []
        if on_one:
            try:
                on_one(a)
            except Exception:
                pass

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
            list(ex.map(work, apps))
    except Exception:
        for a in apps:
            work(a)
    return apps


def uninstall_app(meta, with_leftovers=False, dry=False):
    """卸载一个应用。
    主体移到废纸篓（不是 rm，访达里能拖回去）；残留可选，默认不动。
    返回 {moved, leftover_kb, failed, errors}，单位 KB。"""
    res = {"moved": 0, "leftover_kb": 0, "leftover_n": 0, "failed": 0, "errors": []}
    path = meta.get("path") or ""
    kb = meta.get("size") or 0

    if dry:
        res["moved"] = kb
        for p, _lab in meta.get("leftovers") or []:
            try:
                res["leftover_kb"] += path_size(p) // 1024
            except Exception:
                pass
        res["leftover_n"] = len(meta.get("leftovers") or [])
        return res

    if os.path.lexists(path):
        if _to_trash(path):
            res["moved"] = kb
        else:
            res["failed"] += 1
            res["errors"].append("移入废纸篓失败：%s" % os.path.basename(path))

    if with_leftovers:
        for p, label in meta.get("leftovers") or []:
            try:
                lkb = path_size(p) // 1024
            except Exception:
                lkb = 0
            if not os.path.lexists(p):
                continue
            if _to_trash(p):
                res["leftover_kb"] += lkb
                res["leftover_n"] += 1
            else:
                res["failed"] += 1
                res["errors"].append("残留没清掉：%s" % label)
    return res




# ----------------------------------------------------------------- 一键优化
CLEAN_PATTERNS = ("shipit", "copilot", "homebrew", "helpd", "jetbrains", "sgskin")


class StepRow:
    """优化清单里的一行：状态圆点 + 标题 + 结果说明"""

    def __init__(self, parent, title):
        self.frame = tk.Frame(parent, bg=P["card"])
        self.frame.pack(fill="x", pady=(0, 1))
        self.icon = tk.Canvas(self.frame, width=20, height=20, bg=P["card"],
                              highlightthickness=0)
        self.icon.pack(side="left", padx=(0, 10), pady=8)
        box = tk.Frame(self.frame, bg=P["card"])
        box.pack(side="left", fill="x", expand=True)
        self.title = tk.Label(box, text=title, bg=P["card"], fg=P["text"],
                              font=(FONT, 11), anchor="w")
        self.title.pack(anchor="w")
        self.detail = tk.Label(box, text="等待中…", bg=P["card"], fg=P["faint"],
                               font=(FONT, 10), anchor="w", justify="left",
                               wraplength=520)
        self.detail.pack(anchor="w")
        self.set("pending")

    def set(self, state, detail=None):
        colors = {"pending": P["faint"], "run": P["amber"], "ok": P["green"],
                  "warn": P["amber"], "fail": P["red"], "info": P["blue"]}
        glyph = {"pending": "", "run": "•", "ok": "✓", "warn": "!",
                 "fail": "×", "info": "i"}
        c = self.icon
        c.delete("all")
        col = colors.get(state, P["faint"])
        if state in ("ok", "warn", "fail", "info"):
            c.create_oval(1, 1, 19, 19, fill=col, outline="")
            c.create_text(10, 10, text=glyph[state], fill="#FFFFFF",
                          font=(FONT, 10, "bold"))
        elif state == "run":
            c.create_oval(3, 3, 17, 17, fill=col, outline="")
            c.create_oval(7, 7, 13, 13, fill=P["card"], outline="")
        else:
            c.create_oval(3, 3, 17, 17, outline=col, width=2)
        if detail is not None:
            self.detail.configure(text=detail, fg=P["text2"] if state != "pending" else P["faint"])


class OptimizeDialog(tk.Toplevel):
    """一键优化：按清单逐项执行，实时显示进度，可撤销"""

    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.title("一键优化")
        self.configure(bg=P["card"])
        self.transient(app.root)
        self.resizable(False, False)
        self.moved_agents = []
        self.cache_moved = []
        self.report_path = None
        self.battery = None
        self.dry = bool(os.environ.get("BD_DRY"))
        self.counts = {"ok": 0, "warn": 0, "info": 0, "fail": 0}
        self.q = queue.Queue()
        self._alive = True

        self._build()
        self._center()
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(180, self._start)
        self.after(80, self._poll)

    def _center(self):
        self.update_idletasks()
        w, h = 660, 742
        r = self.app.root
        x = r.winfo_rootx() + (r.winfo_width() - w) // 2
        y = r.winfo_rooty() + max(20, (r.winfo_height() - h) // 3)
        self.geometry("%dx%d+%d+%d" % (w, h, x, y))

    def _build(self):
        head = tk.Frame(self, bg=P["card"])
        head.pack(fill="x", padx=24, pady=(20, 6))
        tk.Label(head, text="一键优化", bg=P["card"], fg=P["text"],
                 font=(FONT, 17, "bold")).pack(anchor="w")
        tk.Label(head, text="只做安全、可撤销的处理；需要硬件的部分会明确写出来，不会假装修好了。",
                 bg=P["card"], fg=P["muted"], font=(FONT, 11), justify="left",
                 wraplength=600).pack(anchor="w", pady=(3, 0))

        self.prog = tk.Canvas(self, height=6, bg=P["card"], highlightthickness=0)
        self.prog.pack(fill="x", padx=24, pady=(14, 6))
        self.prog.bind("<Configure>", lambda e: self._draw_prog())
        self._ratio = 0.0

        body = tk.Frame(self, bg=P["card"])
        body.pack(fill="both", expand=True, padx=24, pady=(2, 0))
        self.steps = [
            ("读取电源与电池状态", self._step_power),
            ("整理多余的后台启动项", self._step_agents),
            ("清理可再生的缓存文件", self._step_cache),
            ("检查磁盘剩余空间", self._step_disk),
            ("检查 Time Machine 备份", self._step_backup),
            ("检查发热与 CPU 限速", self._step_thermal),
            ("检查网络连通性", self._step_net),
            ("生成诊断报告到桌面", self._step_report),
            ("给出最终结论", self._step_verdict),
        ]
        self.rows = [StepRow(body, title) for title, _fn in self.steps]

        self.verdict = tk.Frame(self, bg=P["green_soft"], highlightthickness=1,
                                highlightbackground=P["green_line"])
        self.verdict.pack(fill="x", padx=24, pady=(10, 0))
        self.verdict_lbl = tk.Label(self.verdict, text="正在处理，请稍候…",
                                    bg=P["green_soft"], fg=P["text2"],
                                    font=(FONT, 11), anchor="w", justify="left",
                                    wraplength=590)
        self.verdict_lbl.pack(fill="x", padx=14, pady=10)

        foot = tk.Frame(self, bg=P["card"])
        foot.pack(fill="x", padx=24, pady=(12, 18))
        self.btn_close = RButton(foot, "关闭", self._close, "primary")
        self.btn_close.pack(side="right")
        self.btn_undo = RButton(foot, "撤销本次更改", self._undo, "secondary")
        self.btn_undo.set_enabled(False)
        self.btn_undo.pack(side="right", padx=8)
        self.btn_copy = RButton(foot, "复制报告", self._copy, "secondary")
        self.btn_copy.set_enabled(False)
        self.btn_copy.pack(side="right")
        self.btn_reveal = RButton(foot, "在访达中显示", self._reveal, "ghost")
        self.btn_reveal.set_enabled(False)
        self.btn_reveal.pack(side="left")
        self.btn_next = RButton(foot, "下一步怎么做", self._next_steps, "ghost")
        self.btn_next.pack(side="left", padx=8)

    def _draw_prog(self):
        c = self.prog
        c.delete("all")
        w = c.winfo_width() or 580
        round_rect(c, 0, 0, w, 6, 3, fill=P["track"], outline="")
        if self._ratio > 0:
            round_rect(c, 0, 0, max(6, w * self._ratio), 6, 3,
                       fill=P["accent"], outline="")

    def _set_prog(self, ratio):
        self._ratio = max(0.0, min(1.0, ratio))
        self._draw_prog()

    # ---------- 执行
    def _start(self):
        t = threading.Thread(target=self._worker, daemon=True)
        t.start()

    def _worker(self):
        total = len(self.steps)
        for i, (_title, fn) in enumerate(self.steps):
            self.q.put(("start", i, None, None))
            try:
                state, detail = fn()
            except Exception as e:
                state, detail = "fail", "执行出错：%s" % e
            self.q.put(("row", i, state, detail))
            self.q.put(("prog", (i + 1) / float(total), None, None))
        self.q.put(("done", None, None, None))

    def _poll(self):
        if not self._alive:
            return
        try:
            while True:
                kind, i, state, detail = self.q.get_nowait()
                if kind == "start":
                    self.rows[i].set("run", "正在处理…")
                elif kind == "row":
                    self.rows[i].set(state, detail)
                    self.counts[state] = self.counts.get(state, 0) + 1
                elif kind == "prog":
                    self._set_prog(i)
                elif kind == "done":
                    self._finish()
        except queue.Empty:
            pass
        except Exception:
            pass
        if self._alive:
            try:
                self.after(80, self._poll)
            except Exception:
                pass

    # ---------- 各步骤
    def _step_power(self):
        b = Battery.read()
        self.battery = b
        if not b.ok:
            return "fail", "读不到电池信息（可能不是笔记本机型）"
        probs = []
        if b.on_ac and b.ma < -300:
            probs.append("插着电源却在放电 %d mA" % b.ma)
        if b.adapter == "0" and b.on_ac:
            probs.append("系统认不出这个充电器")
        if b.qmax_avg and b.maxcap and b.health_qmax >= 75 \
                and abs(b.qmax_avg - b.maxcap) * 100 / max(1, b.qmax_avg) >= 25:
            probs.append("容量读数矛盾（系统 %d / 电芯 %d mAh）" % (b.maxcap, b.qmax_avg))
        elif b.health and b.health < 60:
            probs.append("电池容量只剩 %d%%" % b.health)
        if probs:
            return "warn", "、".join(probs)
        return "ok", "供电正常 · 电量 %d%% · 健康度 %d%%" % (b.pct, b.health)

    def _step_agents(self):
        agents = os.path.expanduser("~/Library/LaunchAgents")
        os.makedirs(BACKUP, exist_ok=True)
        moved = []
        for name in USER_AGENTS:
            src = os.path.join(agents, name)
            if os.path.exists(src):
                if self.dry:
                    moved.append(name)
                    continue
                try:
                    shutil.move(src, os.path.join(BACKUP, name))
                    moved.append(name)
                except Exception:
                    pass
        self.moved_agents = moved
        if moved:
            return "ok", "已停用 %d 个多余后台项，可随时撤销" % len(moved)
        return "info", "没有需要停用的项目，已经比较干净"

    def _step_cache(self):
        cache = os.path.expanduser("~/Library/Caches")
        trash = os.path.expanduser("~/.Trash")
        total = 0
        moved = []
        try:
            names = sorted(os.listdir(cache))
        except Exception:
            names = []
        for name in names:
            low = name.lower()
            if not any(p in low for p in CLEAN_PATTERNS):
                continue
            path = os.path.join(cache, name)
            if not os.path.isdir(path):
                continue
            kb = du_kb(path)
            if kb < 20000:
                continue
            if self.dry:
                total += max(kb, 0)
                moved.append(name)
                continue
            dest = os.path.join(trash, "%s.cache-%d" % (name, int(time.time())))
            try:
                shutil.move(path, dest)
                total += max(kb, 0)
                moved.append(name)
            except Exception:
                pass
        self.cache_moved = moved
        if total:
            tail = "演练未实际移动" if self.dry else "已放进废纸篓，清空后释放"
            return "ok", "清理 %s 可再生缓存（%s）" % (human(total), tail)
        return "info", "没有需要清理的大块缓存"

    def _step_disk(self):
        try:
            st = os.statvfs("/")
            free = st.f_bavail * st.f_frsize
            total = st.f_blocks * st.f_frsize
            pct = 100.0 * free / total
        except Exception:
            return "info", "无法读取磁盘信息"
        if pct < 10:
            return "warn", "只剩 %.0f%% 可用，系统会变慢，建议尽快清理" % pct
        if pct < 15:
            return "warn", "可用空间 %.0f%%，低于建议的 15%%" % pct
        return "ok", "可用 %.0f%%，空间充足" % pct

    def _step_backup(self):
        out = run_cmd(["/usr/bin/tmutil", "destinationinfo"], 6)
        if "No destinations" in out or not out.strip():
            return "warn", "还没有备份目标；这台机器随时会断电，建议尽快接一块外置盘开启备份"
        return "ok", "已配置备份目标"

    def _step_thermal(self):
        out = run_cmd(["/usr/bin/pmset", "-g", "therm"], 5)
        m = re.search(r"CPU_Speed_Limit\s*=\s*(\d+)", out)
        limit = to_int(m.group(1)) if m else None
        panics = 0
        for d in ("/Library/Logs/DiagnosticReports",
                  os.path.expanduser("~/Library/Logs/DiagnosticReports")):
            try:
                panics += len([f for f in os.listdir(d) if f.endswith(".panic")])
            except Exception:
                pass
        if limit is not None and limit < 80:
            return "warn", "CPU 被限制在 %d%%（供电不足的表现），未发现过热关机记录" % limit
        if panics:
            return "warn", "发现 %d 个内核崩溃报告，可进一步分析" % panics
        return "ok", "没有过热关机记录，也没有系统崩溃"

    def _step_net(self):
        d = read_net_basic()
        self.net_info = d
        self.app.net_info = d
        if not d["ip"]:
            return "warn", "没有拿到 IP 地址，当前无法上网（到「网络诊断」页可修复）"
        if d["proxy_on"] and not port_open(d["proxy_port"]):
            return "warn", ("系统代理指向 %s:%d 但没有程序监听，网页会全部打不开。"
                            "到「网络诊断」页点一下「一键修复联网」即可"
                            % (d["proxy_host"], d["proxy_port"]))
        code, secs = http_probe(HTTP_TEST, timeout=6)
        if code not in (200, 204):
            code2, secs2 = http_probe(HTTPS_TEST, timeout=6)
            if code2 in (200, 204):
                code, secs = code2, secs2
        if code in (200, 204):
            dns_txt = "、".join(d["dns"][:2]) or "路由器默认"
            return "ok", "外网正常（%d ms）· DNS %s" % (int(secs * 1000), dns_txt)
        return "fail", "外网访问失败，请到「网络诊断」页排查"

    def _step_report(self):
        text = self.app.build_report_text()
        name = "电池医生诊断报告-%s.txt" % time.strftime("%Y%m%d-%H%M")
        base = "/tmp" if self.dry else os.path.expanduser("~/Desktop")
        path = os.path.join(base, name)
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            self.report_path = path
            return "ok", ("已保存到桌面：%s" % name) if not self.dry else ("演练：已写入 %s" % path)
        except Exception as e:
            return "fail", "写入失败：%s" % e

    def _step_verdict(self):
        b = self.battery
        if b is None or not b.ok:
            return "info", "无法判断电源状态"
        if b.on_ac and b.adapter == "0":
            return "warn", ("软件层能做的已经做完了。剩下的「充电器不被识别 + 电池老化」"
                            "只能靠换硬件：先换原装 85W 充电器验证，再换电池。")
        if b.health and b.health < 60:
            return "warn", "软件层已处理完；电池健康只剩 %d%%，建议尽快更换电池。" % b.health
        if b.limit is not None and b.limit < 80:
            return "warn", "软件层已处理完；CPU 仍在降频，供电可能存在硬件问题。"
        return "ok", "软件层状态良好，不需要额外处理。"

    # ---------- 收尾
    def _finish(self):
        self._set_prog(1.0)
        self.btn_copy.set_enabled(True)
        self.btn_reveal.set_enabled(bool(self.report_path))
        self.btn_undo.set_enabled(bool(self.moved_agents))

        c = self.counts
        summary = "完成：%d 项已优化 · %d 项需留意 · %d 项无需处理" % (
            c.get("ok", 0), c.get("warn", 0), c.get("info", 0))
        if c.get("fail"):
            summary += " · %d 项失败" % c["fail"]
        if not self.dry and not self.app.monitoring:
            try:
                self.app.toggle_monitor()
                summary += "。已自动开始记录电源数据，下次断电前的采样会保留下来"
            except Exception:
                pass
        self.verdict_lbl.configure(text=summary + "。")
        self.prog.configure(bg=P["card"])

        try:
            self.app.refresh()
            if self.app.startup_loaded:
                self.app.refresh_startup()
        except Exception:
            pass

    def _undo(self):
        if not self.moved_agents:
            return
        agents = os.path.expanduser("~/Library/LaunchAgents")
        n = 0
        for name in self.moved_agents:
            src = os.path.join(BACKUP, name)
            if os.path.exists(src):
                try:
                    shutil.move(src, os.path.join(agents, name))
                    n += 1
                except Exception:
                    pass
        self.btn_undo.set_enabled(False)
        self.verdict_lbl.configure(text="已恢复 %d 个启动项（缓存文件仍在废纸篓，可自行还原）。" % n)
        try:
            self.app.refresh_startup()
        except Exception:
            pass

    def _copy(self):
        self.clipboard_clear()
        self.clipboard_append(self.app.build_report_text())
        self.verdict_lbl.configure(text="诊断报告已复制到剪贴板，可以直接粘贴给别人。")

    def _reveal(self):
        if self.report_path:
            subprocess.run(["/usr/bin/open", "-R", self.report_path])

    def _next_steps(self):
        b = self.battery
        parts = []
        if b and b.on_ac and b.adapter == "0":
            parts.append("1. SMC 重置（免费，先试这个）")
            parts.append("   关机 → 接上电源 → 同时按住 Shift+Control+Option+电源键 10 秒 →")
            parts.append("   全松手 → 开机。看菜单栏电池图标是否变成「正在充电」。")
            parts.append("")
            parts.append("2. 换一个原装 85W MagSafe 2 充电器（决定性一步）")
            parts.append("   系统现在读到的充电器 ID 是 0，说明它没有正常握手；")
            parts.append("   换原装后如果立刻显示正在充电、CPU 不再降频，问题就解决了。")
            parts.append("")
            parts.append("3. 换完仍不供电 → 检查充电口（DC-in 小板）")
            parts.append("   2015 款 15 寸的常见故障，配件一两百块，比换主板便宜得多。")
        if b and b.health and b.health < 80:
            parts.append("")
            parts.append("4. 换电池：健康度只剩 %d%%，电芯也失衡，撑不住峰值电流。" % b.health)
        if not parts:
            parts.append("目前没有需要处理的硬件问题。保持通风、避免深度放电即可。")
        parts.append("")
        parts.append("修好之前：先备份重要文件（目前没有 Time Machine 目标），电量别低于 40%。")
        messagebox.showinfo("下一步怎么做", "\n".join(parts))

    def _close(self):
        self._alive = False
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()


# ----------------------------------------------------------------- 磁盘清理界面
class CheckBox(tk.Canvas):
    """方框勾选控件"""

    def __init__(self, master, on=False, bg=None, command=None):
        self.bg = bg or P["card"]
        super().__init__(master, width=18, height=18, bg=self.bg,
                         highlightthickness=0, bd=0, cursor="pointinghand")
        self.on = bool(on)
        self.enabled = True
        self.command = command
        self._draw()
        self.bind("<Button-1>", self._click)

    def _draw(self):
        self.delete("all")
        if self.on:
            round_rect(self, 1, 1, 17, 17, 5, fill=P["accent"], outline="")
            self.create_line(5, 9, 8, 12, 13, 6, fill="#FFFFFF", width=2,
                             capstyle="round", joinstyle="round")
        else:
            round_rect(self, 1, 1, 17, 17, 5, fill=P["card2"],
                       outline=P["line"] if self.enabled else P["line2"], width=1)

    def _click(self, _=None):
        if not self.enabled:
            return
        self.set(not self.on)
        if self.command:
            self.command(self.on)

    def set(self, on):
        self.on = bool(on)
        self._draw()

    def set_enabled(self, on):
        self.enabled = bool(on)
        try:
            self.configure(cursor="pointinghand" if on else "arrow")
        except Exception:
            pass
        self._draw()


class ScrollBox(tk.Frame):
    """竖向滚动容器，子控件 pack 到 self.inner"""

    def __init__(self, master, bg=None):
        self.bg = bg or P["card"]
        super().__init__(master, bg=self.bg)
        self.canvas = tk.Canvas(self, bg=self.bg, highlightthickness=0, bd=0)
        self.vs = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self._on_scroll)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=self.bg)
        self.win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", self._cfg_inner)
        self.canvas.bind("<Configure>", self._cfg_canvas)
        self.canvas.bind("<MouseWheel>", self._wheel)
        self.inner.bind("<MouseWheel>", self._wheel)

    def _on_scroll(self, first, last):
        self.vs.set(first, last)
        if float(first) <= 0.001 and float(last) >= 0.999:
            self.vs.pack_forget()
        elif not self.vs.winfo_ismapped():
            self.vs.pack(side="right", fill="y")

    def _cfg_inner(self, _e):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _cfg_canvas(self, e):
        self.canvas.itemconfigure(self.win, width=e.width)

    def _wheel(self, e):
        bb = self.canvas.bbox("all")
        if bb and bb[3] > self.canvas.winfo_height():
            self.canvas.yview_scroll(-1 * int(e.delta), "units")


class CleanRow:
    """清理清单里的一行：勾选框 + 名称 + 风险标签 + 说明 + 大小/状态"""

    def __init__(self, parent, item, on_toggle=None):
        self.it = item
        self.bg = P["card"]
        self.on_toggle = on_toggle
        self.frame = tk.Frame(parent, bg=self.bg)
        self.frame.pack(fill="x")
        box = tk.Frame(self.frame, bg=self.bg)
        box.pack(fill="x", padx=14, pady=10)

        self.chk = CheckBox(box, item.get("on", False), bg=self.bg,
                            command=self._toggled)
        self.chk.pack(side="left", padx=(0, 12), anchor="n", pady=(1, 0))

        right = tk.Frame(box, bg=self.bg)
        right.pack(side="right", padx=(12, 0), anchor="n")
        self.size_lbl = tk.Label(right, text="—", bg=self.bg, fg=P["text2"],
                                 font=(MONO, 11), width=9, anchor="e")
        self.size_lbl.pack(anchor="e")
        self.state_lbl = tk.Label(right, text="扫描中…", bg=self.bg, fg=P["faint"],
                                  font=(FONT, 9), anchor="e")
        self.state_lbl.pack(anchor="e")

        mid = tk.Frame(box, bg=self.bg)
        mid.pack(side="left", fill="x", expand=True)
        head = tk.Frame(mid, bg=self.bg)
        head.pack(fill="x")
        self.name_lbl = tk.Label(head, text=item["name"], bg=self.bg, fg=P["text"],
                                 font=(FONT, 11, "bold"), anchor="w")
        self.name_lbl.pack(side="left")
        rk = item.get("risk", "safe")
        rtext = {"safe": "安全", "care": "需确认", "danger": "含个人数据"}.get(rk, "安全")
        rcol = {"safe": P["green"], "care": P["amber"], "danger": P["red"]}.get(rk, P["green"])
        self.risk_lbl = tk.Label(head, text=rtext, bg=self.bg, fg=rcol,
                                 font=(FONT, 9), anchor="w")
        self.risk_lbl.pack(side="left", padx=(8, 0))
        self.desc_lbl = tk.Label(mid, text=item["desc"], bg=self.bg, fg=P["faint"],
                                 font=(FONT, 9), anchor="w", justify="left",
                                 wraplength=420)
        self.desc_lbl.pack(fill="x", pady=(1, 0))

        # 整行可点：比只能点那个小方框好按
        for w in (self.frame, box, mid, head, self.name_lbl, self.risk_lbl,
                  self.desc_lbl, self.size_lbl):
            w.bind("<Button-1>", lambda e: self.chk._click(), add="+")
            try:
                w.configure(cursor="pointinghand")
            except Exception:
                pass
        self._paint()

    def _toggled(self, on):
        self.it["on"] = on
        self._paint()
        if self.on_toggle:
            self.on_toggle()

    def _paint(self):
        on = self.chk.on
        self.name_lbl.configure(fg=P["text"] if on else P["text2"])
        self.desc_lbl.configure(fg=P["faint"])

    def set_size(self, kb, files=0, status="ok"):
        self.it["status"] = status
        if status in ("missing", "denied"):
            self.size_lbl.configure(text="—")
            self.state_lbl.configure(
                text="无此项" if status == "missing" else "读取受限",
                fg=P["faint"] if status == "missing" else P["amber"])
            self.chk.set(False)
            self.chk.set_enabled(False)
            self.it["on"] = False
            self.name_lbl.configure(fg=P["muted"])
            return
        self.chk.set_enabled(True)
        self.size_lbl.configure(text=human(kb) if kb > 0 else "0")
        if kb <= 0:
            self.state_lbl.configure(text="很干净", fg=P["faint"])
            self.chk.set(False)
            self.it["on"] = False
            self.chk.set_enabled(False)
            self.name_lbl.configure(fg=P["muted"])
        elif files:
            self.state_lbl.configure(text="%d 个文件" % files, fg=P["faint"])
        else:
            self.state_lbl.configure(text="", fg=P["faint"])

    def set_state(self, text, color=None):
        self.state_lbl.configure(text=text, fg=color or P["text2"])


class CleanDialog(tk.Toplevel):
    """磁盘清理：扫描 → 勾选 → 二次确认 → 执行，全程可见"""

    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.title("磁盘清理")
        self.configure(bg=P["card"])
        self.transient(app.root)
        self.resizable(False, False)
        self.dry = bool(os.environ.get("BD_DRY"))
        self.q = queue.Queue()
        self._alive = True
        self.cleaning = False
        self.scanned = 0
        self.rows = []
        self.totals = {"freed": 0, "moved": 0, "removed": 0, "failed": 0}
        self.items = []
        for it in CLEAN_ITEMS:
            d = dict(it)
            d["on"] = bool(it.get("default"))
            d["size"] = None
            self.items.append(d)
        self._free0 = self._free_kb()

        self._build()
        self._center()
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(120, self._start_scan)
        self.after(80, self._poll)

    # ---------- 骨架
    def _build(self):
        head = tk.Frame(self, bg=P["card"])
        head.pack(fill="x", padx=24, pady=(20, 0))
        tk.Label(head, text="磁盘清理", bg=P["card"], fg=P["text"],
                 font=(FONT, 17, "bold")).pack(anchor="w")
        tk.Label(head,
                 text="只处理可再生的缓存和旧文件。每一项都先告诉你多大，勾选后还要再确认一次才动手。",
                 bg=P["card"], fg=P["muted"], font=(FONT, 11), justify="left",
                 wraplength=620).pack(anchor="w", pady=(3, 0))

        sm = tk.Frame(self, bg=P["card2"], highlightthickness=1,
                      highlightbackground=P["line"])
        sm.pack(fill="x", padx=24, pady=(13, 8))
        si = tk.Frame(sm, bg=P["card2"])
        si.pack(fill="x", padx=15, pady=12)
        left = tk.Frame(si, bg=P["card2"])
        left.pack(side="left")
        tk.Label(left, text="当前可用空间", bg=P["card2"], fg=P["muted"],
                 font=(FONT, 9)).pack(anchor="w")
        self.free_lbl = tk.Label(left, text="读取中…", bg=P["card2"], fg=P["text"],
                                 font=(FONT, 17, "bold"))
        self.free_lbl.pack(anchor="w")
        right = tk.Frame(si, bg=P["card2"])
        right.pack(side="right")
        tk.Label(right, text="已勾选 · 预计可释放", bg=P["card2"], fg=P["muted"],
                 font=(FONT, 9), anchor="e").pack(anchor="e")
        self.pick_lbl = tk.Label(right, text="—", bg=P["card2"], fg=P["faint"],
                                 font=(FONT, 17, "bold"), anchor="e")
        self.pick_lbl.pack(anchor="e")

        self.prog = tk.Canvas(self, height=5, bg=P["card"], highlightthickness=0)
        self.prog.pack(fill="x", padx=24, pady=(0, 9))
        self.prog.bind("<Configure>", lambda e: self._draw_prog())
        self._ratio = 0.0

        lst = Card(self, pad=0)
        lst.pack(fill="both", expand=True, padx=24)
        sb = ScrollBox(lst.body, P["card"])
        sb.pack(fill="both", expand=True, pady=2)
        for i, it in enumerate(self.items):
            self.rows.append(CleanRow(sb.inner, it, self._refresh_pick))
            if i < len(self.items) - 1:
                tk.Frame(sb.inner, bg=P["line2"], height=1).pack(fill="x")

        self.hint = tk.Label(self, text="正在扫描，请稍候…", bg=P["card"],
                             fg=P["muted"], font=(FONT, 9), justify="left",
                             wraplength=660, anchor="w")
        self.hint.pack(fill="x", padx=24, pady=(9, 0))

        # 二次确认条（默认不显示）
        self.cf = tk.Frame(self, bg=P["red_soft"], highlightthickness=1,
                           highlightbackground=P["red_line"])
        cfi = tk.Frame(self.cf, bg=P["red_soft"])
        cfi.pack(fill="x", padx=14, pady=10)
        self.cf_lbl = tk.Label(cfi, text="", bg=P["red_soft"], fg=P["text2"],
                               font=(FONT, 10), justify="left", wraplength=400,
                               anchor="w")
        self.cf_lbl.pack(side="left", fill="x", expand=True)
        RButton(cfi, "再看看", self._hide_confirm, "ghost",
                bg=P["red_soft"], size=11).pack(side="right", padx=(8, 0))
        RButton(cfi, "确认清理", self._run_clean, "danger",
                bg=P["red_soft"], size=11).pack(side="right")

        self.foot = tk.Frame(self, bg=P["card"])
        self.foot.pack(fill="x", padx=24, pady=(12, 18))
        self.btn_close = RButton(self.foot, "关闭", self._close, "secondary")
        self.btn_close.pack(side="right")
        self.btn_go = RButton(self.foot, "开始清理", self._ask_confirm, "primary")
        self.btn_go.set_enabled(False)
        self.btn_go.pack(side="right", padx=(0, 8))
        self.btn_none = RButton(self.foot, "全部取消", self._pick_none, "ghost",
                                size=11)
        self.btn_none.pack(side="left", padx=(8, 0))
        self.btn_safe = RButton(self.foot, "只选安全项", self._pick_safe, "ghost",
                                size=11)
        self.btn_safe.pack(side="left")

    def _center(self):
        self.update_idletasks()
        w, h = 748, 736
        r = self.app.root
        x = r.winfo_rootx() + (r.winfo_width() - w) // 2
        y = r.winfo_rooty() + max(16, (r.winfo_height() - h) // 3)
        self.geometry("%dx%d+%d+%d" % (w, h, max(0, x), y))

    def _draw_prog(self):
        c = self.prog
        c.delete("all")
        w = c.winfo_width() or 700
        round_rect(c, 0, 0, w, 5, 3, fill=P["track"], outline="")
        if self._ratio > 0:
            round_rect(c, 0, 0, max(6, w * self._ratio), 5, 3,
                       fill=P["accent"], outline="")

    def _set_prog(self, ratio):
        self._ratio = max(0.0, min(1.0, ratio))
        self._draw_prog()

    @staticmethod
    def _free_kb():
        try:
            st = os.statvfs("/")
            return st.f_bavail * st.f_frsize // 1024
        except Exception:
            return 0

    def _free_now(self):
        kb = self._free_kb()
        self.free_lbl.configure(text=human(kb))
        return kb

    # ---------- 勾选汇总
    def _selected(self):
        return [it for it in self.items
                if it.get("on") and (it.get("size") or 0) > 0]

    def _refresh_pick(self):
        sel = self._selected()
        kb = sum(it.get("size") or 0 for it in sel)
        self.pick_lbl.configure(text=human(kb) if kb > 0 else "—",
                                fg=P["accent"] if kb > 0 else P["faint"])
        if self.scanned >= len(self.items) and not self.cleaning:
            self.btn_go.set_enabled(bool(sel))

    def _pick_safe(self):
        for it in self.items:
            on = it.get("risk") == "safe" and (it.get("size") or 0) > 0
            it["on"] = on
        for r in self.rows:
            r.chk.set(r.it.get("on", False))
            r._paint()
        self._refresh_pick()

    def _pick_none(self):
        for it in self.items:
            it["on"] = False
        for r in self.rows:
            r.chk.set(False)
            r._paint()
        self._refresh_pick()

    # ---------- 扫描
    def _start_scan(self):
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def _scan_worker(self):
        total = len(self.items) or 1
        for i, it in enumerate(self.items):
            try:
                kb, files, status = clean_scan_cached(it)
            except Exception:
                kb, files, status = 0, 0, "denied"
            self.q.put(("size", i, (kb, files, status), None))
            self.q.put(("prog", (i + 1) / float(total), None, None))
        self.q.put(("scan_done", None, None, None))

    # ---------- 执行
    def _ask_confirm(self):
        sel = self._selected()
        if not sel:
            messagebox.showinfo("磁盘清理",
                                "还没有勾选任何项目。\n\n"
                                "点左边的方框，或者用「只选安全项」。")
            return
        n = len(sel)
        kb = sum(it.get("size") or 0 for it in sel)
        risky = [it["name"] for it in sel if it.get("risk") != "safe"]
        text = "将处理 %d 项，共 %s。" % (n, human(kb))
        if risky:
            text += "其中「%s」删除后无法恢复。" % "、".join(risky)
        else:
            text += "都是可再生的数据，删掉会自动重建。"
        self.cf_lbl.configure(text=text)
        self.cf.pack(fill="x", padx=24, pady=(9, 0), before=self.foot)

    def _hide_confirm(self):
        self.cf.pack_forget()

    def _run_clean(self):
        sel = [(i, it) for i, it in enumerate(self.items)
               if it.get("on") and (it.get("size") or 0) > 0]
        if not sel:
            return
        self.cf.pack_forget()
        self.cleaning = True
        self.btn_go.set_enabled(False)
        for b in (self.btn_safe, self.btn_none):
            b.set_enabled(False)
        self.hint.configure(text="正在清理，大目录（如缓存）可能要几分钟…",
                            fg=P["muted"])
        threading.Thread(target=self._clean_worker, args=(sel,), daemon=True).start()

    def _clean_text(self, done_n):
        """清理中的实时提示：正在清理第几项、已处理多少个目标"""
        info = getattr(self, "_clean_info", {}) or {}
        name = info.get("name", "")
        pos = "第 %d/%d 项" % (info.get("n", 1), info.get("total", 1)) if name else ""
        if done_n > 0:
            cnt = "{:,}".format(done_n) + " 个文件" if done_n < 10000 \
                else "%.1f 万个文件" % (done_n / 10000.0)
            return "正在清理：%s（%s）· 已处理 %s" % (name, pos, cnt)
        return "正在清理：%s（%s），大目录要几分钟，请别关窗口" % (name, pos) if name \
            else "正在清理，大目录（如缓存）可能要几分钟…"

    def _clean_worker(self, sel):
        total = len(sel) or 1
        for n, (i, it) in enumerate(sel):
            self.q.put(("clean_start", i,
                        {"name": it["name"], "n": n + 1, "total": total}, None))
            cnt = {"n": 0, "last": 0.0}

            def prog(path, c=cnt):
                c["n"] += 1
                now = time.time()
                if now - c["last"] >= 1.5:
                    c["last"] = now
                    self.q.put(("clean_tick", i, c["n"], None))

            try:
                r = clean_apply(it, dry=self.dry, progress=prog)
            except Exception as e:
                r = {"freed": 0, "moved": 0, "removed": 0, "failed": 1,
                     "err": str(e)}
            self.q.put(("clean_row", i, r, None))
            self.q.put(("prog", (n + 1) / float(total), None, None))
        self.q.put(("clean_done", None, None, None))

    # ---------- 消息泵
    def _poll(self):
        if not self._alive:
            return
        try:
            while True:
                kind, i, a, b = self.q.get_nowait()
                if kind == "size":
                    kb, files, status = a
                    self.items[i]["size"] = kb
                    self.items[i]["status"] = status
                    self.rows[i].set_size(kb, files, status)
                    self.scanned += 1
                    self._refresh_pick()
                elif kind == "prog":
                    self._set_prog(i)
                elif kind == "scan_done":
                    self._scan_finished()
                elif kind == "clean_start":
                    self.rows[i].set_state("清理中…", P["amber"])
                    self._clean_info = a or {}
                    self.hint.configure(text=self._clean_text(0), fg=P["muted"])
                elif kind == "clean_tick":
                    self.hint.configure(text=self._clean_text(a or 0),
                                        fg=P["muted"])
                elif kind == "clean_row":
                    self._row_done(i, a)
                elif kind == "clean_done":
                    self._clean_finished()
        except queue.Empty:
            pass
        except Exception:
            pass
        if self._alive:
            try:
                self.after(80, self._poll)
            except Exception:
                pass

    def _scan_finished(self):
        self._set_prog(1.0)
        self._free_now()
        self._refresh_pick()
        total = sum(it.get("size") or 0 for it in self.items)
        denied = [it["name"] for it in self.items if it.get("status") == "denied"]
        if total <= 0:
            text = ("这台机器没有多少可清理的东西。空间可能被其他用户的文件、"
                    "系统快照或 Time Machine 本地备份占着。")
        else:
            text = ("共发现 %s 可清理。移到废纸篓的部分要清空废纸篓后才真正腾出空间。"
                    % human(total))
        if denied:
            text += (" 另有 %s 读不到——它们受系统保护，需要在「系统设置 → 隐私与安全性 → "
                     "完全磁盘访问权限」里给电池医生授权后才能统计。"
                     % "、".join(denied[:3]))
        self.hint.configure(text=text,
                            fg=P["amber"] if denied else P["muted"])

    def _row_done(self, i, r):
        for k in ("freed", "moved", "removed", "failed"):
            self.totals[k] = self.totals.get(k, 0) + r.get(k, 0)
        self.rows[i].set_state(clean_summary(r),
                               P["green"] if (r.get("freed") or r.get("moved"))
                               else P["faint"])

    def _clean_finished(self):
        self.cleaning = False
        head = clean_summary(self.totals)
        before, after = self._free0, self._free_now()
        self.hint.configure(
            text="清理完成：%s。可用空间 %s → %s。移到废纸篓的东西在访达里还能找回。"
                 % (head, human(before), human(after)), fg=P["green"])
        self._set_prog(1.0)
        self.btn_go.set_text("重新扫描")
        self.btn_go.command = self._rescan
        self.btn_go.set_enabled(True)
        self.btn_safe.set_enabled(True)
        self.btn_none.set_enabled(True)
        try:
            clean_memo_clear()
            scan_cache_drop()
            self.app.start_scan(force=True)
            self.app.add_event("磁盘清理：%s" % head, "green")
        except Exception:
            pass

    def _rescan(self):
        self.scanned = 0
        self.totals = {"freed": 0, "moved": 0, "removed": 0, "failed": 0}
        for it in self.items:
            it["size"] = None
        for r in self.rows:
            r.size_lbl.configure(text="—")
            r.state_lbl.configure(text="扫描中…", fg=P["faint"])
            r.chk.set(r.it.get("on", False))
        self.btn_go.set_text("开始清理")
        self.btn_go.command = self._ask_confirm
        self.btn_go.set_enabled(False)
        self.hint.configure(text="正在扫描，请稍候…", fg=P["muted"])
        self._set_prog(0.0)
        clean_memo_clear()
        self._start_scan()

    def _close(self):
        if self.cleaning:
            if messagebox.askyesno(
                    "磁盘清理",
                    "清理还在进行中。\n\n现在关闭的话看不到结果，但删除不会中断，"
                    "已完成的部分照常生效。\n\n确定要关吗？"):
                pass
            else:
                return
        self._alive = False
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()


# ----------------------------------------------------------------- 检查更新（弹窗）
class UpdateDialog(tk.Toplevel):
    """手动检查更新。

    设计上的取舍：不做「启动就静默连线」的自动更新——那要么偷偷联网，
    要么在没有服务器时天天失败。这里只在两种情况下发请求：
    你点「检查更新」，或者你自己勾了「每周自动看一眼」。
    """

    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.title("检查更新")
        self.configure(bg=P["card"])
        self.transient(app.root)
        self.resizable(False, False)
        self.grab_set()
        self.info = None
        self.dl_path = None

        pad = tk.Frame(self, bg=P["card"], width=520)
        pad.pack(fill="both", expand=True, padx=24, pady=20)
        self.pad = pad

        tk.Label(pad, text="检查更新", bg=P["card"], fg=P["text"],
                 font=(FONT, 15, "bold")).pack(anchor="w")

        self.ver_lbl = tk.Label(pad, text="当前版本 v%s　·　正在连接 v5pc.com…" % VERSION,
                                bg=P["card"], fg=P["text2"], font=(FONT, 10),
                                justify="left", anchor="w", wraplength=470)
        self.ver_lbl.pack(fill="x", pady=(4, 8))

        self.notes = tk.Label(pad, text="", bg=P["card2"], fg=P["text2"],
                              font=(FONT, 10), justify="left", anchor="w",
                              wraplength=444, padx=12, pady=10)
        self.notes.pack(fill="x")

        self.bar = tk.Canvas(pad, height=4, bg=P["card"], highlightthickness=0)
        self.bar.pack(fill="x", pady=(10, 0))

        self.hint = tk.Label(pad, text="", bg=P["card"], fg=P["faint"],
                             font=(FONT, 9), justify="left", anchor="w",
                             wraplength=470)
        self.hint.pack(fill="x", pady=(8, 0))

        foot = tk.Frame(pad, bg=P["card"])
        foot.pack(fill="x", pady=(14, 0))
        self.btn_dl = RButton(foot, "下载并安装", self._download, "primary")
        self.btn_dl.pack(side="left")
        self.btn_dl.set_enabled(False)
        RButton(foot, "关闭", self.destroy, "ghost").pack(side="left", padx=(8, 0))

        self.auto = tk.BooleanVar(value=bool(update_cfg_read().get("auto")))
        chk = tk.Checkbutton(
            pad, text="每周自动检查一次（只在你勾选后才联网，关闭后一个请求都不发）",
            variable=self.auto, command=self._toggle_auto, bg=P["card"],
            fg=P["muted"], font=(FONT, 9), anchor="w", activebackground=P["card"],
            selectcolor=P["card2"], highlightthickness=0, bd=0)
        chk.pack(fill="x", pady=(10, 0))

        self._check()

    # ---------- 状态
    def _set_prog(self, frac):
        self.bar.delete("all")
        w = max(to_int(self.bar.winfo_width()), 1)
        self.bar.create_rectangle(0, 1, w, 3, fill=P["line2"], outline="")
        if frac > 0:
            self.bar.create_rectangle(0, 1, w * min(frac, 1.0), 3,
                                      fill=P["accent"], outline="")

    def _toggle_auto(self):
        update_cfg_write(auto=bool(self.auto.get()))

    def _check(self):
        self.ver_lbl.configure(text="当前版本 v%s　·　正在连接 v5pc.com…" % VERSION)
        self.notes.configure(text="")
        self.hint.configure(text="", fg=P["faint"])

        def work():
            r = update_check()
            try:
                self.after(0, lambda: self._checked(r))
            except Exception:
                pass
        threading.Thread(target=work, daemon=True).start()

    def _checked(self, r):
        if not r.get("ok"):
            self.ver_lbl.configure(text="当前版本 v%s　·　检查失败" % VERSION)
            self.hint.configure(
                text="连不上更新服务器：%s\n没网、被墙或服务器维护时都会这样，"
                     "不影响使用——直接去 v5pc.com/battery 手动下载也行。" % r.get("err", ""),
                fg=P["amber"])
            self.btn_dl.set_text("重试")
            self.btn_dl.command = self._check
            self.btn_dl.set_enabled(True)
            return
        info = r["info"]
        self.info = info
        cur, latest = info.get("current", VERSION), info.get("version", VERSION)
        if not info.get("newer"):
            self.ver_lbl.configure(
                text="当前版本 v%s　·　已是最新版本" % cur)
            self.notes.configure(text="不用更新。有新版本时这里会列出改了什么。")
            self.hint.configure(
                text="这个版本号来自 v5pc.com/battery/version.json。",
                fg=P["faint"])
            self.btn_dl.set_text("已是最新")
            self.btn_dl.set_enabled(False)
            return
        notes = info.get("notes") or []
        if isinstance(notes, str):
            notes = [notes]
        body = "\n".join("· " + str(n) for n in notes[:8]) or "（这次没有写更新说明）"
        self.ver_lbl.configure(
            text="当前版本 v%s　·　发现新版本 v%s（%s）"
                 % (cur, latest, info.get("date", "")))
        self.notes.configure(text="更新内容：\n" + body)
        size = info.get("size_mb")
        self.hint.configure(
            text=("下载约 %s MB，下完会自动打开磁盘映像，把「电池医生」拖进"
                  "「应用程序」覆盖旧版即可。设置和采样记录都在 "
                  "~/Library/Logs/PowerWatch，不会被覆盖。"
                  % (size if size else "30")),
            fg=P["muted"])
        self.btn_dl.set_text("下载 v%s" % latest)
        self.btn_dl.command = self._download
        self.btn_dl.set_enabled(True)

    # ---------- 下载
    def _download(self):
        if not self.info or not self.info.get("newer"):
            self._check()
            return
        url = self.info.get("url") or ""
        if not url:
            self.hint.configure(text="清单里没有下载地址，请到 v5pc.com/battery 手动下载。",
                                fg=P["amber"])
            return
        ver = self.info.get("version", "new")
        self.btn_dl.set_enabled(False)
        self.btn_dl.set_text("下载中…")
        self.hint.configure(text="正在下载…", fg=P["muted"])

        def work():
            dest = os.path.join(os.path.expanduser("~/Downloads"),
                                "BatteryDoctor-%s.dmg" % ver)
            try:
                update_download(
                    url, dest,
                    progress=lambda f: self.after(0, lambda: self._set_prog(f)))
                self.after(0, lambda: self._downloaded(dest))
            except Exception as e:
                self.after(0, lambda: self._dl_failed(str(e)))
        threading.Thread(target=work, daemon=True).start()

    def _downloaded(self, path):
        self.dl_path = path
        self._set_prog(1.0)
        self.hint.configure(
            text="下载完成：%s\n磁盘映像已打开，把「电池医生」拖进「应用程序」覆盖旧版，"
                 "然后重新打开即可。" % path.replace(os.path.expanduser("~"), "~"),
            fg=P["green"])
        self.btn_dl.set_text("已下载")
        try:
            subprocess.Popen(["/usr/bin/open", path])
        except Exception:
            pass
        try:
            self.app.add_event("检查更新：已下载 v%s" % self.info.get("version", ""), "green")
        except Exception:
            pass

    def _dl_failed(self, err):
        self.btn_dl.set_text("重试下载")
        self.btn_dl.command = self._download
        self.btn_dl.set_enabled(True)
        self.hint.configure(
            text="下载失败：%s\n网络慢的时候常见，重试一次通常就好了；"
                 "也可以直接到 v5pc.com/battery 下载。" % err, fg=P["amber"])


# ----------------------------------------------------------------- 负载压降测试
class LoadTestDialog(tk.Toplevel):
    """短时满负载，看电池带载时电压塌多少。
    「用一会就关机」最直接的实证：一上负载电压就掉到保护线 —— 电芯内阻高或供电链路有问题。
    成熟软件（HWiNFO 的 battery wear test）做的也是这件事，只是没人替你解读。"""

    LOAD_SEC = 8
    IDLE_SEC = 3

    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.title("负载压降测试")
        self.configure(bg=P["card"])
        self.transient(app.root)
        self.resizable(False, False)
        self.grab_set()
        self.procs = []
        self.idle, self.under = [], []
        self.phase = "ready"
        self.result = None

        pad = tk.Frame(self, bg=P["card"])
        pad.pack(fill="both", expand=True, padx=22, pady=18)
        tk.Label(pad, text="负载压降测试", bg=P["card"], fg=P["text"],
                 font=(FONT, 15, "bold")).pack(anchor="w")
        tk.Label(pad,
                 text="先安静测 3 秒，再让 4 个核心满载跑 8 秒，同时每 0.3 秒记录电压和电流。\n"
                      "健康电池在满载时电压只会掉一点；掉了半伏以上，说明电池撑不住峰值功率——\n"
                      "这正是「一忙起来就关机」的物理原因。",
                 bg=P["card"], fg=P["text2"], font=(FONT, 10), justify="left",
                 wraplength=500).pack(anchor="w", pady=(4, 8))

        warn = tk.Frame(pad, bg=P["amber_soft"], highlightthickness=1,
                        highlightbackground=P["amber_line"])
        warn.pack(fill="x", pady=(0, 10))
        tk.Label(warn, bg=P["amber_soft"], fg=P["amber"], font=(FONT, 9),
                 justify="left", anchor="w", wraplength=488, padx=10, pady=8,
                 text="⚠︎ 这台机器本来就可能在满载时关机。真关机也不是白跑："
                      "监控已经在每 5 秒落盘，重启后能看到断电前那一刻的电压曲线，"
                      "正好是最有力的证据。建议先保存手头的东西再开始。").pack(fill="x")

        self.stage = tk.Label(pad, text="准备就绪", bg=P["card"], fg=P["muted"],
                              font=(FONT, 10), anchor="w")
        self.stage.pack(fill="x")

        self.cv = tk.Canvas(pad, height=132, bg=P["card2"], highlightthickness=1,
                            highlightbackground=P["line2"])
        self.cv.pack(fill="x", pady=(6, 8))

        self.readout = tk.Frame(pad, bg=P["card"])
        self.readout.pack(fill="x")
        self.lbl_v = tk.Label(self.readout, text="电压 —", bg=P["card"], fg=P["text"],
                              font=(MONO, 11, "bold"))
        self.lbl_v.pack(side="left")
        self.lbl_a = tk.Label(self.readout, text="电流 —", bg=P["card"], fg=P["text"],
                              font=(MONO, 11, "bold"))
        self.lbl_a.pack(side="left", padx=(16, 0))
        self.lbl_r = tk.Label(self.readout, text="", bg=P["card"], fg=P["accent"],
                              font=(MONO, 11, "bold"))
        self.lbl_r.pack(side="right")

        self.verdict = tk.Label(pad, text="", bg=P["card"], fg=P["text2"],
                                font=(FONT, 10), justify="left", anchor="w",
                                wraplength=500)
        self.verdict.pack(fill="x", pady=(8, 0))

        btns = tk.Frame(pad, bg=P["card"])
        btns.pack(fill="x", pady=(12, 0))
        self.btn_go = RButton(btns, "开始测试（约 12 秒）", self.start, "primary", size=11)
        self.btn_go.pack(side="left")
        self.btn_stop = RButton(btns, "中止", self.abort, "secondary", size=11)
        self.btn_stop.pack(side="left", padx=8)
        self.btn_stop.set_enabled(False)
        RButton(btns, "关闭", self._close, "ghost", size=11).pack(side="right")

        self.protocol("WM_DELETE_WINDOW", self._close)
        self.update_idletasks()
        w, h = 566, 512
        x = app.root.winfo_rootx() + (app.root.winfo_width() - w) // 2
        y = app.root.winfo_rooty() + max(12, (app.root.winfo_height() - h) // 4)
        self.geometry("%dx%d+%d+%d" % (w, h, x, y))

    # ---- 控制
    def start(self):
        b = Battery.read()
        if b.on_ac:
            messagebox.showinfo("负载压降测试",
                                "现在接着电源，测的是「电池」的带载能力，电源会盖住问题。\n"
                                "请先拔掉充电器再试——这也是你平时最容易关机的状态。",
                                parent=self)
            return
        if b.pct < 15:
            if not messagebox.askyesno("电量偏低",
                                       "电量只剩 %d%%。跑这个测试很可能直接关机。\n"
                                       "真关机的话数据也会留下来，但建议先充到 30%% 以上。\n\n"
                                       "仍要现在测试吗？" % b.pct, parent=self):
                return
        else:
            if not messagebox.askyesno(
                    "确认开始",
                    "接下来会有 8 秒风扇满载、机器发热，并且有可能触发一次真实关机。\n"
                    "请先保存正在编辑的东西。\n\n开始吗？", parent=self):
                return
        self.phase = "idle"
        self.t0 = time.time()
        self.idle, self.under = [], []
        self.btn_go.set_enabled(False)
        self.btn_stop.set_enabled(True)
        self.verdict.configure(text="")
        self.lbl_r.configure(text="")
        self._tick()

    def _spawn_load(self):
        for _ in range(4):
            try:
                self.procs.append(subprocess.Popen(
                    ["/bin/sh", "-c", "while :; do :; done"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
            except Exception:
                pass

    def _kill_load(self):
        for p in self.procs:
            try:
                p.terminate()
            except Exception:
                pass
        for p in self.procs:
            try:
                p.kill()
                p.wait(timeout=2)
            except Exception:
                pass
        self.procs = []

    def abort(self):
        self._kill_load()
        self.phase = "ready"
        self.btn_go.set_enabled(True)
        self.btn_stop.set_enabled(False)
        self.stage.configure(text="已中止，没有产生结论。")

    def _close(self):
        self._kill_load()
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()

    # ---- 采样
    def _tick(self):
        if self.phase == "ready":
            return
        try:
            b = Battery.read()
        except Exception:
            b = None
        now = time.time() - self.t0
        if b is not None and b.ok:
            if self.phase == "idle":
                self.idle.append(b)
                self.stage.configure(text="安静采样中… %.1f / %.0f 秒" % (now, self.IDLE_SEC))
                if now >= self.IDLE_SEC:
                    self.phase = "load"
                    self._spawn_load()
            else:
                self.under.append(b)
                self.stage.configure(
                    text="满载测试中… %.1f / %.0f 秒（风扇会响，属正常）"
                         % (now - self.IDLE_SEC, self.LOAD_SEC))
                if now - self.IDLE_SEC >= self.LOAD_SEC:
                    self._finish()
                    return
            self.lbl_v.configure(text="电压 %d mV" % b.volt)
            self.lbl_a.configure(text="电流 %+d mA" % b.ma)
        self._draw()
        self.after(300, self._tick)

    def _draw(self):
        c = self.cv
        c.delete("all")
        W = max(120, c.winfo_width())
        H = 132
        pts = [(s.volt, P["blue"]) for s in self.idle] + \
              [(s.volt, P["red"]) for s in self.under]
        if len(pts) < 2:
            c.create_text(W // 2, H // 2, text="等待采样…", fill=P["faint"],
                          font=(FONT, 9))
            return
        vs = [v for v, _ in pts]
        lo, hi = min(vs) - 120, max(vs) + 120
        span = max(1, hi - lo)
        total = max(2, len(pts) - 1)
        for i, (v, col) in enumerate(pts):
            x = 12 + (W - 24) * i / total
            y = H - 12 - (H - 24) * (v - lo) / float(span)
            if i:
                pv, pc = pts[i - 1]
                px = 12 + (W - 24) * (i - 1) / total
                py = H - 12 - (H - 24) * (pv - lo) / float(span)
                c.create_line(px, py, x, y, fill=col, width=2)
            c.create_oval(x - 2, y - 2, x + 2, y + 2, fill=col, outline="")
        c.create_text(12, 10, anchor="w", text="%d mV" % hi, fill=P["faint"],
                      font=(MONO, 8))
        c.create_text(12, H - 10, anchor="w", text="%d mV" % lo, fill=P["faint"],
                      font=(MONO, 8))

    def _finish(self):
        self._kill_load()
        self.phase = "ready"
        self.btn_go.set_enabled(True)
        self.btn_stop.set_enabled(False)
        self._draw()
        if not self.idle or len(self.under) < 3:
            self.stage.configure(text="采样不够，没能得出结论。")
            return

        def med(xs):
            xs = sorted(xs)
            return xs[len(xs) // 2]

        v_idle = med([s.volt for s in self.idle])
        a_idle = med([s.ma for s in self.idle])
        tail = self.under[len(self.under) // 2:]
        v_load = med([s.volt for s in tail])
        a_load = med([s.ma for s in tail])
        a_peak = min([s.ma for s in self.under])      # 放电时是负值，取最负
        drop = v_idle - v_load
        di = abs(a_load - a_idle)
        r = (drop / float(di) * 1000.0) if di > 150 else 0.0

        self.result = {"v_idle": v_idle, "v_load": v_load, "drop": drop,
                       "a_idle": a_idle, "a_load": a_load, "a_peak": a_peak,
                       "r_mohm": r}
        self.stage.configure(text="测试完成（安静 %d mV / %+d mA → 满载 %d mV / %+d mA）"
                                  % (v_idle, a_idle, v_load, a_load))
        if r:
            self.lbl_r.configure(text="估算内阻 %.0f mΩ" % r)

        if not di or di < 150:
            lvl, head = "info", "电流没上去，测不出压降"
            body = ("负载期间电流只增加了 %d mA，可能系统在限流，或负载被系统让给了别的核心。"
                    "换个时间（别在跑下载/同步时）再试一次。" % di)
        elif drop < 180 and r < 90:
            lvl, head = "green", "带载能力正常：满载只掉了 %d mV" % drop
            body = ("内阻约 %.0f mΩ，属于健康范围。电池在峰值负载下还能稳住电压，"
                    "所以「一会就关机」不太可能出在电池带载能力上，"
                    "更像是主板供电或电源适配器那一侧的问题。" % r)
        elif drop < 420 and r < 170:
            lvl, head = "amber", "带载能力偏弱：满载掉了 %d mV" % drop
            body = ("内阻约 %.0f mΩ，比新电池高不少。日常轻负载还能撑，"
                    "但一开视频会议、编译、游戏这种峰值功率，电压就会往保护线靠。"
                    "这解释了偶发的关机。" % r)
        else:
            lvl, head = "red", "带载能力差：满载掉了 %d mV" % drop
            body = ("内阻约 %.0f mΩ，电压一压就塌。电池已经无法提供峰值电流，"
                    "系统会在负载上来时直接断电保护——这就是「用一会就关机」。"
                    "换电池是主要解法，换之前先做一次校准排除读数问题。" % r)
        self.verdict.configure(text=head + "。" + body,
                              fg={"green": P["green"], "amber": P["amber"],
                                  "red": P["red"], "info": P["muted"]}[lvl])
        st = _care_state()
        st["loadtest"] = {"ts": time.strftime("%Y-%m-%d %H:%M"), "drop": drop,
                          "r": round(r), "level": lvl}
        _care_save(st)
        try:
            self.app.add_event("负载压降测试：掉了 %d mV，内阻约 %.0f mΩ" % (drop, r),
                               lvl if lvl != "info" else "info")
        except Exception:
            pass


# ----------------------------------------------------------------- 主程序
class App:
    def __init__(self, root):
        self.root = root
        self.monitoring = False
        self._after_id = None
        self._scan_thread = None
        self._instant_thread = None
        self._energy_thread = None
        self.events = []
        self.page = "overview"
        self.proc_mode = "avg"
        self.proc_rows = []
        self.net_info = {}
        self.net_checks = []
        self.net_loaded = False
        self._net_thread = None
        self._net_q = None
        os.makedirs(BASE, exist_ok=True)

        root.title(APP_NAME)
        root.configure(bg=P["bg"])
        root.geometry("1024x780")
        root.minsize(960, 720)
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.bind("<Command-r>", lambda e: self.refresh())

        self._style()
        self._build_shell()
        self._build_pages()
        self.show_page("overview")
        self.check_previous_shutdown()
        self.refresh()
        self.log_startup()
        self.root.after(5000, self._tick)
        # 用户勾了「每周自动检查」才会真的联网，默认什么都不发
        self.root.after(3000, self.update_auto_maybe)

        if os.environ.get("BD_SELFTEST"):
            root.after(2500, self._selftest)
        if os.environ.get("BD_SMOKE"):
            root.after(1200, self._smoke)
        if os.environ.get("BD_SHOW_OPT"):
            root.after(900, self.one_click_optimize)
        if os.environ.get("BD_INSTALL_DAILY"):
            root.after(1500, self.install_daily)
        if os.environ.get("BD_PAGE"):
            root.after(700, lambda: self.show_page(os.environ["BD_PAGE"]))
        if os.environ.get("BD_CLEAN"):
            root.after(900, self.open_clean)
        if os.environ.get("BD_AUTOSTART") or "--autostart" in sys.argv:
            root.after(1500, self._autostart_mode)
        if os.path.exists(os.path.join(BASE, ".probe")):
            root.after(1400, self._probe)

    # ---------- 全局样式
    def _style(self):
        st = ttk.Style()
        try:
            st.theme_use("aqua")
        except Exception:
            pass
        st.configure("Vertical.TScrollbar", troughcolor=P["bg"], background=P["line"],
                     bordercolor=P["bg"], arrowcolor=P["muted"], width=10)

    # ---------- 外壳：侧栏 + 内容区
    def _build_shell(self):
        self.side = tk.Frame(self.root, bg=P["sidebar"], width=196)
        self.side.pack(side="left", fill="y")
        self.side.pack_propagate(False)

        brand = tk.Frame(self.side, bg=P["sidebar"])
        brand.pack(fill="x", padx=16, pady=(22, 18))
        ic = tk.Canvas(brand, width=32, height=32, bg=P["sidebar"], highlightthickness=0)
        ic.pack(side="left")
        round_rect(ic, 1, 7, 27, 25, 6, fill=P["accent"], outline="")
        ic.create_rectangle(27, 12, 30, 20, fill=P["accent"], outline="")
        ic.create_text(14, 16, text="♥", fill="#FFFFFF", font=(FONT, 11, "bold"))
        tbox = tk.Frame(brand, bg=P["sidebar"])
        tbox.pack(side="left", padx=(9, 0))
        tk.Label(tbox, text=APP_NAME, bg=P["sidebar"], fg=P["text"],
                 font=(FONT, 13, "bold")).pack(anchor="w")
        tk.Label(tbox, text="Battery Doctor", bg=P["sidebar"], fg=P["faint"],
                 font=("Menlo", 8)).pack(anchor="w")

        self.nav = {}
        nav_items = [("overview", "体检概览"), ("battery", "电池详情"),
                     ("charge", "充电养护"), ("procs", "进程负载"),
                     ("storage", "存储空间"), ("startup", "启动项目"),
                     ("uninstall", "应用卸载"),
                     ("network", "网络诊断"), ("trend", "趋势记录")]
        for key, title in nav_items:
            it = NavItem(self.side, title, key, self.show_page)
            it.pack(fill="x", padx=8, pady=1)
            self.nav[key] = it

        foot = tk.Frame(self.side, bg=P["sidebar"])
        foot.pack(side="bottom", fill="x", padx=16, pady=16)
        line = tk.Frame(foot, bg=P["line"], height=1)
        line.pack(fill="x", pady=(0, 10))
        safe = tk.Frame(foot, bg=P["sidebar"])
        safe.pack(fill="x")
        tk.Label(safe, text="●", bg=P["sidebar"], fg=P["green"],
                 font=(FONT, 8)).pack(side="left")
        tk.Label(safe, text="本地运行 · 不联网\n改动前都会先问你", bg=P["sidebar"],
                 fg=P["muted"], font=(FONT, 9), justify="left",
                 wraplength=150).pack(side="left", padx=(4, 0))
        vrow = tk.Frame(foot, bg=P["sidebar"])
        vrow.pack(fill="x", pady=(8, 0))
        tk.Label(vrow, text="v%s" % VERSION, bg=P["sidebar"], fg=P["faint"],
                 font=("Menlo", 8), anchor="w").pack(side="left")
        upd = tk.Label(vrow, text="检查更新", bg=P["sidebar"], fg=P["accent"],
                       font=(FONT, 8), anchor="w", cursor="pointinghand")
        upd.pack(side="left", padx=(8, 0))
        upd.bind("<Button-1>", lambda e: self.open_update())

        self.main = tk.Frame(self.root, bg=P["bg"])
        self.main.pack(side="left", fill="both", expand=True)

    def _build_pages(self):
        self.pages = {}
        self.pages["overview"] = tk.Frame(self.main, bg=P["bg"])
        self.pages["battery"] = tk.Frame(self.main, bg=P["bg"])
        self.pages["charge"] = tk.Frame(self.main, bg=P["bg"])
        self.pages["procs"] = tk.Frame(self.main, bg=P["bg"])
        self.pages["storage"] = tk.Frame(self.main, bg=P["bg"])
        self.pages["startup"] = tk.Frame(self.main, bg=P["bg"])
        self.pages["uninstall"] = tk.Frame(self.main, bg=P["bg"])
        self.pages["network"] = tk.Frame(self.main, bg=P["bg"])
        self.pages["trend"] = tk.Frame(self.main, bg=P["bg"])
        self._build_overview(self.pages["overview"])
        self._build_battery(self.pages["battery"])
        self._build_charge(self.pages["charge"])
        self._build_procs(self.pages["procs"])
        self._build_storage(self.pages["storage"])
        self._build_startup(self.pages["startup"])
        self._build_uninstall(self.pages["uninstall"])
        self._build_network(self.pages["network"])
        self._build_trend(self.pages["trend"])
        self._auto_wrap_pages()

    def _auto_wrap_pages(self):
        """把页面上固定换行宽度的文字改成跟随容器宽度——
        窗口收窄时文字自动重排，而不是被裁掉。"""
        for page in self.pages.values():
            for w in walk(page):
                if isinstance(w, tk.Label):
                    if getattr(w, "_no_auto_wrap", False):
                        continue
                    try:
                        base = to_int(w.cget("wraplength"))
                    except Exception:
                        continue
                    if base > 0:
                        self._bind_wrap(w, base)

    def _bind_wrap(self, label, base):
        state = {"last": base}

        def upd(_evt=None):
            try:
                pw = label.master.winfo_width()
            except Exception:
                return
            if pw < 80:
                return
            want = max(160, min(base, pw - 14))
            if abs(want - state["last"]) >= 4:
                state["last"] = want
                try:
                    label.configure(wraplength=want)
                except Exception:
                    pass

        try:
            label.master.bind("<Configure>", upd, add="+")
        except Exception:
            pass
        upd()

    def show_page(self, key):
        if key not in self.pages:
            return
        for k, f in self.pages.items():
            f.pack_forget()
            self.nav[k].set_active(k == key)
        self.pages[key].pack(fill="both", expand=True, padx=0, pady=0)
        self.page = key
        if key == "battery":
            self.refresh_battery()
        elif key == "charge":
            self.refresh_charge()
            self.update_charge_habit(force=True)
        elif key == "procs" and not self.procs_loaded:
            self.refresh_procs()
        elif key == "storage" and not self.storage_loaded:
            self.start_scan()
        elif key == "startup" and not self.startup_loaded:
            self.refresh_startup()
        elif key == "uninstall" and not self.uninstall_loaded:
            self.refresh_uninstall()
        elif key == "network" and not self.net_loaded:
            self.start_net_scan()
        elif key == "trend":
            self.draw_trend()

    def _header(self, parent, title, subtitle, actions=()):
        head = tk.Frame(parent, bg=P["bg"])
        head.pack(fill="x", padx=26, pady=(22, 14))
        left = tk.Frame(head, bg=P["bg"])
        left.pack(side="left")
        tk.Label(left, text=title, bg=P["bg"], fg=P["text"],
                 font=(FONT, 20, "bold")).pack(anchor="w")
        lbl = tk.Label(left, text=subtitle, bg=P["bg"], fg=P["muted"],
                       font=(FONT, 11), justify="left", wraplength=520)
        lbl.pack(anchor="w", pady=(3, 0))
        # header 的父容器宽度由内容决定，不能拿它算换行；跟着整页宽度走
        lbl._no_auto_wrap = True

        def _fit_head(e, lb=lbl, pg=parent):
            try:
                pw = pg.winfo_width()
            except Exception:
                return
            if pw < 260:
                return
            want = max(240, min(560, pw - 250))
            if abs(want - to_int(lb.cget("wraplength"))) >= 8:
                lb.configure(wraplength=want)
        parent.bind("<Configure>", _fit_head, add="+")
        right = tk.Frame(head, bg=P["bg"])
        right.pack(side="right")
        made = {}
        for key, text, cmd, kind in reversed(actions):
            b = RButton(right, text, cmd, kind)
            b.pack(side="right", padx=(8, 0))
            made[key] = b
        return lbl, made

    # ---------------- 体检页
    def _build_overview(self, page):
        self.ov_sub, _ = self._header(
            page, "体检概览", "正在读取硬件信息…")

        wrap = tk.Frame(page, bg=P["bg"])
        wrap.pack(fill="both", expand=True, padx=26, pady=(0, 22))

        # 状态卡
        self.status_card = tk.Frame(wrap, bg=P["red_soft"], highlightthickness=1,
                                    highlightbackground=P["red_line"], bd=0)
        self.status_card.pack(fill="x")
        inner = tk.Frame(self.status_card, bg=P["red_soft"])
        inner.pack(fill="x", padx=18, pady=16)

        ring_box = tk.Frame(inner, bg=P["red_soft"])
        ring_box.pack(side="left")
        self.ring = Ring(ring_box, 172)
        self.ring.pack()
        self.ring.draw(0, 0, P["muted"])
        self.caption = tk.Label(ring_box, text="", bg=P["red_soft"], fg=P["muted"],
                                font=(FONT, 9), justify="center")
        self.caption.pack(pady=(2, 0))

        txt = tk.Frame(inner, bg=P["red_soft"])
        txt.pack(side="left", fill="both", expand=True, padx=(20, 0))
        self.st_title = tk.Label(txt, text="正在诊断…", bg=P["red_soft"], fg=P["red"],
                                 font=(FONT, 16, "bold"), anchor="w", justify="left")
        self.st_title.pack(anchor="w")
        self.st_desc = tk.Label(txt, text="", bg=P["red_soft"], fg=P["text2"],
                                font=(FONT, 11), anchor="w", justify="left",
                                wraplength=560)
        self.st_desc.pack(anchor="w", pady=(4, 0))
        self.st_steps = tk.Label(txt, text="", bg=P["red_soft"], fg=P["text2"],
                                 font=(FONT, 11), anchor="w", justify="left",
                                 wraplength=560)
        self.st_steps.pack(anchor="w", pady=(6, 0))
        self._status_bg = [P["red_soft"], P["red_line"]]

        # 指标卡片 4 × 2
        grid = tk.Frame(wrap, bg=P["bg"])
        grid.pack(fill="x", pady=(14, 0))
        for i in range(4):
            grid.columnconfigure(i, weight=1, uniform="m")
        self.rows = {}
        spec = [("source", "供电来源", "电源 / 电池"),
                ("current", "当前电流", "正数充电，负数放电"),
                ("adapter", "充电器", "能认出说明是原装"),
                ("limit", "CPU 限速", "100% 表示未降频"),
                ("temp", "电池温度", "30℃ 上下属正常"),
                ("cycle", "循环次数", "500 次内属健康"),
                ("capacity", "满充容量", "对比出厂设计值"),
                ("cells", "电芯偏差", "越小越均衡")]
        for idx, (key, label, hint) in enumerate(spec):
            card = MetricCard(grid, label, hint)
            card.grid(row=idx // 4, column=idx % 4,
                      padx=(0 if idx % 4 == 0 else 8, 0),
                      pady=(0 if idx < 4 else 8, 0), sticky="nsew")
            self.rows[key] = card

        # 操作栏：第一层只放两件主要的事，其余收进下面的工具条
        bar = tk.Frame(wrap, bg=P["bg"])
        bar.pack(fill="x", pady=(16, 0))
        top = tk.Frame(bar, bg=P["bg"])
        top.pack(fill="x")
        RButton(top, "一键优化", self.one_click_optimize, "primary",
                height=34, size=12).pack(side="left")
        self.btn_monitor = RButton(top, "开始记录", self.toggle_monitor, "secondary",
                                   height=34, size=12)
        self.btn_monitor.pack(side="left", padx=8)
        self.status = tk.Label(top, text="", bg=P["bg"], fg=P["faint"], font=(FONT, 10))
        self.status.pack(side="right")

        tools = tk.Frame(bar, bg=P["bg"])
        tools.pack(fill="x", pady=(8, 0))
        for text, cmd in (("刷新", self.refresh),
                          ("复制报告", self.copy_report),
                          ("导出 PDF", self.export_pdf),
                          ("悬浮小窗", self.toggle_floatwin),
                          ("保养提醒", self.maintenance_dialog),
                          ("电池详情", lambda: self.show_page("battery")),
                          ("打开日志", self.open_logs)):
            RButton(tools, text, cmd, "ghost", size=9, height=28,
                    padx=11).pack(side="left", padx=(0, 6))

        # 最近事件
        ev = Card(wrap, pad=0)
        ev.pack(fill="both", expand=True, pady=(14, 0))
        head = tk.Frame(ev, bg=P["card"])
        head.pack(fill="x", padx=16, pady=(12, 6))
        tk.Label(head, text="最近事件", bg=P["card"], fg=P["text"],
                 font=(FONT, 12, "bold")).pack(side="left")
        self.ev_count = tk.Label(head, text="", bg=P["card"], fg=P["faint"],
                                 font=(FONT, 10))
        self.ev_count.pack(side="right")
        self.ev_box = tk.Frame(ev, bg=P["card"])
        self.ev_box.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        self._render_events()

    def _render_events(self):
        for w in self.ev_box.winfo_children():
            w.destroy()
        if not self.events:
            tk.Label(self.ev_box, text="暂无事件。点击「开始记录」后，我会把每一次异常都记在这里。",
                     bg=P["card"], fg=P["faint"], font=(FONT, 11),
                     anchor="w", justify="left", wraplength=680).pack(fill="x", pady=4)
            self.ev_count.configure(text="")
            return
        for ts, text, level in self.events[-4:]:
            row = tk.Frame(self.ev_box, bg=P["card"])
            row.pack(fill="x", pady=1)
            dot = {"red": P["red"], "amber": P["amber"], "green": P["green"],
                   "info": P["faint"]}.get(level, P["faint"])
            tk.Label(row, text="●", bg=P["card"], fg=dot,
                     font=(FONT, 8)).pack(side="left", padx=(0, 6))
            tk.Label(row, text=ts, bg=P["card"], fg=P["faint"],
                     font=("Menlo", 9)).pack(side="left")
            tk.Label(row, text=text, bg=P["card"], fg=P["text2"],
                     font=(FONT, 11), anchor="w", justify="left").pack(
                side="left", padx=(8, 0))
        self.ev_count.configure(text="共 %d 条" % len(self.events))

    def _set_status_card(self, level, title, desc, steps, b):
        soft, line, fg = {
            "red": (P["red_soft"], P["red_line"], P["red"]),
            "amber": (P["amber_soft"], P["amber_line"], P["amber"]),
            "green": (P["green_soft"], P["green_line"], P["green"]),
        }[level]
        self.status_card.configure(bg=soft, highlightbackground=line)
        recolor(self.status_card, soft,
                only=(self._status_bg[0], P["card"]))
        self._status_bg = [soft, line]

        self.st_title.configure(text=title, fg=fg)
        self.st_desc.configure(text=desc)
        if steps:
            self.st_steps.configure(
                text="\n".join("· " + s for s in steps[:3]), fg=P["text2"])
        else:
            self.st_steps.configure(text="")
        self.ring.draw(b.pct, b.health, fg)
        self.caption.configure(text="满充 %d mAh · 设计 %d mAh" % (b.maxcap, b.design),
                               fg=P["muted"])

    # 兼容旧字段（自测脚本使用）
    @property
    def banner_text(self):
        return self.st_title

    def refresh(self):
        if self._after_id:
            try:
                self.root.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

        b = Battery.read()
        if not b.ok:
            self.st_title.configure(text="读不到电池信息")
            self.st_desc.configure(text="这台机器可能不是笔记本，或系统接口暂时不可用。")
            self._after_id = self.root.after(4000, self.refresh)
            return

        self.battery = b
        level, title, desc, steps = b.explain()
        self._set_status_card(level, title, desc, steps, b)

        self.rows["source"].set(
            b.source + (" · 充电中" if b.charging == "Yes" else ""),
            P["green"] if b.on_ac else P["amber"],
            "正在用%s供电" % ("电源" if b.on_ac else "电池"))
        self.rows["current"].set(
            "%+d mA" % b.ma,
            P["red"] if (b.on_ac and b.ma < -300) else P["text"],
            "插电却在放电" if (b.on_ac and b.ma < -300) else "正常范围")
        self.rows["adapter"].set(
            "无法识别" if b.adapter == "0" else ("ID %s" % b.adapter if b.adapter != "na" else "未接电源"),
            P["red"] if b.adapter == "0" else P["text"],
            "非原装或接头损坏" if b.adapter == "0" else "已正常识别")
        ok_limit = b.limit is None or b.limit >= 80
        self.rows["limit"].set(
            "100% 正常" if ok_limit else "%d%% 已降频" % b.limit,
            P["text"] if ok_limit else P["amber"],
            "供电不足会触发降频" if not ok_limit else "性能未受限")
        self.rows["temp"].set("%.1f ℃" % b.temp_c,
                              P["red"] if b.temp_c > 45 else P["text"],
                              "偏高，注意散热" if b.temp_c > 45 else "散热正常")
        self.rows["cycle"].set("%d 次" % b.cycle, None,
                               "500 次内属健康" if b.cycle < 500 else "已超设计寿命")
        self.rows["capacity"].set(
            "%d mAh" % b.maxcap, None,
            ("设计 %d · 电芯实测 %d" % (b.design, b.qmax_avg)) if b.qmax_avg
            else ("出厂设计 %d mAh" % b.design))
        self.rows["cells"].set("%d mV" % b.imbalance if b.cells else "--",
                               P["red"] if b.imbalance > 150 else
                               (P["amber"] if b.imbalance > 50 else P["text"]),
                               "正常应小于 50 mV")
        self.ov_sub.configure(
            text="全程只读 · 每 4 秒自动刷新 · 数据来自系统 SMC")
        self.status.configure(text="更新于 " + time.strftime("%H:%M:%S"))
        self._care_check(b)
        if getattr(self, "page", "") == "charge":
            self.refresh_charge(b)

        if self.monitoring:
            self.monitor_sample(b)
            self._after_id = self.root.after(5000, self.refresh)
        else:
            self._after_id = self.root.after(4000, self.refresh)

    def add_event(self, text, level="info"):
        self.events.append((time.strftime("%H:%M:%S"), text, level))
        self.events = self.events[-60:]
        if hasattr(self, "ev_box"):
            self._render_events()

    def _autostart_mode(self):
        """登录自启时不要弹一个大窗口吓人：收进悬浮小窗，继续在后台采样"""
        try:
            self.toggle_floatwin()
            self.root.iconify()
            self.add_event("开机自启：已转入后台监控（右上角小窗）。", "info")
        except Exception:
            pass

    def _probe(self):
        """支持排查用探针：在 ~/Library/Logs/PowerWatch/.probe 存在时，
        把关键读取能力写进 app.log（沙箱里跑不出来的命令，要在真实环境验）"""
        out = []
        rows, err = read_processes()
        out.append("probe.ps=%s" % ("ok %d" % len(rows) if rows else "fail %s" % err))
        erows, eerr, emeta = read_energy()
        out.append("probe.top_energy=%s" % (
            "ok %d total=%.0f" % (len(erows), emeta.get("total", 0)) if erows
            else "fail %s" % eerr))
        b = Battery.read()
        out.append("probe.battery=ok volt=%d qmax=%s health=%d" %
                   (b.volt, b.qmax, b.health))
        try:
            from tkinter import font as _f
            out.append("probe.font=%s" % _f.families()[:1])
        except Exception:
            pass
        try:
            with open(APPLOG, "a", encoding="utf-8") as f:
                f.write("%s PROBE %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"),
                                            " | ".join(out)))
        except Exception:
            pass

    def log_startup(self):
        try:
            procs, err = read_processes()
            state = "可用" if procs is not None else "不可用(%s)" % err
            with open(APPLOG, "a", encoding="utf-8") as f:
                f.write("%s 启动 进程列表%s\n"
                        % (time.strftime("%Y-%m-%d %H:%M:%S"), state))
        except Exception:
            pass

    CSV_MAX_BYTES = 40 * 1024 * 1024   # 采样文件上限，超过后只保留最近一段
    CSV_KEEP_ROWS = 200000             # 约合 11 天（5 秒一条）

    def _rotate_csv(self):
        """长期运行时把过大的采样日志裁到最近若干行，避免无限增长。"""
        now = time.time()
        if now - getattr(self, "_last_rot", 0) < 6 * 3600:
            return
        self._last_rot = now
        try:
            if not os.path.exists(CSV) or os.path.getsize(CSV) <= self.CSV_MAX_BYTES:
                return
            with open(CSV, encoding="utf-8", errors="replace") as f:
                lines = f.read().splitlines()
            if len(lines) < self.CSV_KEEP_ROWS + 2:
                return
            head = lines[0]
            tail = lines[-self.CSV_KEEP_ROWS:]
            tmp = CSV + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(head + "\n")
                f.write("\n".join(tail) + "\n")
            os.replace(tmp, CSV)
            self.add_event("采样日志超过上限，已归档并保留最近 %d 条（约 11 天）"
                           % len(tail), "info")
        except Exception:
            pass

    def monitor_sample(self, b):
        self._rotate_csv()
        new_file = not os.path.exists(CSV)
        note = []
        if b.on_ac and b.ma < -300:
            note.append("AC_BUT_DISCHARGING")
        if b.limit is not None and b.limit < 80:
            note.append("CPU_THROTTLED_%d" % b.limit)
        try:
            with open(CSV, "a", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                if new_file:
                    f.write(CSV_HEADER + "\n")
                w.writerow([int(time.time()), time.strftime("%Y-%m-%d %H:%M:%S"),
                            "AC" if b.on_ac else "BAT", b.pct, b.cur,
                            b.maxcap, b.design, b.health, b.ma, b.volt, b.temp_c,
                            b.cycle, b.adapter,
                            b.limit if b.limit is not None else "na",
                            b.charging, "|".join(note)])
            with open(BEAT, "w") as f:
                f.write(str(int(time.time())))
            if note:
                self.add_event("异常：%s（电量 %d%%，电流 %d mA）"
                               % ("|".join(note), b.pct, b.ma), "amber")
        except Exception as e:
            self.add_event("写入日志失败：%s" % e, "red")

    def check_previous_shutdown(self):
        if not os.path.exists(BEAT):
            return
        try:
            last = int(open(BEAT).read().strip() or 0)
        except Exception:
            return
        gap = int(time.time()) - last
        if gap <= 120:
            return
        clean = 0
        if os.path.exists(CLEAN):
            try:
                clean = int(open(CLEAN).read().strip() or 0)
            except Exception:
                clean = 0
        if clean >= last:
            self.add_event("上次会话正常结束，未记为断电。", "info")
            return

        when = time.strftime("%m-%d %H:%M:%S", time.localtime(last))
        self.add_event("上次异常断电，记录停在 %s（中断约 %d 分钟）"
                       % (when, gap // 60), "red")
        notify("电池医生 · 检测到异常断电",
               "上次记录停在 %s，中断约 %d 分钟" % (when, gap // 60))
        try:
            with open(INC, "a", encoding="utf-8") as f:
                f.write("=== 异常断电 %s（中断 %d 秒）===\n"
                        % (time.strftime("%Y-%m-%d %H:%M:%S"), gap))
                if os.path.exists(CSV):
                    lines = open(CSV, encoding="utf-8").read().strip().splitlines()[-12:]
                    f.write("\n".join(lines) + "\n\n")
        except Exception:
            pass

    def mark_clean_stop(self):
        try:
            with open(CLEAN, "w") as f:
                f.write(str(int(time.time())))
        except Exception:
            pass

    def toggle_monitor(self):
        self.monitoring = not self.monitoring
        if self.monitoring:
            self.btn_monitor.set_text("停止记录")
            self.add_event("开始记录，每 5 秒采样一次。", "green")
        else:
            self.btn_monitor.set_text("开始记录")
            self.mark_clean_stop()
            self.add_event("已停止记录。", "info")

    def on_close(self):
        self.mark_clean_stop()
        self.root.destroy()

    def build_report_text(self):
        """生成可复制/可保存的诊断报告"""
        b = getattr(self, "battery", None) or Battery.read()
        level, title, desc, steps = b.explain()
        lines = [
            "电池医生诊断报告",
            "时间：%s" % time.strftime("%Y-%m-%d %H:%M:%S"),
            "系统：macOS %s" % run_cmd(["/usr/bin/sw_vers", "-productVersion"]).strip(),
            "",
            "【结论】%s" % title,
            "%s" % desc,
            "",
            "【关键数据】",
            "  供电来源：%s（充电中：%s）" % (b.source, b.charging),
            "  电量：%d%%    健康度：%d%%" % (b.pct, b.health),
            "  电流：%+d mA    电压：%d mV" % (b.ma, b.volt),
            "  适配器 ID：%s" % b.adapter,
            "  CPU 限速：%s" % (("%d%%" % b.limit) if b.limit is not None else "未知"),
            "  温度：%.1f ℃    循环次数：%d" % (b.temp_c, b.cycle),
            "  满充 / 设计容量：%d / %d mAh" % (b.maxcap, b.design),
            "  电芯电压：%s    偏差：%d mV" % (", ".join(map(str, b.cells)), b.imbalance),
        ]
        d = getattr(self, "net_info", None)
        if d:
            lines += [
                "",
                "【网络】",
                "  连接：%s（%s）   IP：%s   网关：%s"
                % (d.get("ssid") or "—", d.get("service") or "—",
                   d.get("ip") or "—", d.get("router") or "—"),
                "  DNS：%s" % ("、".join(d.get("dns") or []) or "路由器默认"),
                "  系统代理：%s" % (
                    "、".join("%s %s:%d" % (k, h, p) for k, h, p in d.get("proxy_list") or [])
                    or "未启用"),
            ]
        lines += [
            "",
            "【建议】",
        ] + ["  %d. %s" % (i + 1, s) for i, s in enumerate(steps)]
        if level in ("amber", "red"):
            lines += ["", "说明：软件层能改善的部分已处理；涉及硬件的问题需要更换配件才能根治。"]
        return "\n".join(lines)

    def copy_report(self):
        text = self.build_report_text()
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.add_event("诊断报告已复制到剪贴板。", "green")

    def one_click_optimize(self):
        dlg = getattr(self, "_optdlg", None)
        try:
            if dlg is not None and dlg.winfo_exists():
                dlg.lift()
                dlg.focus_force()
                return
        except Exception:
            pass
        self._optdlg = OptimizeDialog(self)

    def optimize(self):
        os.makedirs(BACKUP, exist_ok=True)
        moved = []
        agents = os.path.expanduser("~/Library/LaunchAgents")
        for name in USER_AGENTS:
            src = os.path.join(agents, name)
            if os.path.exists(src):
                try:
                    shutil.move(src, os.path.join(BACKUP, name))
                    moved.append(name)
                except Exception:
                    pass
        if moved:
            self.add_event("已停用 %d 个后台启动项。" % len(moved), "green")
        else:
            self.add_event("没有需要停用的启动项，或此前已优化过。", "info")
        self.refresh_startup()
        messagebox.showinfo("一键优化",
                            "已停用 %d 个后台启动项，注销后彻底生效。\n"
                            "系统级项目请到「启动项目」页查看需要管理员权限的命令。\n"
                            "所有文件都保留在 ~/Library/.batterydoctor-backup，可随时恢复。"
                            % len(moved))

    def open_logs(self):
        subprocess.run(["/usr/bin/open", BASE])

    # ---------------- 进程页
    # ---------------- 电池详情页（对标 coconutBattery / HWiNFO 的深度读数）
    def _build_battery(self, page):
        self.batt_sub, self.batt_btns = self._header(
            page, "电池详情",
            "电芯级读数，加上三种容量口径的对照。",
            [("cal", "校准向导", self.calibration_dialog, "primary"),
             ("load", "负载压降", self.load_test_dialog, "secondary"),
             ("wo", "导出维修单", self.export_workorder, "ghost")])

        wrap = tk.Frame(page, bg=P["bg"])
        wrap.pack(fill="both", expand=True, padx=26, pady=(0, 20))

        lower = tk.Frame(wrap, bg=P["bg"])
        lower.pack(fill="both", expand=True)

        right = tk.Frame(lower, bg=P["bg"], width=306)
        right.pack(side="right", fill="y", padx=(12, 0))
        right.pack_propagate(False)

        left = tk.Frame(lower, bg=P["bg"])
        left.pack(side="left", fill="both", expand=True)

        # ---- 左：电池身份
        ident = Card(left, pad=14)
        ident.pack(fill="x")
        tk.Label(ident.body, text="电池身份", bg=P["card"], fg=P["text"],
                 font=(FONT, 11, "bold")).pack(anchor="w")
        grid = tk.Frame(ident.body, bg=P["card"])
        grid.pack(fill="x", pady=(8, 0))
        for c in range(3):
            grid.columnconfigure(c, weight=1, uniform="id")
        self.ident = {}
        for i, (key, label) in enumerate([("model", "型号"), ("serial", "序列号"),
                                          ("vendor", "电芯厂商"), ("cycle", "循环次数"),
                                          ("temp", "温度"), ("adapter", "充电器")]):
            cell = tk.Frame(grid, bg=P["card"])
            cell.grid(row=i // 3, column=i % 3, sticky="w",
                      pady=(0 if i < 3 else 8, 0))
            tk.Label(cell, text=label, bg=P["card"], fg=P["faint"],
                     font=(FONT, 9)).pack(anchor="w")
            v = tk.Label(cell, text="—", bg=P["card"], fg=P["text"],
                         font=(FONT, 11, "bold"))
            v.pack(anchor="w")
            self.ident[key] = v

        # ---- 左：电芯明细
        cells_card = Card(left, pad=14)
        cells_card.pack(fill="x", pady=(10, 0))
        chead = tk.Frame(cells_card.body, bg=P["card"])
        chead.pack(fill="x")
        tk.Label(chead, text="电芯明细", bg=P["card"], fg=P["text"],
                 font=(FONT, 11, "bold")).pack(side="left")
        self.cell_chip = Chip(chead, "--", fg=P["muted"])
        self.cell_chip.pack(side="right")
        self.cell_cv = tk.Canvas(cells_card.body, height=104, bg=P["card"],
                                 highlightthickness=0)
        self.cell_cv.pack(fill="x", pady=(6, 0))
        self.cell_note = tk.Label(cells_card.body, text="", bg=P["card"],
                                  fg=P["muted"], font=(FONT, 9), anchor="w",
                                  justify="left", wraplength=430)
        self.cell_note.pack(fill="x")
        # 窗口尺寸变化后重画，否则第一次渲染用的是宽度还没算出来的默认值
        self.cell_cv.bind("<Configure>", self._on_cells_resize)

        # ---- 左：结论（容量口径矛盾）
        self.verdict_card = Card(left, pad=14)
        self.verdict_card.pack(fill="both", expand=True, pady=(10, 0))
        self.vd_title = tk.Label(self.verdict_card.body, text="正在读电池…",
                                 bg=P["card"], fg=P["text"], font=(FONT, 12, "bold"),
                                 anchor="w", justify="left", wraplength=430)
        self.vd_title.pack(fill="x")
        self.vd_text = tk.Label(self.verdict_card.body, text="", bg=P["card"],
                                fg=P["text2"], font=(FONT, 10), anchor="w",
                                justify="left", wraplength=430)
        self.vd_text.pack(fill="x", pady=(6, 0))
        self.vd_steps = tk.Label(self.verdict_card.body, text="", bg=P["card"],
                                 fg=P["text2"], font=(FONT, 10), anchor="w",
                                 justify="left", wraplength=430)
        self.vd_steps.pack(fill="x", pady=(6, 0))

        # ---- 右：三种容量口径
        cap = Card(right, pad=14)
        cap.pack(fill="x")
        tk.Label(cap.body, text="容量对照", bg=P["card"], fg=P["text"],
                 font=(FONT, 11, "bold")).pack(anchor="w")
        self.cap_rows = {}
        for key, label, color in (("design", "出厂设计", P["faint"]),
                                  ("qmax", "电芯学到", P["blue"]),
                                  ("sys", "系统认的", P["accent"])):
            row = tk.Frame(cap.body, bg=P["card"])
            row.pack(fill="x", pady=(8, 0))
            top = tk.Frame(row, bg=P["card"])
            top.pack(fill="x")
            tk.Label(top, text=label, bg=P["card"], fg=P["muted"],
                     font=(FONT, 9)).pack(side="left")
            val = tk.Label(top, text="—", bg=P["card"], fg=P["text"],
                           font=(MONO, 10, "bold"))
            val.pack(side="right")
            bar = tk.Canvas(row, height=7, bg=P["card"], highlightthickness=0)
            bar.pack(fill="x", pady=(3, 0))
            self.cap_rows[key] = (val, bar, color)
        self.cap_note = tk.Label(cap.body, text="", bg=P["card"], fg=P["faint"],
                                 font=(FONT, 9), anchor="w", justify="left",
                                 wraplength=250)
        self.cap_note.pack(fill="x", pady=(10, 0))

        # ---- 右：功率与续航
        pw = Card(right, pad=14)
        pw.pack(fill="x", pady=(10, 0))
        tk.Label(pw.body, text="功率与续航", bg=P["card"], fg=P["text"],
                 font=(FONT, 11, "bold")).pack(anchor="w")
        self.pw = {}
        for key, label in (("watts", "当前功率"), ("adapter", "充电器标称"),
                           ("runtime", "剩余时间")):
            row = tk.Frame(pw.body, bg=P["card"])
            row.pack(fill="x", pady=(7, 0))
            tk.Label(row, text=label, bg=P["card"], fg=P["muted"],
                     font=(FONT, 9)).pack(side="left")
            v = tk.Label(row, text="—", bg=P["card"], fg=P["text"],
                         font=(MONO, 10))
            v.pack(side="right")
            self.pw[key] = v
        self.pw_note = tk.Label(pw.body, text="", bg=P["card"], fg=P["faint"],
                                font=(FONT, 9), anchor="w", justify="left",
                                wraplength=250)
        self.pw_note.pack(fill="x", pady=(8, 0))

        # ---- 右：使用强度（来自历史采样）
        use = Card(right, pad=14)
        use.pack(fill="both", expand=True, pady=(10, 0))
        tk.Label(use.body, text="使用强度", bg=P["card"], fg=P["text"],
                 font=(FONT, 11, "bold")).pack(anchor="w")
        self.use_note = tk.Label(use.body, text="还没有采样数据", bg=P["card"],
                                 fg=P["faint"], font=(FONT, 9), anchor="w",
                                 justify="left", wraplength=250)
        self.use_note.pack(fill="x", pady=(8, 0))

    def _on_cells_resize(self, _evt=None):
        b = getattr(self, "battery", None)
        if b is not None and b.ok:
            self._draw_cells(b)

    def _draw_cells(self, b):
        c = self.cell_cv
        c.delete("all")
        W = c.winfo_width()
        if W < 60:
            W = 430
        c.configure(scrollregion=(0, 0, W, 104))
        if not b.cells:
            c.create_text(0, 34, anchor="w", text="这台机器的电池没有提供逐节电压。",
                          fill=P["faint"], font=(FONT, 9))
            self.cell_chip.set("未提供", fg=P["muted"])
            self.cell_note.configure(text="")
            return
        lo, hi = 3900, 4320
        bw = max(80, W - 168)
        for i, mv in enumerate(b.cells):
            y = 8 + i * 33
            c.create_text(0, y + 8, anchor="w", text="第 %d 节" % (i + 1),
                          fill=P["muted"], font=(FONT, 9))
            c.create_text(56, y + 8, anchor="w", text="%d mV" % mv,
                          fill=P["text"], font=(MONO, 10, "bold"))
            diff = mv - min(b.cells)
            ratio = (mv - lo) / float(hi - lo)
            ratio = max(0.02, min(1.0, ratio))
            round_rect(c, 124, y + 3, 124 + bw, y + 13, 5, fill=P["track"], outline="")
            col = P["accent"] if diff == 0 else (P["amber"] if diff > 40 else P["blue"])
            round_rect(c, 124, y + 3, 124 + int(bw * ratio), y + 13, 5, fill=col, outline="")
            if diff:
                c.create_text(124 + bw + 8, y + 8, anchor="w", text="+%d" % diff,
                              fill=P["amber"] if diff > 40 else P["faint"],
                              font=(MONO, 9))
        lvl = P["red"] if b.imbalance > 150 else (P["amber"] if b.imbalance > 50 else P["accent"])
        self.cell_chip.set("偏差 %d mV" % b.imbalance, fg=lvl,
                           bg=P["card2"], dot=lvl)
        if b.imbalance > 150:
            note = ("三节电芯差得比较多。电池的短板取决于最弱那节，"
                    "在大电流时最容易先掉到保护电压，表现就是突然关机。")
        elif b.imbalance > 50:
            note = "有轻微不均衡，多数老电池都会这样，暂时不影响使用。"
        else:
            note = "三节电压很接近，说明电芯之间还算同步。"
        self.cell_note.configure(text=note)

    def _draw_cap_bars(self, b):
        vals = {"design": b.design, "qmax": b.qmax_avg, "sys": b.maxcap}
        top = max(vals.values()) if max(vals.values()) else 1
        for key, (val, bar, color) in self.cap_rows.items():
            v = vals[key]
            val.configure(text=("%d mAh" % v) if v else "—",
                          fg=P["text"] if v else P["faint"])
            bar.delete("all")
            W = bar.winfo_width()
            if W < 40:
                W = 250
            round_rect(bar, 0, 0, W, 6, 3, fill=P["track"], outline="")
            if v:
                w = max(3, int(W * v / float(top)))
                round_rect(bar, 0, 0, w, 6, 3, fill=color, outline="")
        d, q, s = vals["design"], vals["qmax"], vals["sys"]
        if d and q and s and q > 0:
            self.cap_note.configure(
                text="按电芯读数算是 %d%%，按系统读数只有 %d%%。"
                     % (int(q * 100 / d), int(s * 100 / d)))

    def refresh_battery(self):
        b = Battery.read()
        if not b.ok:
            self.vd_title.configure(text="读不到电池信息")
            self.vd_text.configure(text="这台机器可能不是笔记本，或系统接口暂时不可用。")
            return
        self.battery = b
        self.ident["model"].configure(text=b.name or "—")
        self.ident["serial"].configure(text=(b.serial or "—")[-10:])
        self.ident["vendor"].configure(text=b.vendor or "—")
        self.ident["cycle"].configure(text="%d 次" % b.cycle,
                                      fg=P["amber"] if b.cycle > 700 else P["text"])
        self.ident["temp"].configure(text="%.1f ℃" % b.temp_c,
                                     fg=P["red"] if b.temp_c > 45 else P["text"])
        self.ident["adapter"].configure(
            text=("未识别" if b.adapter == "0" else
                  ("%s W" % b.adapter_w if b.adapter_w else "ID %s" % b.adapter)),
            fg=P["red"] if b.adapter == "0" else P["text"])
        self._draw_cells(b)
        self._draw_cap_bars(b)

        level, title, desc, steps = capacity_verdict(b)
        soft, line, fg = {
            "red": (P["red_soft"], P["red_line"], P["red"]),
            "amber": (P["amber_soft"], P["amber_line"], P["amber"]),
            "green": (P["green_soft"], P["green_line"], P["green"]),
            "info": (P["card"], P["line"], P["text"]),
        }[level]
        self.verdict_card.configure(bg=soft, highlightbackground=line)
        recolor(self.verdict_card, soft, only=(P["card"],))
        self.vd_title.configure(text=title, fg=fg, bg=soft)
        self.vd_text.configure(text=desc, bg=soft)
        self.vd_steps.configure(
            text="\n".join("· " + s for s in steps), bg=soft)

        if b.watts:
            self.pw["watts"].configure(
                text="%.1f W" % b.watts,
                fg=P["accent"] if b.charging == "Yes" else P["text"])
        else:
            self.pw["watts"].configure(text="—")
        self.pw["adapter"].configure(text=("%d W" % b.adapter_w) if b.adapter_w else "—")
        rmin = b.runtime_min
        if rmin:
            txt = ("%d 小时 %d 分" % (rmin // 60, rmin % 60)) if rmin >= 60 else ("%d 分钟" % rmin)
            self.pw["runtime"].configure(text=txt)
            self.pw_note.configure(
                text=("按当前充电电流估算充满还要多久" if b.charging == "Yes"
                      else "按当前放电电流估算，实际取决于你在做什么"))
        else:
            self.pw["runtime"].configure(text="—")
            self.pw_note.configure(text="接电且电池已满时没有剩余时间可算")

        st = drain_stats()
        if st.get("samples"):
            self.use_note.configure(
                text="采样 %d 条 · 覆盖 %.1f 天\n电池供电平均 %d mA（峰值 %d mA）\n"
                     "插电却放电的采样 %d 条 · CPU 降频采样 %d 条\n"
                     "非正常断电 %d 次"
                     % (st["samples"], st["days"], st["avg_ma"], st["max_ma"],
                        st["ac_discharge"], st["throttled"], len(incident_list())),
                fg=P["text2"])
        else:
            self.use_note.configure(text="还没有采样数据。回「体检概览」点「开始记录」。")

    def export_workorder(self):
        b = getattr(self, "battery", None) or Battery.read()
        text = workorder_text(b)
        name = "电池医生-送修单-%s.pdf" % time.strftime("%Y%m%d-%H%M")
        try:
            from tkinter import filedialog
            path = filedialog.asksaveasfilename(
                title="导出送修单", initialfile=name,
                initialdir=os.path.expanduser("~/Desktop"),
                defaultextension=".pdf", filetypes=[("PDF 文件", "*.pdf")],
                parent=self.root)
        except Exception:
            path = os.path.join(os.path.expanduser("~/Desktop"), name)
        if not path:
            return
        try:
            text_to_pdf(text, path)
            self.add_event("送修单已导出：%s" % os.path.basename(path), "green")
            notify("电池医生", "送修单已导出到桌面，可直接给维修店看")
        except Exception as e:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            messagebox.showwarning("导出失败",
                                   "PDF 生成失败：%s\n\n内容已复制到剪贴板，可以粘贴到别处。" % e)

    # ---------------- 校准向导（对标 AlDente 的保养闭环，但不写 SMC）
    def calibration_dialog(self):
        dlg = getattr(self, "_cal_dlg", None)
        try:
            if dlg is not None and dlg.winfo_exists():
                dlg.lift()
                return
        except Exception:
            pass
        b = getattr(self, "battery", None) or Battery.read()
        st = _care_state()
        before = st.get("cal_before") or {}
        last = st.get("cal_last") or ""

        dlg = tk.Toplevel(self.root)
        self._cal_dlg = dlg
        dlg.title("校准向导")
        dlg.configure(bg=P["card"])
        dlg.transient(self.root)
        dlg.resizable(False, False)
        dlg.grab_set()

        pad = tk.Frame(dlg, bg=P["card"])
        pad.pack(fill="both", expand=True, padx=24, pady=20)
        tk.Label(pad, text="电池校准向导", bg=P["card"], fg=P["text"],
                 font=(FONT, 15, "bold")).pack(anchor="w")
        tk.Label(pad, text="不是修复电芯，而是让「电量计」重新认识这块电池。免费，但要花半天。",
                 bg=P["card"], fg=P["muted"], font=(FONT, 10), justify="left",
                 wraplength=430).pack(anchor="w", pady=(2, 10))

        status = tk.Frame(pad, bg=P["card2"], highlightthickness=1,
                          highlightbackground=P["line2"])
        status.pack(fill="x", pady=(0, 12))
        self.cal_status = tk.Label(
            status, bg=P["card2"], fg=P["text2"], font=(FONT, 10),
            justify="left", anchor="w", wraplength=420, padx=12, pady=10,
            text=("上次校准：%s\n校准前记录的系统容量：%s"
                  % (last or "没有记录",
                     ("%d mAh" % before["maxcap"]) if before.get("maxcap") else "没有记录")))
        self.cal_status.pack(fill="x")

        steps = [("把电用到 10% 以下", "正常用就行，不必等到自动关机。低电量时电量计才愿意重新学习。"),
                 ("关机后连续充电 8 小时", "中途不要开机。这一晚是让电池从「空」走到「满」，把满点记下来。"),
                 ("充满后再静置 2 小时", "插着电放着，不进系统。让电压彻底稳定。"),
                 ("回来点「复测」看结果", "容量如果跳到 8000 mAh 以上，说明原来只是记错了。")]
        self.cal_checks = []
        for i, (t, d) in enumerate(steps, 1):
            row = tk.Frame(pad, bg=P["card"])
            row.pack(fill="x", pady=(0, 9))
            ck = CheckBox(row, on=False, command=lambda v, i=i: None)
            ck.pack(side="left", anchor="n", pady=(2, 0))
            self.cal_checks.append(ck)
            txt = tk.Frame(row, bg=P["card"])
            txt.pack(side="left", fill="x", expand=True, padx=(8, 0))
            tk.Label(txt, text="%d. %s" % (i, t), bg=P["card"], fg=P["text"],
                     font=(FONT, 10, "bold"), anchor="w").pack(fill="x")
            tk.Label(txt, text=d, bg=P["card"], fg=P["muted"], font=(FONT, 9),
                     anchor="w", justify="left", wraplength=380).pack(fill="x")

        btns = tk.Frame(pad, bg=P["card"])
        btns.pack(fill="x", pady=(8, 0))
        RButton(btns, "记录当前容量，开始校准", self.cal_begin, "primary",
                size=11).pack(side="left")
        RButton(btns, "我已完成，复测", self.cal_finish, "secondary",
                size=11).pack(side="left", padx=8)
        RButton(btns, "关闭", dlg.destroy, "ghost", size=11).pack(side="right")

        dlg.update_idletasks()
        w, h = 486, 520
        x = self.root.winfo_rootx() + (self.root.winfo_width() - w) // 2
        y = self.root.winfo_rooty() + max(16, (self.root.winfo_height() - h) // 3)
        dlg.geometry("%dx%d+%d+%d" % (w, h, x, y))

    def cal_begin(self):
        b = Battery.read()
        if not b.ok:
            messagebox.showwarning("校准", "现在读不到电池信息，稍后再试。")
            return
        st = _care_state()
        st["cal_before"] = {"maxcap": b.maxcap, "ts": time.strftime("%Y-%m-%d %H:%M"),
                            "qmax": b.qmax_avg, "pct": b.pct}
        _care_save(st)
        self.cal_status.configure(
            text="已记录校准前容量 %d mAh（%s）。\n按上面四步做完，回来点「我已完成，复测」。"
                 % (b.maxcap, st["cal_before"]["ts"]))
        self.add_event("已记录校准前容量 %d mAh" % b.maxcap, "info")

    def cal_finish(self):
        b = Battery.read()
        if not b.ok:
            messagebox.showwarning("校准", "现在读不到电池信息，稍后再试。")
            return
        st = _care_state()
        before = st.get("cal_before") or {}
        old = before.get("maxcap") or 0
        gain = b.maxcap - old if old else 0
        st["cal_last"] = time.strftime("%Y-%m-%d")
        st.pop("cal_before", None)
        _care_save(st)
        self.refresh_battery()
        if not old:
            self.cal_status.configure(text="这次没有校准前的记录，已按 %d mAh 存为当前值。" % b.maxcap)
            return
        if gain >= 300:
            msg = ("容量从 %d mAh 变成 %d mAh，回升 %d mAh。\n"
                   "这说明之前是电量计记错了，不用换电池。") % (old, b.maxcap, gain)
            lvl = "green"
        elif gain > -300:
            msg = ("容量 %d → %d mAh，基本没变。\n"
                   "校准没能把容量找回来，说明电芯确实到了这个状态。") % (old, b.maxcap)
            lvl = "amber"
        else:
            msg = ("容量 %d → %d mAh，反而降了 %d mAh。\n"
                   "电量计重新学习后给出了更悲观的数字，按硬件老化处理。"
                   % (old, b.maxcap, -gain))
            lvl = "red"
        self.cal_status.configure(text=msg)
        self.add_event("校准复测：%d → %d mAh" % (old, b.maxcap), lvl if lvl != "amber" else "info")
        messagebox.showinfo("校准结果", msg)

    # ---------------- 负载压降测试：给「一用就关机」做实证
    def load_test_dialog(self):
        dlg = getattr(self, "_load_dlg", None)
        try:
            if dlg is not None and dlg.winfo_exists():
                dlg.lift()
                return
        except Exception:
            pass
        self._load_dlg = LoadTestDialog(self)

    def _build_procs(self, page):
        self.proc_sub, self.proc_btns = self._header(
            page, "进程负载",
            "按占用排序，看看是谁在偷偷吃你的电和性能。",
            [("instant", "抓取瞬时占用", self.grab_instant, "secondary"),
             ("kill", "结束所选进程", self.kill_selected, "danger")])

        wrap = tk.Frame(page, bg=P["bg"])
        wrap.pack(fill="both", expand=True, padx=26, pady=(0, 22))

        # 负载概览
        self.load_card = Card(wrap, pad=14)
        self.load_card.pack(fill="x")
        lrow = tk.Frame(self.load_card.body, bg=P["card"])
        lrow.pack(fill="x")
        self.load_main = tk.Label(lrow, text="--", bg=P["card"], fg=P["text"],
                                  font=(FONT, 24, "bold"))
        self.load_main.pack(side="left")
        self.load_unit = tk.Label(lrow, text="", bg=P["card"], fg=P["muted"],
                                  font=(FONT, 11))
        self.load_unit.pack(side="left", padx=(6, 0), pady=(0, 6))
        self.load_chip = Chip(lrow, "", fg=P["muted"])
        self.load_chip.pack(side="right", pady=(4, 0))
        self.load_hint = tk.Label(self.load_card.body, text="", bg=P["card"],
                                  fg=P["faint"], font=(FONT, 10), anchor="w",
                                  justify="left", wraplength=700)
        self.load_hint.pack(fill="x", pady=(2, 0))

        # 排序口径切换（对标活动监视器的「CPU / 能耗」标签）
        self.mode_box = tk.Frame(self.load_card.body, bg=P["card"])
        self.mode_box.pack(fill="x", pady=(8, 0))
        self.mode_btns = {}
        self._render_mode_buttons()

        # 列表
        lst = Card(wrap, pad=0)
        lst.pack(fill="both", expand=True, pady=(14, 0))
        head = tk.Frame(lst, bg=P["card"])
        head.pack(fill="x", padx=(16, 14), pady=(10, 6))
        tk.Label(head, text="内存", bg=P["card"], fg=P["muted"], font=(FONT, 10),
                 width=8, anchor="e").pack(side="right")
        tk.Label(head, text="CPU", bg=P["card"], fg=P["muted"], font=(FONT, 10),
                 width=8, anchor="e").pack(side="right", padx=(0, 10))
        tk.Label(head, text="PID", bg=P["card"], fg=P["muted"], font=(FONT, 10),
                 width=8, anchor="e").pack(side="right", padx=(0, 10))
        tk.Label(head, text="进程", bg=P["card"], fg=P["muted"], font=(FONT, 10),
                 anchor="w").pack(side="left")
        tk.Frame(lst, bg=P["line2"], height=1).pack(fill="x")

        self.proc_list = RowList(lst, self._proc_row, key_of=lambda r: r[0],
                                 on_select=self._proc_selected,
                                 on_activate=lambda k: self.kill_selected())
        self.proc_list.empty = "正在读取进程列表…"
        self.proc_list.pack(fill="both", expand=True, padx=6, pady=(2, 0))
        self.proc_list.set_items([])

        self.proc_hint = tk.Label(wrap, text="", bg=P["bg"], fg=P["faint"],
                                  font=(FONT, 10), anchor="w", justify="left",
                                  wraplength=760)
        self.proc_hint.pack(fill="x", pady=(10, 0))
        self.procs_loaded = False

    MODES = (("avg", "按 CPU 平均"), ("instant", "瞬时 CPU"), ("energy", "按耗电估算"))

    def _render_mode_buttons(self):
        for w in self.mode_box.winfo_children():
            w.destroy()
        self.mode_btns = {}
        for key, label in self.MODES:
            active = (self.proc_mode == key)
            b = RButton(self.mode_box, label,
                        lambda k=key: self.set_proc_mode(k),
                        "primary" if active else "ghost", size=9, height=27)
            b.pack(side="left", padx=(0, 6))
            self.mode_btns[key] = b

    def set_proc_mode(self, key):
        if key == getattr(self, "proc_mode", "avg"):
            if key == "energy":
                self.grab_energy()
            return
        self.proc_mode = key
        self._render_mode_buttons()
        if key == "energy":
            self.grab_energy()
        elif key == "instant":
            self.grab_instant()
        else:
            self.refresh_procs()

    def grab_energy(self):
        if self._energy_thread is not None and self._energy_thread.is_alive():
            return
        self.proc_hint.configure(text="正在统计 CPU 周期数，约 3 秒…", fg=P["muted"])
        self.proc_list.empty = "正在统计…"
        self.proc_list.set_items([])

        def work():
            try:
                rows, err, meta = read_energy()
            except Exception as e:
                rows, err, meta = None, str(e), {}
            self.root.after(0, lambda: self._energy_done(rows, err, meta))

        self._energy_thread = threading.Thread(target=work, daemon=True)
        self._energy_thread.start()

    def _energy_done(self, rows, err, meta):
        if rows is None:
            self.proc_mode = "avg"
            self._render_mode_buttons()
            self.refresh_procs()
            self.proc_hint.configure(
                text="这台系统读不到 CPU 周期数（%s），已先按 CPU 占用排序。"
                     % (err or "未知原因"), fg=P["amber"])
            return
        self.procs_loaded = True
        self.proc_rows = rows
        self._render_proc_rows(rows)
        total = meta.get("total") or 0
        self.proc_hint.configure(
            text="按 CPU 周期数排序 · 周期数比「CPU 占比」更接近真实耗电，"
                 "因为不同指令的功耗不同 · 共 %d 个进程%s"
                 % (len(rows), ("，合计 %.0f M 周期/秒" % (total / 1e6)) if total else ""),
            fg=P["faint"])

    def _bar(self, parent, ratio, color, width=120, height=6, bg=None):
        c = tk.Canvas(parent, width=width, height=height + 2, bg=bg or P["card"],
                      highlightthickness=0)
        round_rect(c, 0, 1, width, height + 1, height / 2, fill=P["track"], outline="")
        w = max(2, int(width * max(0.02, min(1.0, ratio))))
        round_rect(c, 0, 1, w, height + 1, height / 2, fill=color, outline="")
        return c

    def _proc_row(self, row, item, idx):
        bg = P["card"]
        row.configure(bg=bg)
        pid, cpu, mem, rss, name, _cmd = item
        col = P["red"] if cpu > 50 else (P["amber"] if cpu > 15 else P["green"])
        tk.Label(row, text="●", bg=bg, fg=col if cpu > 1 else P["line"],
                 font=(FONT, 9)).pack(side="left", padx=(12, 8), pady=8)

        tk.Label(row, text=human(rss) if rss > 0 else "%.1f%%" % mem, bg=bg,
                 fg=P["text2"], font=(MONO, 9), width=8,
                 anchor="e").pack(side="right", padx=(0, 14))
        tk.Label(row, text="%.1f%%" % cpu, bg=bg, fg=col, font=(MONO, 9),
                 width=8, anchor="e").pack(side="right", padx=(0, 10))
        tk.Label(row, text=str(pid), bg=bg, fg=P["faint"], font=(MONO, 9),
                 width=8, anchor="e").pack(side="right", padx=(0, 10))
        nm = name if len(name) <= 34 else name[:33] + "…"
        tk.Label(row, text=nm, bg=bg, fg=P["text"], font=(FONT, 11),
                 anchor="w").pack(side="left", fill="x", expand=True)

    def refresh_procs(self):
        rows, err = read_processes()
        if rows is None:
            self.proc_list.empty = err or "无法读取进程列表"
            self.proc_list.set_items([])
            self.proc_hint.configure(
                text="系统策略禁止读取进程列表。请关闭本窗口，从访达（应用程序）里重新打开。",
                fg=P["red"])
            self.procs_loaded = False
            return
        self.procs_loaded = True
        self.proc_rows = rows
        self._render_proc_rows(rows)

    def _render_proc_rows(self, rows):
        self.proc_list.set_items(rows[:40])
        try:
            la = os.getloadavg()
            cores = os.cpu_count() or 1
            lvl = P["red"] if la[0] > cores else (P["amber"] if la[0] > cores * 0.7 else P["green"])
            self.load_main.configure(text="%.2f" % la[0], fg=lvl)
            self.load_unit.configure(text="负载（1 分钟） · %d 逻辑核" % cores)
            self.load_chip.set("%.2f / %.2f" % (la[1], la[2]),
                               fg=lvl, bg=P["card2"])
            if la[0] > cores:
                hint = ("现在的负载高于核心数，说明有程序在争抢 CPU，机器会明显变慢、发热，"
                        "也会加快耗电。点「抓取瞬时占用」看看到底是谁。")
            elif la[0] > cores * 0.7:
                hint = "负载偏高但仍在可接受范围，可能是索引、同步或更新任务在进行。"
            else:
                hint = "负载很低，CPU 处于轻松状态。"
            self.load_hint.configure(text=hint)
        except Exception:
            pass

        mode = "瞬时 CPU" if self.proc_mode == "instant" else "CPU（平均）"
        self.proc_hint.configure(
            text="共显示 %d 个进程 · 按%s排序 · 选中一行可结束它 · %s"
                 % (min(40, len(rows)), mode,
                    "每 5 秒自动刷新" if self.proc_mode == "avg" else "数据为刚才那一刻的采样"),
            fg=P["faint"])

    def grab_instant(self):
        if self._instant_thread and self._instant_thread.is_alive():
            return
        self.proc_hint.configure(text="正在采样 1 秒，看这一刻谁在占用 CPU…", fg=P["muted"])
        self.proc_btns["instant"].set_enabled(False)

        def work():
            rows, err = read_instant_cpu()
            self.root.after(0, lambda: self._instant_done(rows, err))

        self._instant_thread = threading.Thread(target=work, daemon=True)
        self._instant_thread.start()

    def _instant_done(self, rows, err):
        self.proc_btns["instant"].set_enabled(True)
        if rows is None:
            self.proc_hint.configure(text="瞬时采样失败：%s" % err, fg=P["red"])
            return
        self.proc_mode = "instant"
        self.proc_rows = rows
        self._render_proc_rows(rows)
        self.add_event("已抓取瞬时 CPU 占用，最高：%s %.1f%%"
                       % (rows[0][4], rows[0][1]), "info")

    def _proc_selected(self, _key):
        pass

    def _tick(self):
        try:
            if self.page == "procs" and self.proc_mode == "avg":
                self.refresh_procs()
            self._fw_update()
        except Exception:
            pass
        self.root.after(5000, self._tick)

    def kill_selected(self):
        key = self.proc_list.selected_key()
        if key is None:
            messagebox.showinfo("结束进程", "请先在列表里点选一个进程。")
            return
        row = next((r for r in self.proc_rows if r[0] == key), None)
        if not row:
            return
        pid, _cpu, _mem, _rss, name, _cmd = row
        if pid <= 1:
            return
        if not messagebox.askyesno("结束进程",
                                   "确定要结束「%s」（PID %d）吗？\n\n"
                                   "如果它是系统进程，结束后可能会自动重启。" % (name, pid)):
            return
        try:
            os.kill(pid, signal.SIGTERM)
            self.add_event("已结束进程 %s（PID %d）" % (name, pid), "info")
        except Exception as e:
            self.add_event("结束进程失败：%s" % e, "red")
        self.root.after(600, self.refresh_procs)

    # ---------------- 存储页
    def _build_storage(self, page):
        self.storage_sub, self.st_btns = self._header(
            page, "存储空间",
            "双击一行可在访达查看。清理前会逐项确认。",
            [("clean", "清理磁盘…", self.open_clean, "primary"),
             ("advice", "复制建议", self.copy_storage_advice, "secondary"),
             ("scan", "重新扫描", lambda: self.start_scan(force=True), "ghost")])

        wrap = tk.Frame(page, bg=P["bg"])
        wrap.pack(fill="both", expand=True, padx=26, pady=(0, 22))

        disk = Card(wrap, pad=16)
        disk.pack(fill="x")
        top = tk.Frame(disk.body, bg=P["card"])
        top.pack(fill="x")
        self.disk_label = tk.Label(top, text="正在读取磁盘信息…", bg=P["card"],
                                   fg=P["text"], font=(FONT, 13, "bold"))
        self.disk_label.pack(side="left")
        self.disk_right = tk.Label(top, text="", bg=P["card"], fg=P["muted"],
                                   font=(FONT, 10))
        self.disk_right.pack(side="right")
        self.disk_bar = tk.Canvas(disk.body, height=10, bg=P["card"],
                                  highlightthickness=0)
        self.disk_bar.pack(fill="x", pady=(10, 0))
        self.disk_bar.bind("<Configure>", lambda e: self._draw_disk_bar())
        self.disk_pct = 0
        self.disk_free = ""

        lst = Card(wrap, pad=0)
        lst.pack(fill="both", expand=True, pady=(14, 0))
        head = tk.Frame(lst, bg=P["card"])
        head.pack(fill="x", padx=16, pady=(12, 6))
        tk.Label(head, text="位置", bg=P["card"], fg=P["muted"],
                 font=(FONT, 10)).pack(side="left")
        tk.Label(head, text="占用", bg=P["card"], fg=P["muted"],
                 font=(FONT, 10)).pack(side="right")
        tk.Frame(lst, bg=P["line2"], height=1).pack(fill="x")

        self.storage_list = RowList(lst, self._storage_row, key_of=lambda r: r[1],
                                    on_activate=self.reveal_storage,
                                    empty="还没有扫描结果，点右上角「重新扫描」。")
        self.storage_list.pack(fill="both", expand=True, padx=6, pady=(2, 6))

        self.storage_hint = tk.Label(wrap, text="", bg=P["bg"], fg=P["faint"],
                                     font=(FONT, 10), anchor="w", justify="left",
                                     wraplength=760)
        self.storage_hint.pack(fill="x", pady=(10, 0))
        self.storage_loaded = False

    def _draw_disk_bar(self):
        c = self.disk_bar
        c.delete("all")
        w = c.winfo_width() or 600
        h = 10
        round_rect(c, 0, 0, w, h, 5, fill=P["track"], outline="")
        used = max(0.0, min(1.0, self.disk_pct / 100.0))
        if used > 0:
            col = P["red"] if self.disk_pct > 88 else (
                P["amber"] if self.disk_pct > 80 else P["accent"])
            round_rect(c, 0, 0, max(6, w * used), h, 5, fill=col, outline="")

    def _storage_row(self, row, item, idx):
        name, path, kb = item
        bg = P["card"]
        row.configure(bg=bg)
        box = tk.Frame(row, bg=bg)
        box.pack(side="left", fill="x", expand=True, padx=(10, 0), pady=8)
        tk.Label(box, text=name, bg=bg, fg=P["text"], font=(FONT, 11),
                 anchor="w").pack(anchor="w")
        short = path.replace(os.path.expanduser("~"), "~")
        if len(short) > 62:
            short = "…" + short[-60:]
        tk.Label(box, text=short, bg=bg, fg=P["faint"], font=(MONO, 8),
                 anchor="w").pack(anchor="w")
        right = tk.Frame(row, bg=bg)
        right.pack(side="right", padx=(8, 14))
        tk.Label(right, text=human(kb), bg=bg, fg=P["text2"], font=(MONO, 10),
                 anchor="e").pack(side="right", padx=(8, 0))
        total = sum(r[2] for r in getattr(self, "_scan_result", [])) or 1
        self._bar(right, kb / float(total), P["accent"], 130, 6).pack(side="right")

    # ---------------- 应用卸载页
    def _build_uninstall(self, page):
        self.uninstall_sub, self.un_btns = self._header(
            page, "应用卸载",
            "移到废纸篓，随时能拖回去。系统自带的东西不会出现在这里。",
            [("scan", "重新扫描", self.refresh_uninstall, "ghost")])

        wrap = tk.Frame(page, bg=P["bg"])
        wrap.pack(fill="both", expand=True, padx=26, pady=(0, 22))

        chips = tk.Frame(wrap, bg=P["bg"])
        chips.pack(fill="x")
        self.chip_un_apps = Chip(chips, "应用 --", fg=P["text2"], bg=P["card"],
                                 dot=P["accent"])
        self.chip_un_apps.pack(side="left")
        self.chip_un_size = Chip(chips, "可释放 --", fg=P["text2"], bg=P["card"])
        self.chip_un_size.pack(side="left", padx=8)
        self.chip_un_state = Chip(chips, "待扫描", fg=P["text2"], bg=P["card"])
        self.chip_un_state.pack(side="left")

        lst = Card(wrap, pad=0)
        lst.pack(fill="both", expand=True, pady=(12, 0))
        head = tk.Frame(lst.body, bg=P["card"])
        head.pack(fill="x", padx=16, pady=(12, 6))
        tk.Label(head, text="应用", bg=P["card"], fg=P["muted"],
                 font=(FONT, 10)).pack(side="left")
        tk.Label(head, text="操作", bg=P["card"], fg=P["muted"],
                 font=(FONT, 10)).pack(side="right", padx=(0, 4))
        tk.Frame(lst.body, bg=P["line2"], height=1).pack(fill="x")

        self.uninstall_list = RowList(lst.body, self._uninstall_row,
                                      key_of=lambda r: r["path"],
                                      empty="没发现可卸载的应用。")
        self.uninstall_list.pack(fill="both", expand=True, padx=6, pady=(2, 6))

        foot = tk.Frame(wrap, bg=P["bg"])
        foot.pack(fill="x", pady=(12, 0))
        self._un_leftover = False
        self.un_leftover_chk = CheckBox(foot, False, bg=P["bg"],
                                        command=self._un_toggle_leftover)
        self.un_leftover_chk.pack(side="left", anchor="n", pady=(2, 0))
        tk.Label(foot, text="连同残留数据一起清理（配置、缓存、登录状态——删了找不回来）",
                 bg=P["bg"], fg=P["muted"], font=(FONT, 10)).pack(side="left", padx=(8, 0))
        self.btn_un = RButton(foot, "卸载选中", self.uninstall_selected,
                               "primary", height=30)
        self.btn_un.pack(side="right")

        self.uninstall_hint = tk.Label(wrap, text="", bg=P["bg"], fg=P["faint"],
                                       font=(FONT, 10), anchor="w", justify="left",
                                       wraplength=760)
        self.uninstall_hint.pack(fill="x", pady=(8, 0))
        self.uninstall_loaded = False
        self._un_sel = set()
        self._un_apps = []
        self._un_total = 0

    def _uninstall_row(self, row, item, idx):
        bg = P["card"]
        row.configure(bg=bg)
        chk = CheckBox(row, item["path"] in self._un_sel, bg=bg,
                       command=lambda on, p=item["path"]: self._un_toggle(p, on))
        chk.pack(side="left", padx=(12, 10), anchor="n", pady=(12, 0))
        item["_chk"] = chk

        box = tk.Frame(row, bg=bg)
        box.pack(side="left", fill="x", expand=True)
        nm = item["name"]
        if len(nm) > 46:
            nm = nm[:45] + "…"
        tk.Label(box, text=nm, bg=bg, fg=P["text"], font=(FONT, 11, "bold"),
                 anchor="w").pack(anchor="w")
        meta = tk.Frame(box, bg=bg)
        meta.pack(anchor="w")
        if item.get("_ready"):
            bits = []
            if item.get("version"):
                bits.append("v" + item["version"])
            bits.append(human(item.get("size") or 0))
            if item.get("last_used"):
                bits.append("最后使用 " + item["last_used"])
            if item.get("leftovers"):
                bits.append("残留 %d 项" % len(item["leftovers"]))
            txt = " · ".join(bits)
        else:
            txt = "统计中…"
        mlbl = tk.Label(meta, text=txt, bg=bg,
                        fg=P["amber"] if item.get("running") else P["faint"],
                        font=(FONT, 9), anchor="w")
        mlbl.pack(anchor="w")
        item["_meta_lbl"] = mlbl
        short = item["path"].replace(os.path.expanduser("~"), "~")
        tk.Label(box, text=short, bg=bg, fg=P["faint"], font=(MONO, 8),
                 anchor="w").pack(anchor="w")

        act = tk.Frame(row, bg=bg)
        act.pack(side="right", padx=(8, 12))
        RButton(act, "卸载", lambda: self.uninstall_one(item),
                "ghost", height=26, size=10, padx=12).pack()

    def refresh_uninstall(self):
        if not hasattr(self, "uninstall_list"):
            return
        self._un_sel = set()
        self._un_apps = []
        self._un_total = 0
        self._un_shown = False
        self._un_done = False
        self._un_stage1 = None
        self.uninstall_list.set_items([])
        self.chip_un_apps.set("应用 --")
        self.chip_un_size.set("可释放 --")
        self.chip_un_state.set("扫描中…")
        self.btn_un.set_enabled(False)
        self.uninstall_hint.configure(text="正在扫描已安装的应用…", fg=P["muted"])
        self.un_btns["scan"].set_enabled(False)
        self._un_thread = threading.Thread(target=self._un_scan_worker, daemon=True)
        self._un_thread.start()
        self.root.after(300, self._poll_uninstall)

    def _un_scan_worker(self):
        apps = scan_apps()
        self._un_stage1 = apps
        enrich_apps(apps)
        self._un_stage1 = None
        self._un_result = apps
        self._un_done = True

    def _poll_uninstall(self):
        stage = getattr(self, "_un_stage1", None)
        if stage and not getattr(self, "_un_shown", False):
            self._un_shown = True
            self._un_apps = stage
            self.uninstall_list.set_items(stage)
            self.chip_un_apps.set("应用 %d 个" % len(stage))
            self.chip_un_state.set("统计大小中…")
        if getattr(self, "_un_done", False):
            self._un_done = False
            self._un_render(getattr(self, "_un_result", []))
            return
        if self._un_thread and self._un_thread.is_alive():
            self.root.after(400, self._poll_uninstall)
        else:
            self._un_render(getattr(self, "_un_result", []))

    def _un_render(self, apps):
        for a in apps:
            a["_ready"] = True
        self._un_apps = apps
        self._un_total = sum(a.get("size") or 0 for a in apps)
        self.uninstall_list.set_items(apps)
        self.chip_un_apps.set("应用 %d 个" % len(apps))
        self.chip_un_state.set("已完成")
        self.un_btns["scan"].set_enabled(True)
        self._un_refresh_sel()
        running = [a["name"] for a in apps if a.get("running")]
        text = "统计完成：%d 个应用，合计 %s。" % (len(apps), human(self._un_total))
        if running:
            text += " 正在运行：%s——卸载前先退出会更干净。" % "、".join(running[:3])
        self.uninstall_hint.configure(text=text, fg=P["muted"])
        self.uninstall_loaded = True

    def _un_toggle(self, path, on):
        if on:
            self._un_sel.add(path)
        else:
            self._un_sel.discard(path)
        # 状态可能从别处改过来的，把勾选框的显示也同步上
        for a in self._un_apps:
            chk = a.get("_chk")
            if a.get("path") == path and chk is not None:
                try:
                    if chk.on != on:
                        chk.set(on)
                except Exception:
                    pass
                break
        self._un_refresh_sel()

    def _un_refresh_sel(self):
        n = len(self._un_sel)
        kb = sum(a.get("size") or 0 for a in self._un_apps
                 if a["path"] in self._un_sel)
        self.btn_un.set_text(("卸载选中 (%d)" % n) if n else "卸载选中")
        self.btn_un.set_enabled(n > 0)
        if n:
            self.chip_un_size.set("已选 %s" % human(kb))
        else:
            self.chip_un_size.set("可释放 %s" % human(self._un_total))

    def _un_toggle_leftover(self, on):
        self._un_leftover = bool(on)
        if on:
            self.uninstall_hint.configure(
                text="已勾选：卸载时会把配置和缓存一起移到废纸篓。这些找不回来。",
                fg=P["amber"])
        elif getattr(self, "_un_total", 0):
            self.uninstall_hint.configure(
                text="统计完成：%d 个应用，合计 %s。"
                     % (len(self._un_apps), human(self._un_total)), fg=P["muted"])

    def uninstall_one(self, app):
        self._un_confirm([app])

    def uninstall_selected(self):
        sel = [a for a in self._un_apps if a["path"] in self._un_sel]
        if not sel:
            messagebox.showinfo("应用卸载",
                                "还没勾选应用。\n\n"
                                "点左边的方框，或者直接点某一行的「卸载」。")
            return
        self._un_confirm(sel)

    def _un_confirm(self, apps):
        total = sum(a.get("size") or 0 for a in apps)
        lines = []
        for a in apps[:12]:
            sz = ("  %s" % human(a.get("size") or 0)) if a.get("size") else ""
            lines.append("· %s%s" % (a["name"], sz))
        text = "要卸载 %d 个应用，合计 %s：\n\n%s" % (
            len(apps), human(total), "\n".join(lines))
        if len(apps) > 12:
            text += "\n…另外 %d 个" % (len(apps) - 12)
        text += "\n\n它们会被移到废纸篓，在访达里还能拖回来。"
        running = [a["name"] for a in apps if a.get("running")]
        if running:
            text += "\n\n注意：%s 正在运行，先退出会更干净。" % "、".join(running[:3])
        if self._un_leftover:
            lf = []
            for a in apps:
                for _p, label in (a.get("leftovers") or [])[:4]:
                    lf.append("%s/%s" % (a["name"], label))
            if lf:
                text += ("\n\n连同残留一起清，这些目录会一起进废纸篓：\n"
                         + "\n".join("  · " + x for x in lf[:10]))
                if len(lf) > 10:
                    text += "\n  …另外 %d 项" % (len(lf) - 10)
                text += ("\n残留里可能有你的聊天记录、登录状态这类东西，"
                         "删了找不回来。")
        if not messagebox.askyesno("确认卸载", text):
            return
        self._un_udone = False
        self._un_unres = []
        self.btn_un.set_enabled(False)
        self.uninstall_hint.configure(text="正在卸载，不要关闭窗口…", fg=P["muted"])
        self._un_uthread = threading.Thread(target=self._un_run_worker,
                                            args=(apps,), daemon=True)
        self._un_uthread.start()
        self.root.after(300, self._poll_uninstall_run)

    def _un_run_worker(self, apps):
        for a in apps:
            try:
                res = uninstall_app(a, with_leftovers=self._un_leftover)
            except Exception as e:
                res = {"moved": 0, "leftover_kb": 0, "failed": 1, "errors": [str(e)]}
            self._un_unres.append((a, res))
        self._un_udone = True

    def _poll_uninstall_run(self):
        for a, res in getattr(self, "_un_unres", []):
            lbl = a.get("_meta_lbl")
            if lbl is None or a.get("_done_marked"):
                continue
            try:
                if not lbl.winfo_exists():
                    continue
            except Exception:
                continue
            a["_done_marked"] = True
            parts = []
            if res.get("moved"):
                parts.append("已移到废纸篓")
            if res.get("leftover_n"):
                parts.append("残留 %d 项已清" % res["leftover_n"])
            if res.get("failed"):
                parts.append("%d 项没成功" % res["failed"])
            lbl.configure(text=" · ".join(parts) or "已处理", fg=P["green"])
        if getattr(self, "_un_udone", False):
            self._un_udone = False
            self._un_finished()
            return
        self.root.after(300, self._poll_uninstall_run)

    def _un_finished(self):
        results = getattr(self, "_un_unres", [])
        moved = sum(r.get("moved") or 0 for _a, r in results)
        lkb = sum(r.get("leftover_kb") or 0 for _a, r in results)
        lfn = sum(r.get("leftover_n") or 0 for _a, r in results)
        failed = sum(r.get("failed") or 0 for _a, r in results)
        left = [a for a in self._un_apps if os.path.lexists(a["path"])]
        self._un_apps = left
        self._un_sel = set()
        self._un_total = sum(a.get("size") or 0 for a in left)
        self.uninstall_list.set_items(left)
        self.chip_un_apps.set("应用 %d 个" % len(left))
        self._un_refresh_sel()
        text = "卸载完成：%s 移入废纸篓" % human(moved)
        if lfn:
            text += "，另清掉 %d 项残留" % lfn
        if failed:
            text += "，有 %d 项没成功" % failed
        text += "。剩下的在访达废纸篓里能拖回去。"
        self.uninstall_hint.configure(text=text, fg=P["green"])
        # 存储页的数字过期了，让它下次进入时重新扫
        self.storage_loaded = False
        try:
            self.add_event("应用卸载：%s 移入废纸篓" % human(moved), "green")
        except Exception:
            pass

    def open_clean(self):
        dlg = getattr(self, "_cleandlg", None)
        if dlg is not None and dlg.winfo_exists():
            dlg.lift()
            return
        self._cleandlg = CleanDialog(self)

    def open_update(self):
        dlg = getattr(self, "_upddlg", None)
        if dlg is not None and dlg.winfo_exists():
            dlg.lift()
            return
        self._upddlg = UpdateDialog(self)

    def update_auto_maybe(self):
        """启动时按用户意愿看一眼新版本：默认关闭，勾了才每 7 天发一次请求。"""
        cfg = update_cfg_read()
        if not cfg.get("auto"):
            return
        if time.time() - to_int(cfg.get("last_check"), 0) < UPDATE_AUTO_DAYS * 86400:
            return

        def work():
            r = update_check()
            if r.get("ok") and r["info"].get("newer"):
                v = r["info"].get("version")
                try:
                    self.root.after(0, lambda: notify(
                        "电池医生有新版本 v%s" % v,
                        "侧栏左下角「检查更新」可以看更新内容并下载"))
                except Exception:
                    pass
        threading.Thread(target=work, daemon=True).start()

    def start_scan(self, force=False):
        if self._scan_thread and self._scan_thread.is_alive():
            return
        cached = None if force else scan_cache_read()
        use_cache = bool(cached) and (time.time() - cached["ts"] < SCAN_TTL)
        if use_cache:
            # 有缓存就先把页面填上，不让用户对着空列表等 —— 扫描在后台做
            self._scan_result = cached["items"]
            self._scan_ts = cached["ts"]
            self._render_scan(stamp=cached["ts"], pending=True)
            if time.time() - cached["ts"] < SCAN_FRESH:
                return
        else:
            self.storage_list.set_items([])
            self.storage_list.empty = ("正在扫描…（第一次约半分钟，之后直接用上次结果，"
                                       "不用再等）")
            self.storage_hint.configure(text="扫描中，请稍候…", fg=P["muted"])
        self.st_btns["scan"].set_enabled(False)
        self._scan_thread = threading.Thread(target=self._scan_worker, daemon=True)
        self._scan_thread.start()
        self.root.after(300, self._poll_scan)

    def _scan_worker(self):
        try:
            result = scan_all()
        except Exception:
            result = []
        if result:
            scan_cache_write(result)
        self._scan_result = result
        self._scan_ts = int(time.time())
        self._scan_done = True

    def _poll_scan(self):
        if getattr(self, "_scan_done", False):
            self._scan_done = False
            self._render_scan()
        elif self._scan_thread and self._scan_thread.is_alive():
            self.root.after(500, self._poll_scan)
        else:
            self._render_scan()

    def _render_scan(self, stamp=None, pending=False):
        rows = getattr(self, "_scan_result", [])
        self.storage_list.empty = "没有可统计的目录。"
        self.storage_list.set_items(rows)
        self.st_btns["scan"].set_enabled(True)

        try:
            st = os.statvfs("/")
            free_kb = st.f_bavail * st.f_frsize // 1024
            total_kb = st.f_blocks * st.f_frsize // 1024
            used_pct = 100.0 * (total_kb - free_kb) / total_kb
        except Exception:
            free_kb = total_kb = 0
            used_pct = 0

        self.disk_pct = used_pct
        self.disk_free = human(free_kb)
        color = P["red"] if used_pct > 88 else (P["amber"] if used_pct > 80 else P["accent"])
        self.disk_label.configure(text="可用空间 %s" % human(free_kb), fg=P["text"])
        self.disk_right.configure(
            text="已用 %.0f%% · 共 %s" % (used_pct, human(total_kb)), fg=color)
        self._draw_disk_bar()

        when = human_ago(stamp if stamp is not None else getattr(self, "_scan_ts", 0))
        if pending:
            self.storage_hint.configure(
                text="上次扫描：%s。下面是当时的结果，正在后台更新…" % when, fg=P["muted"])
        elif used_pct > 85:
            hint = ("磁盘空间偏紧。低于 15% 可用时，系统会变慢、更新也可能失败。"
                    "点右上角「清理磁盘…」能清掉缓存和旧安装包；微信占的空间要在微信里清。"
                    "　· 数据采集于%s" % when)
            self.storage_hint.configure(text=hint, fg=P["amber"])
        else:
            self.storage_hint.configure(
                text="磁盘空间充裕。要清出更多空间，点右上角「清理磁盘…」。"
                     "　· 数据采集于%s" % when, fg=P["faint"])
        self.storage_loaded = True

    def reveal_storage(self, _key=None):
        key = self.storage_list.selected_key() if _key is None else _key
        if key:
            subprocess.run(["/usr/bin/open", key])
        else:
            subprocess.run(["/usr/bin/open", os.path.expanduser("~")])

    # ---------------- 启动项页
    def _build_startup(self, page):
        self.startup_sub, _ = self._header(
            page, "启动项目",
            "停用只是把文件挪到备份目录，随时可以恢复。",
            [("script", "生成系统清理脚本", self.gen_system_script, "secondary"),
             ("opt", "一键优化", self.optimize, "ghost"),
             ("scan", "重新扫描", self.refresh_startup, "ghost")])

        wrap = tk.Frame(page, bg=P["bg"])
        wrap.pack(fill="both", expand=True, padx=26, pady=(0, 22))

        self.startup_chips = tk.Frame(wrap, bg=P["bg"])
        self.startup_chips.pack(fill="x")
        self.chip_active = Chip(self.startup_chips, "生效中 --", fg=P["text2"],
                                bg=P["card"], dot=P["accent"])
        self.chip_active.pack(side="left")
        self.chip_sys = Chip(self.startup_chips, "系统级 --", fg=P["text2"], bg=P["card"])
        self.chip_sys.pack(side="left", padx=8)
        self.chip_off = Chip(self.startup_chips, "已停用 --", fg=P["text2"], bg=P["card"])
        self.chip_off.pack(side="left")

        lst = Card(wrap, pad=0)
        lst.pack(fill="both", expand=True, pady=(12, 0))
        head = tk.Frame(lst, bg=P["card"])
        head.pack(fill="x", padx=16, pady=(12, 6))
        tk.Label(head, text="项目", bg=P["card"], fg=P["muted"],
                 font=(FONT, 10)).pack(side="left")
        tk.Label(head, text="操作", bg=P["card"], fg=P["muted"],
                 font=(FONT, 10)).pack(side="right", padx=(0, 4))
        tk.Frame(lst, bg=P["line2"], height=1).pack(fill="x")

        self.startup_list = RowList(lst, self._startup_row, key_of=lambda r: r[1],
                                    empty="没有发现第三方启动项，很干净。")
        self.startup_list.pack(fill="both", expand=True, padx=6, pady=(2, 6))

        self.startup_hint = tk.Label(wrap, text="", bg=P["bg"], fg=P["faint"],
                                     font=(FONT, 10), anchor="w", justify="left",
                                     wraplength=760)
        self.startup_hint.pack(fill="x", pady=(10, 0))
        self.startup_loaded = False

    def _startup_row(self, row, item, idx):
        state, name, level, path, kind = item
        bg = P["card"]
        row.configure(bg=bg)
        dot = P["accent"] if state == "已启用" else P["faint"]
        tk.Label(row, text="●", bg=bg, fg=dot, font=(FONT, 9)).pack(
            side="left", padx=(12, 8), pady=9)
        box = tk.Frame(row, bg=bg)
        box.pack(side="left", fill="x", expand=True)
        nm = name if len(name) <= 44 else name[:43] + "…"
        tk.Label(box, text=nm, bg=bg,
                 fg=P["text"] if state == "已启用" else P["muted"],
                 font=(FONT, 11), anchor="w").pack(anchor="w")
        meta = tk.Frame(box, bg=bg)
        meta.pack(anchor="w")
        tk.Label(meta, text=level, bg=bg, fg=P["faint"], font=(FONT, 9)).pack(side="left")
        tk.Label(meta, text=" · %s" % state, bg=bg, fg=P["faint"],
                 font=(FONT, 9)).pack(side="left")

        act = tk.Frame(row, bg=bg)
        act.pack(side="right", padx=(8, 12))
        if kind == "backup":
            b = RButton(act, "恢复", lambda: self.enable_startup(path, name),
                        "secondary", height=26, size=10, padx=12)
        elif kind == "system":
            b = RButton(act, "需管理员", lambda: self.system_hint(path),
                        "ghost", height=26, size=10, padx=12)
        else:
            b = RButton(act, "停用", lambda: self.disable_startup(path, name),
                        "ghost", height=26, size=10, padx=12)
        b.pack()

    def _scan_startup(self):
        items = []
        user_dir = os.path.expanduser("~/Library/LaunchAgents")
        names = sorted(os.listdir(user_dir)) if os.path.isdir(user_dir) else []
        for name in names:
            if name.endswith(".plist"):
                items.append(("已启用", name, "用户", os.path.join(user_dir, name), "user"))
        for path in SYSTEM_AGENTS:
            if os.path.exists(path):
                items.append(("已启用", os.path.basename(path), "系统",
                              path, "system"))
        if os.path.isdir(BACKUP):
            for name in sorted(os.listdir(BACKUP)):
                if name.endswith(".plist"):
                    items.append(("已停用", name, "用户",
                                  os.path.join(BACKUP, name), "backup"))
        return items

    def refresh_startup(self):
        if not hasattr(self, "startup_list"):
            return
        items = self._scan_startup()
        self.startup_list.set_items(items)
        active = sum(1 for i in items if i[0] == "已启用")
        sysn = sum(1 for i in items if i[3] == "system")
        off = sum(1 for i in items if i[0] == "已停用")
        self.chip_active.set("生效中 %d" % active, fg=P["text2"], bg=P["card"],
                             dot=P["accent"])
        self.chip_sys.set("系统级 %d" % sysn, fg=P["text2"], bg=P["card"])
        self.chip_off.set("已停用 %d" % off, fg=P["text2"], bg=P["card"])
        self.startup_hint.configure(
            text="用户级项目可直接停用；系统级项目在 /Library 下，需要管理员权限。"
                 "停用的文件都保存在 ~/Library/.batterydoctor-backup。", fg=P["faint"])
        self.startup_loaded = True

    def disable_startup(self, path, name):
        os.makedirs(BACKUP, exist_ok=True)
        try:
            shutil.move(path, os.path.join(BACKUP, name))
            self.add_event("已停用启动项 %s" % name, "info")
            self.refresh_startup()
        except Exception as e:
            messagebox.showerror("停用失败", str(e))

    def enable_startup(self, path, name):
        try:
            shutil.move(path, os.path.expanduser("~/Library/LaunchAgents/" + name))
            self.add_event("已恢复启动项 %s" % name, "info")
            self.refresh_startup()
        except Exception as e:
            messagebox.showerror("恢复失败", str(e))

    def system_hint(self, path):
        self.root.clipboard_clear()
        self.root.clipboard_append('sudo mv "%s" ~/Library/.batterydoctor-backup/' % path)
        messagebox.showinfo(
            "需要管理员权限",
            "系统级项目在 /Library 下，普通权限无法移动。\n\n"
            "我已经把命令复制到剪贴板，打开「终端」粘贴执行即可：\n\n"
            'sudo mv "%s" ~/Library/.batterydoctor-backup/\n\n'
            "执行后回到本页点「重新扫描」。" % path)

    # ---------------- 网络诊断页
    def _build_network(self, page):
        self.net_sub, _acts = self._header(
            page, "网络诊断",
            "检查 Wi-Fi、IP、网关、DNS、代理与外网连通性，异常可一键修复。",
            [("rescan", "重新诊断", self.start_net_scan, "secondary")])

        wrap = tk.Frame(page, bg=P["bg"])
        wrap.pack(fill="both", expand=True, padx=26, pady=(0, 18))

        # 状态卡
        self.net_card = tk.Frame(wrap, bg=P["green_soft"], highlightthickness=1,
                                 highlightbackground=P["green_line"], bd=0)
        self.net_card.pack(fill="x")
        self._net_inner = tk.Frame(self.net_card, bg=P["green_soft"])
        self._net_inner.pack(fill="x", padx=18, pady=13)
        self.net_icon = tk.Canvas(self._net_inner, width=74, height=74,
                                  bg=P["green_soft"], highlightthickness=0)
        self.net_icon.pack(side="left")
        self._net_txt = tk.Frame(self._net_inner, bg=P["green_soft"])
        self._net_txt.pack(side="left", fill="both", expand=True, padx=(16, 0))
        self.net_title = tk.Label(self._net_txt, text="正在诊断网络…",
                                  bg=P["green_soft"], fg=P["green"],
                                  font=(FONT, 16, "bold"), anchor="w", justify="left")
        self.net_title.pack(anchor="w")
        self.net_desc = tk.Label(self._net_txt, text="", bg=P["green_soft"],
                                 fg=P["text2"], font=(FONT, 11), anchor="w",
                                 justify="left", wraplength=600)
        self.net_desc.pack(anchor="w", pady=(4, 0))
        self.net_steps = tk.Label(self._net_txt, text="", bg=P["green_soft"],
                                  fg=P["text2"], font=(FONT, 11), anchor="w",
                                  justify="left", wraplength=600)
        self.net_steps.pack(anchor="w", pady=(5, 0))
        self._net_bg = [P["green_soft"], P["green_line"]]
        self._draw_net_icon(P["green"])

        # 指标卡
        grid = tk.Frame(wrap, bg=P["bg"])
        grid.pack(fill="x", pady=(12, 0))
        for i in range(4):
            grid.columnconfigure(i, weight=1, uniform="nn")
        self.net_rows = {}
        for i, (key, label, hint) in enumerate(
                [("ssid", "当前网络", "名称与频段"),
                 ("latency", "网关延迟", "越小越快"),
                 ("dnsms", "域名解析", "20 ms 内算很快"),
                 ("proxy", "系统代理", "关闭时最省心")]):
            card = MetricCard(grid, label, hint)
            card.grid(row=0, column=i, padx=(0 if i == 0 else 8, 0), sticky="nsew")
            self.net_rows[key] = card

        low = tk.Frame(wrap, bg=P["bg"])
        low.pack(fill="both", expand=True, pady=(12, 0))

        # 先固定右侧修复面板，再让检查清单吃掉剩余宽度（pack 顺序不能反）
        side = tk.Frame(low, bg=P["card"], width=240,
                        highlightthickness=1, highlightbackground=P["line"])
        side.pack(side="right", fill="y", padx=(12, 0))
        side.pack_propagate(False)
        box = tk.Frame(side, bg=P["card"])
        box.pack(fill="both", expand=True, padx=14, pady=13)

        lst = Card(low, pad=0)
        lst.pack(side="left", fill="both", expand=True)
        head = tk.Frame(lst, bg=P["card"])
        head.pack(fill="x", padx=14, pady=(10, 6))
        tk.Label(head, text="检查项", bg=P["card"], fg=P["text"],
                 font=(FONT, 12, "bold")).pack(side="left")
        self.net_hint = tk.Label(head, text="", bg=P["card"], fg=P["faint"],
                                 font=(FONT, 10))
        self.net_hint.pack(side="right")
        tk.Frame(lst, bg=P["line2"], height=1).pack(fill="x")
        self.net_list = tk.Frame(lst, bg=P["card"])
        self.net_list.pack(fill="both", expand=True, padx=14, pady=(2, 10))
        self.net_check_rows = {}
        for key, title in NET_CHECKS:
            self._net_check_row(self.net_list, key, title)

        tk.Label(box, text="快捷修复", bg=P["card"], fg=P["text"],
                 font=(FONT, 12, "bold")).pack(anchor="w")
        tk.Label(box, text="改动前会自动备份，随时能还原。", bg=P["card"],
                 fg=P["faint"], font=(FONT, 9), anchor="w", justify="left",
                 wraplength=200).pack(anchor="w", pady=(2, 10))
        RButton(box, "一键修复联网", self.net_fix_all, "primary",
                width=208).pack(anchor="w", pady=(0, 7))
        for text, cmd in [("关闭系统代理", self.net_proxy_off),
                          ("DNS 换为阿里", self.net_dns_ali),
                          ("DNS 恢复自动", self.net_dns_auto),
                          ("刷新 DNS 缓存", self.net_flush),
                          ("续租 IP 地址", self.net_renew),
                          ("还原上次修复", self.net_restore),
                          ("复制网络报告", self.net_copy_report)]:
            RButton(box, text, cmd, "ghost", width=208, height=28,
                    size=11).pack(anchor="w", pady=1)
        self.net_status = tk.Label(box, text="", bg=P["card"], fg=P["faint"],
                                   font=(FONT, 9), anchor="w", justify="left",
                                   wraplength=200)
        self.net_status.pack(anchor="w", pady=(8, 0))

    def _net_check_row(self, parent, key, title):
        row = tk.Frame(parent, bg=P["card"])
        row.pack(fill="x")
        dot = tk.Canvas(row, width=18, height=18, bg=P["card"], highlightthickness=0)
        dot.pack(side="left", padx=(0, 8), pady=7)
        tk.Label(row, text=title, bg=P["card"], fg=P["text2"], font=(FONT, 11),
                 width=9, anchor="w").pack(side="left")
        val = tk.Label(row, text="检查中…", bg=P["card"], fg=P["faint"],
                       font=(FONT, 11, "bold"), width=15, anchor="w")
        val.pack(side="left", padx=(2, 10))
        det = tk.Label(row, text="", bg=P["card"], fg=P["muted"], font=(FONT, 10),
                       anchor="w", justify="left")
        det.pack(side="left", fill="x", expand=True)
        # 按标签自身实际宽度换行（用父容器宽度算不准，中间还有若干固定宽度列）
        def _fit(e, lb=det):
            want = max(120, e.width - 4)
            if abs(want - to_int(lb.cget("wraplength"))) >= 4:
                lb.configure(wraplength=want)
        det.bind("<Configure>", _fit)
        self._paint_dot(dot, "run")
        self.net_check_rows[key] = (dot, val, det)

    @staticmethod
    def _paint_dot(cv, state):
        cv.delete("all")
        col = NET_COLORS.get(state, P["faint"])
        if state in ("ok", "warn", "fail"):
            cv.create_oval(1, 1, 17, 17, fill=col, outline="")
            cv.create_text(9, 9, text=NET_GLYPH[state], fill="#FFFFFF",
                           font=(FONT, 9, "bold"))
        elif state == "skip":
            cv.create_oval(3, 3, 15, 15, outline=col, width=2)
        else:
            cv.create_oval(5, 5, 13, 13, fill=col, outline="")

    def _draw_net_icon(self, color):
        c = self.net_icon
        c.delete("all")
        cx, cy = 37, 54
        for r, wd in ((30, 5), (20, 5), (10, 5)):
            c.create_arc(cx - r, cy - r, cx + r, cy + r, start=45, extent=90,
                         style="arc", outline=color, width=wd)
        c.create_oval(cx - 4, cy - 5, cx + 4, cy + 3, fill=color, outline="")

    def _set_net_card(self, level, title, desc, steps):
        soft, line, fg = {
            "red": (P["red_soft"], P["red_line"], P["red"]),
            "amber": (P["amber_soft"], P["amber_line"], P["amber"]),
            "green": (P["green_soft"], P["green_line"], P["green"]),
        }[level]
        self.net_card.configure(bg=soft, highlightbackground=line)
        for w in (self._net_inner, self._net_txt, self.net_title, self.net_desc,
                  self.net_steps, self.net_icon):
            try:
                w.configure(bg=soft)
            except Exception:
                pass
        self._net_bg = [soft, line]
        self.net_title.configure(text=title, fg=fg)
        self.net_desc.configure(text=desc)
        if steps:
            self.net_steps.configure(text="\n".join("· " + s for s in steps[:3]))
        else:
            self.net_steps.configure(text="")
        self._draw_net_icon(fg)

    def start_net_scan(self):
        if getattr(self, "_net_thread", None) is not None and self._net_thread.is_alive():
            return
        self.net_checks = []
        self._net_q = queue.Queue()
        for key, _t in NET_CHECKS:
            dot, val, det = self.net_check_rows[key]
            self._paint_dot(dot, "run")
            val.configure(text="检查中…", fg=P["faint"])
            det.configure(text="")
        self.net_title.configure(text="正在诊断网络…", fg=P["muted"])
        self.net_desc.configure(text="挨个检查 Wi-Fi、IP、网关、DNS、代理与 hosts，约需十秒。")
        self.net_steps.configure(text="")
        self.net_hint.configure(text="")
        self.net_loaded = True

        def work():
            def on_check(item):
                self._net_q.put(("check", item))

            def on_done(scan):
                self._net_q.put(("done", scan))

            try:
                NetScan(on_check, on_done).run()
            except Exception as e:
                self._net_q.put(("error", repr(e)))

        self._net_thread = threading.Thread(target=work, daemon=True)
        self._net_thread.start()
        self.root.after(100, self._poll_net)

    def _poll_net(self):
        q = getattr(self, "_net_q", None)
        if q is None:
            return
        done = False
        try:
            while True:
                kind, payload = q.get_nowait()
                if kind == "check":
                    self._apply_net_check(payload)
                elif kind == "done":
                    self._apply_net_scan(payload)
                    done = True
                elif kind == "error":
                    self.net_desc.configure(text="诊断出错：%s" % payload)
                    done = True
        except queue.Empty:
            pass
        if not done:
            self.root.after(120, self._poll_net)

    def _apply_net_check(self, item):
        self.net_checks.append(item)
        row = self.net_check_rows.get(item["key"])
        if not row:
            return
        dot, val, det = row
        self._paint_dot(dot, item["state"])
        val.configure(text=item["value"],
                      fg=NET_COLORS.get(item["state"], P["text"]))
        det.configure(text=item["detail"])

    def _apply_net_scan(self, scan):
        d = scan.info or {}
        self.net_info = d
        self._net_scan = scan
        level, title, desc, steps = scan.verdict()
        self._set_net_card(level, title, desc, steps)

        ssid = d.get("ssid") or (d.get("service") or "—")
        ch = (d.get("channel") or "").split(",")[0]
        band = ""
        if ch:
            band = "5 GHz" if to_int(ch, 0) >= 36 else "2.4 GHz"
        self.net_rows["ssid"].set(ssid, P["text"],
                                  "%s · 信道 %s" % (band, ch) if band else "有线网络")
        self.net_rows["latency"].set(
            ("%.0f ms" % scan.gw_ms) if scan.gw_ms else "不通",
            P["text"] if scan.gw_ms else P["red"],
            ("网关 %s" % d.get("router", "")) if d.get("router") else "无默认网关")
        self.net_rows["dnsms"].set(
            ("%d ms" % scan.dns_ms) if scan.dns_ms is not None else "—",
            P["red"] if (scan.dns_ms or 0) > 900 else P["text"],
            "、".join(d.get("dns", [])[:2]) or "路由器默认")
        if d.get("proxy_on"):
            self.net_rows["proxy"].set("%s:%d" % (d.get("proxy_host", ""),
                                                  d.get("proxy_port", 0)),
                                       P["amber"], "代理生效中，关掉更省心")
        else:
            self.net_rows["proxy"].set("直连", P["green"], "流量不经过代理")
        okc = sum(1 for c in self.net_checks if c["state"] == "ok")
        self.net_hint.configure(
            text="%d 项正常 · 共 %d 项" % (okc, len(self.net_checks)))
        self.net_status.configure(text="诊断完成于 " + time.strftime("%H:%M:%S"))

    # ---- 修复动作
    def _net_apply_dns(self, servers):
        d = self.net_info or read_net_basic()
        svc = d.get("service") or "Wi-Fi"
        if not os.environ.get("BD_DRY"):
            save_net_backup(d)
        if servers:
            out = net_cmd(["/usr/sbin/networksetup", "-setdnsservers", svc]
                          + list(servers), 12)
            msg = "DNS 已改为 %s" % "、".join(servers)
        else:
            out = net_cmd(["/usr/sbin/networksetup", "-setdnsservers", svc, "Empty"], 12)
            msg = "DNS 已恢复为路由器自动分配"
        net_cmd(["/usr/bin/dscacheutil", "-flushcache"], 8)
        if "Error" in out or "ERROR" in out:
            msg = "修改失败：%s（可能需要管理员权限）" % out.splitlines()[-1][:80]
            self.add_event(msg, "red")
            messagebox.showwarning("DNS 未修改", msg)
        else:
            self.add_event(msg + "。", "green")
            self.net_status.configure(text=msg)
        self.start_net_scan()

    def net_dns_ali(self):
        self._net_apply_dns(DNS_SUGGEST)

    def net_dns_auto(self):
        self._net_apply_dns(None)

    def net_proxy_off(self):
        d = self.net_info or read_net_basic()
        svc = d.get("service") or "Wi-Fi"
        if not d.get("proxy_on"):
            messagebox.showinfo("无需处理", "系统当前没有启用代理，流量本来就是直连。")
            return
        save_net_backup(d)
        for kind, _l in PROXY_KINDS:
            net_cmd(["/usr/sbin/networksetup", "-set%sstate" % kind, svc, "off"], 12)
        net_cmd(["/usr/sbin/networksetup", "-setautoproxystate", svc, "off"], 12)
        self.add_event("已关闭系统代理，恢复直连。", "green")
        self.net_status.configure(text="系统代理已关闭")
        self.start_net_scan()

    def net_flush(self):
        net_cmd(["/usr/bin/dscacheutil", "-flushcache"], 8)
        out = net_cmd(["/usr/bin/killall", "-HUP", "mDNSResponder"], 6)
        if "not permitted" in out or "No matching" in out:
            self.net_status.configure(text="解析缓存已清空（系统解析器需重启才彻底刷新）")
            self.add_event("DNS 缓存已刷新（部分需要重启才彻底生效）。", "info")
        else:
            self.net_status.configure(text="DNS 缓存已刷新")
            self.add_event("DNS 缓存已刷新。", "green")

    def net_renew(self):
        d = self.net_info or read_net_basic()
        dev = d.get("dev") or "en0"
        out = net_cmd(["/usr/sbin/ipconfig", "set", dev, "DHCP"], 20)
        if "not permitted" in out or "must be root" in out.lower() or "ERROR" in out:
            cmd = 'sudo ipconfig set %s DHCP' % dev
            self.root.clipboard_clear()
            self.root.clipboard_append(cmd)
            self.net_status.configure(text="需要管理员权限，命令已复制到剪贴板")
            messagebox.showinfo(
                "需要管理员权限",
                "续租 IP 需要管理员权限。\n\n命令已复制到剪贴板，"
                "打开「终端」粘贴执行：\n\n%s" % cmd)
            return
        self.add_event("已让 %s 重新申请 IP 地址。" % dev, "green")
        self.net_status.configure(text="已续租，正在复测…")
        self.root.after(2500, self.start_net_scan)

    def net_restore(self):
        cfg = load_net_backup()
        if not cfg:
            messagebox.showinfo("没有备份",
                                "还没有做过网络修复，或备份文件已被删除。\n"
                                "备份位置：~/Library/.batterydoctor-backup/net-last.json")
            return
        svc = cfg.get("service") or "Wi-Fi"
        dns = cfg.get("dns") or []
        if dns:
            net_cmd(["/usr/sbin/networksetup", "-setdnsservers", svc] + dns, 12)
        else:
            net_cmd(["/usr/sbin/networksetup", "-setdnsservers", svc, "Empty"], 12)
        rev = dict((v, k) for k, v in PROXY_KINDS)
        for p in cfg.get("proxies") or []:
            kind = rev.get(p.get("label"))
            if not kind:
                continue
            net_cmd(["/usr/sbin/networksetup", "-set" + kind, svc,
                     p.get("host", ""), str(p.get("port", 0))], 12)
            net_cmd(["/usr/sbin/networksetup", "-set%sstate" % kind, svc, "on"], 12)
        net_cmd(["/usr/bin/dscacheutil", "-flushcache"], 8)
        self.add_event("网络设置已还原到 %s 的状态。" % cfg.get("ts", "上次修复前"), "info")
        self.net_status.configure(text="已还原到 %s 的设置" % cfg.get("ts", "修复前"))
        self.start_net_scan()

    def net_fix_all(self):
        dlg = getattr(self, "_netdlg", None)
        try:
            if dlg is not None and dlg.winfo_exists():
                dlg.lift()
                dlg.focus_force()
                return
        except Exception:
            pass
        self._netdlg = NetRepairDialog(self)

    def build_net_report(self):
        d = self.net_info or {}
        scan = getattr(self, "_net_scan", None)
        if scan is not None and scan.checks:
            level, title, desc, steps = scan.verdict()
        else:
            level, title, desc, steps = ("info", "尚未完成诊断",
                                         "点一下「重新诊断」再生成报告。", [])
        lines = [
            "网络诊断报告",
            "时间：%s" % time.strftime("%Y-%m-%d %H:%M:%S"),
            "",
            "【结论】%s" % title,
            desc,
            "",
            "【连接信息】",
            "  网络：%s（%s）" % (d.get("ssid") or "—", d.get("service") or "—"),
            "  接口：%s    频率信道：%s" % (d.get("dev") or "—", d.get("channel") or "—"),
            "  IP / 掩码：%s / %s" % (d.get("ip") or "—", d.get("mask") or "—"),
            "  网关：%s" % (d.get("router") or "—"),
            "  DNS：%s" % ("、".join(d.get("dns") or []) or "路由器默认"),
            "  系统代理：%s" % (
                "、".join("%s %s:%d" % (k, h, p) for k, h, p in d.get("proxy_list") or [])
                or "未启用"),
            "",
            "【检查明细】",
        ]
        for c in self.net_checks:
            lines.append("  [%s] %-6s %-16s %s" % (
                {"ok": "正常", "warn": "留意", "fail": "异常", "skip": "跳过"}
                .get(c["state"], c["state"]),
                dict(NET_CHECKS).get(c["key"], c["key"]),
                c["value"], c["detail"]))
        if steps:
            lines += ["", "【建议】"] + ["  %d. %s" % (i + 1, s)
                                        for i, s in enumerate(steps)]
        return "\n".join(lines)

    def net_copy_report(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.build_net_report())
        self.net_status.configure(text="报告已复制到剪贴板")
        self.add_event("网络诊断报告已复制到剪贴板。", "green")

    # ---------------- 充电养护页
    def _build_charge(self, page):
        sub, _ = self._header(
            page, "充电养护",
            "锂电池只怕两件事：长期停在满电、热着充电。这里能看自己最近怎么充的，"
            "也能直接给充电器设一个上限。")
        self.chg_sub = sub

        wrap = tk.Frame(page, bg=P["bg"])
        wrap.pack(fill="both", expand=True, padx=26, pady=(0, 22))

        grid = tk.Frame(wrap, bg=P["bg"])
        grid.pack(fill="x")
        for i in range(4):
            grid.columnconfigure(i, weight=1, uniform="chg")
        self.chg_rows = {}
        for idx, (key, label, hint) in enumerate(
                [("state", "当前状态", "插着电还是在用电池"),
                 ("power", "充电功率", "实际充进电池的功率"),
                 ("temp", "电池温度", "超过 40℃ 先别充"),
                 ("limit", "充电上限", "SMC 里的限流值")]):
            c = MetricCard(grid, label, hint)
            c.grid(row=0, column=idx, padx=(0 if idx == 0 else 8, 0), sticky="nsew")
            self.chg_rows[key] = c

        lim = Card(wrap, pad=0)
        lim.pack(fill="x", pady=(14, 0))
        inner = tk.Frame(lim, bg=P["card"])
        inner.pack(fill="x", padx=18, pady=16)
        top = tk.Frame(inner, bg=P["card"])
        top.pack(fill="x")
        tk.Label(top, text="充电上限", bg=P["card"], fg=P["text"],
                 font=(FONT, 12, "bold")).pack(side="left")
        self.chg_limit_lbl = tk.Label(top, text="读取中…", bg=P["card"], fg=P["muted"],
                                      font=(FONT, 10))
        self.chg_limit_lbl.pack(side="right")
        self.chg_limit_desc = tk.Label(
            inner, text="", bg=P["card"], fg=P["muted"], font=(FONT, 10),
            anchor="w", justify="left", wraplength=520)
        self.chg_limit_desc.pack(fill="x", pady=(6, 10))

        row = tk.Frame(inner, bg=P["card"])
        row.pack(fill="x")
        for pct, txt, kind in ((80, "设成 80%", "primary"), (70, "70%", "secondary"),
                               (60, "60%", "secondary"), (100, "恢复 100%", "secondary")):
            RButton(row, txt, lambda p=pct: self.set_charge_limit(p), kind,
                    size=10, height=30, padx=12).pack(side="left", padx=(0, 6))
        self.chg_limit_msg = tk.Label(inner, text="", bg=P["card"], fg=P["faint"],
                                      font=(FONT, 9), anchor="w", justify="left",
                                      wraplength=520)
        self.chg_limit_msg.pack(fill="x", pady=(8, 0))

        hab = Card(wrap, pad=0)
        hab.pack(fill="x", pady=(14, 0))
        hb = tk.Frame(hab, bg=P["card"])
        hb.pack(fill="x", padx=18, pady=16)
        ht = tk.Frame(hb, bg=P["card"])
        ht.pack(fill="x")
        tk.Label(ht, text="充电习惯（近 14 天）", bg=P["card"], fg=P["text"],
                 font=(FONT, 12, "bold")).pack(side="left")
        self.chg_score = tk.Label(ht, text="", bg=P["card"], fg=P["muted"],
                                  font=(FONT, 11, "bold"))
        self.chg_score.pack(side="right")
        self.chg_habit = tk.Label(hb, text="正在统计…", bg=P["card"], fg=P["text2"],
                                  font=(FONT, 10), anchor="w", justify="left",
                                  wraplength=540)
        self.chg_habit.pack(fill="x", pady=(8, 0))
        self.chg_advice = tk.Label(hb, text="", bg=P["card"], fg=P["amber"],
                                   font=(FONT, 10), anchor="w", justify="left",
                                   wraplength=540)
        self.chg_advice.pack(fill="x", pady=(6, 0))

        tk.Label(wrap, text="上限靠写 SMC 的 BCLM 键实现，只影响「充到多少就停」，"
                            "不改电源管理策略，随时可以改回 100%。",
                 bg=P["bg"], fg=P["faint"], font=(FONT, 9), anchor="w",
                 justify="left", wraplength=540).pack(fill="x", pady=(10, 0))

    def _bclm_now(self):
        now = time.time()
        c = getattr(self, "_bclm_cache", None)
        if c and now - c[0] < 60:
            return c[1]
        v = bclm_read()
        self._bclm_cache = (now, v)
        return v

    def update_charge_habit(self, force=False):
        if not hasattr(self, "chg_habit"):
            return
        now = time.time()
        c = getattr(self, "_habit_cache", None)
        if not force and c and now - c[0] < 300:
            st = c[1]
        else:
            st = charge_stats()
            self._habit_cache = (now, st)
        try:
            if not st.get("ready"):
                self.chg_score.configure(text="样本不足", fg=P["faint"])
                self.chg_habit.configure(
                    text="还没攒够数据。让它记录一两天（每 5 秒一条），"
                         "这里就能看出你的充电习惯。")
                self.chg_advice.configure(text="")
                return
            self.chg_habit.configure(text="\n".join([
                "插电时间　%.0f%%　（共 %.1f 天记录）"
                % (st["ac_ratio"] * 100, st["days"]),
                "满电插着　%.0f%% 的时间（≥95%% 且接着电源）"
                % (st["full_ac_ratio"] * 100),
                "高温充电　%d 分钟（≥40℃）" % st["hot_min"],
                "深度放电　%d 次（<10%%）" % st["deep_times"],
                "平均充电　%.1f W" % st["avg_chg_w"],
            ]))
            s = st["score"]
            col = P["green"] if s >= 85 else (P["amber"] if s >= 60 else P["red"])
            self.chg_score.configure(text="习惯评分 %d" % s, fg=col)
            self.chg_advice.configure(text="\n".join("· " + a for a in st["advice"]))
        except Exception:
            pass

    def refresh_charge(self, b=None):
        try:
            if b is None or not getattr(b, "ok", False):
                b = getattr(self, "battery", None)
                if b is None or not getattr(b, "ok", False):
                    b = Battery.read()
            if b is None or not getattr(b, "ok", False):
                return
            if b.on_ac:
                if b.charging == "Yes":
                    st, col, hint = ("充电中 %d%%" % b.pct, P["green"],
                                     "适配器供电，正在充进电池")
                elif b.pct >= 96:
                    st, col, hint = ("已充满 %d%%" % b.pct, P["green"],
                                     "充满后停止充电，属正常")
                else:
                    st, col, hint = ("插电未充电 %d%%" % b.pct, P["amber"],
                                     "电芯温度偏高或已到上限" if b.ncr
                                     else "插着电但没在充")
            else:
                st, col, hint = ("电池供电 %d%%" % b.pct,
                                 P["amber"] if b.pct < 20 else P["text"],
                                 "现在没接充电器")
            self.chg_rows["state"].set(st, col, hint)

            w = b.watts
            self.chg_rows["power"].set(
                ("%.1f W" % w) if w > 0 else "--",
                P["text"] if w > 0 else P["muted"],
                ("适配器标称 %d W" % b.adapter_w) if b.adapter_w else "未接电源")

            tcol = (P["red"] if b.temp_c >= 45 else
                    (P["amber"] if b.temp_c >= 40 else P["text"]))
            self.chg_rows["temp"].set(
                "%.1f ℃" % b.temp_c, tcol,
                "偏高，先散热再充" if b.temp_c >= 40 else "散热正常")

            lim = self._bclm_now()
            if lim is None:
                self.chg_rows["limit"].set("未限制", P["muted"], "一直充到 100%")
            else:
                self.chg_rows["limit"].set("%d%%" % lim, P["green"], "充到这里就停")
            self._paint_limit(lim)
            self.update_charge_habit()
        except Exception:
            pass

    def _paint_limit(self, lim):
        try:
            if not _find_bclm():
                self.chg_limit_lbl.configure(text="还没有限充工具", fg=P["muted"])
                self.chg_limit_desc.configure(
                    text="这台机器可以用 SMC 的 BCLM 键做硬件限充，需要一个小工具 bclm"
                         "（开源，几十 KB，AlDente 这类软件也是同样原理）。"
                         "点下面的按钮会调用 Homebrew 安装，装完用系统密码框提权写一次上限。")
                return
            self.chg_limit_lbl.configure(
                text=("未设置（一直充到 100%）" if lim is None
                      else "当前上限 %d%%" % lim),
                fg=P["green"] if lim else P["muted"])
            self.chg_limit_desc.configure(
                text="设成 80% 的意思是：插着电也最多充到 80%，之后充电器只给主板供电，"
                     "电池不再进电。要出远门时改回 100% 即可，不影响续航。")
        except Exception:
            pass

    def set_charge_limit(self, pct):
        if not _find_bclm():
            self.install_bclm(pct)
            return
        if not messagebox.askyesno(
                "设置充电上限",
                "把充电上限设成 %d%%？\n\n"
                "· 只影响「充到多少停」，随时可改回 100%%\n"
                "· 需要管理员密码，系统会弹窗\n"
                "· %s" % (pct, "改回充满" if pct >= 100
                          else "设好后插着电也只充到这里"),
                parent=self.root):
            return
        ok, err = bclm_write(pct)
        if ok:
            self._bclm_cache = (time.time(), pct)
            self.chg_limit_msg.configure(text="已设为 %d%%" % pct, fg=P["green"])
            self.add_event("充电上限已设为 %d%%" % pct, "green")
        else:
            self.chg_limit_msg.configure(text="没改成：%s" % err, fg=P["red"])
        self.refresh_charge()

    def install_bclm(self, pct=80):
        brew = None
        for p in ("/usr/local/bin/brew", "/opt/homebrew/bin/brew"):
            if os.path.exists(p):
                brew = p
                break
        if not brew:
            self.chg_limit_msg.configure(
                text="没找到 Homebrew。可先装 Homebrew，再执行 "
                     "brew install zackelia/formulae/bclm", fg=P["amber"])
            return
        if not messagebox.askyesno(
                "安装限充工具",
                "要安装开源小工具 bclm 吗？\n\n"
                "· 来源 github.com/zackelia/bclm，几十 KB\n"
                "· 用 Homebrew 安装，装完自动设成 %d%%\n"
                "· 不想用了随时 brew uninstall bclm" % pct,
                parent=self.root):
            return
        self.chg_limit_msg.configure(text="正在通过 Homebrew 安装，可能要一两分钟…",
                                     fg=P["muted"])

        def work():
            try:
                # 新版 Homebrew 要求先显式 tap
                subprocess.run([brew, "tap", "zackelia/formulae"],
                               capture_output=True, text=True, timeout=300)
                subprocess.run([brew, "install", "zackelia/formulae/bclm"],
                               capture_output=True, text=True, timeout=900)
            except Exception:
                pass

            def finish():
                if not _find_bclm():
                    self.chg_limit_msg.configure(
                        text="安装没成功，可稍后重试，或在终端执行 "
                             "brew install zackelia/formulae/bclm", fg=P["red"])
                    self._paint_limit(None)
                    return
                self.chg_limit_msg.configure(text="装好了，请输入密码完成设置…",
                                             fg=P["green"])
                ok2, err2 = bclm_write(pct)
                if ok2:
                    self._bclm_cache = (time.time(), pct)
                    self.chg_limit_msg.configure(text="已设为 %d%%" % pct,
                                                 fg=P["green"])
                    self.add_event("充电上限已设为 %d%%" % pct, "green")
                else:
                    self.chg_limit_msg.configure(text="装好了，但设置没成功：%s" % err2,
                                                 fg=P["amber"])
                self.refresh_charge()

            self.root.after(0, finish)

        threading.Thread(target=work, daemon=True).start()

    # ---------------- 趋势页
    # ---------------- 保养提醒 / 每日体检 / 导出 / 悬浮窗
    CARE_DEFAULTS = {"charge_alert": True, "charge_to": 80, "fullplug_alert": True,
                     "hot_alert": True, "hot_temp": 40, "monthly_cal": True}

    def care_cfg(self):
        st = _care_state()
        cfg = dict(self.CARE_DEFAULTS)
        cfg.update(st.get("cfg") or {})
        return st, cfg

    def care_set(self, key, val):
        st, cfg = self.care_cfg()
        cfg[key] = val
        st["cfg"] = cfg
        _care_save(st)

    def _care_check(self, b):
        try:
            st, cfg = self.care_cfg()
            today = time.strftime("%Y-%m-%d")
            msgs = []
            thr = to_int(cfg.get("charge_to", 80), 80)
            if cfg.get("charge_alert", True) and b.charging == "Yes" and b.pct >= thr \
                    and st.get("charge80") != today:
                msgs.append("电量已到 %d%%，可以拔掉充电器了。锂电池长期停在满电会加速老化。" % b.pct)
                st["charge80"] = today
            if cfg.get("fullplug_alert", True) and b.on_ac and b.pct >= 96 \
                    and b.charging != "Yes" and st.get("fullplug") != today:
                msgs.append("电池已充满且一直插着电。每月做一次完整充放电校准更健康。")
                st["fullplug"] = today
            hot = to_int(cfg.get("hot_temp", 40), 40)
            if cfg.get("hot_alert", True) and b.temp_c >= hot and st.get("hot") != today:
                msgs.append("电池温度 %.1f℃，高于 %d℃。高温下充放电最伤电池，先挪到通风处。"
                            % (b.temp_c, hot))
                st["hot"] = today
            if cfg.get("monthly_cal", True) and st.get("cal_last"):
                try:
                    days = (time.time() - time.mktime(
                        time.strptime(st["cal_last"], "%Y-%m-%d"))) / 86400.0
                except Exception:
                    days = 0
                if days >= 30 and st.get("cal_remind") != today[:7]:
                    msgs.append("距上次校准已有 %d 天，可以再做一次（免费，只要一个晚上）。" % int(days))
                    st["cal_remind"] = today[:7]
            if msgs:
                _care_save(st)
                for m in msgs:
                    self.add_event(m, "green")
                notify("电池医生 · 保养提醒", msgs[0])
        except Exception:
            pass

    def daily_status_text(self):
        daily_on = os.path.exists(DAILY_PLIST)
        try:
            with open(DAILY_FILE, encoding="utf-8") as f:
                d = json.load(f)
            last = "上次体检 %s，发现 %d 个问题" % (d.get("ts", "?"), len(d.get("issues", [])))
        except Exception:
            last = "还没有体检记录"
        return daily_on, last

    def maintenance_dialog(self):
        dlg = getattr(self, "_care_dlg", None)
        try:
            if dlg is not None and dlg.winfo_exists():
                dlg.destroy()
        except Exception:
            pass
        dlg = tk.Toplevel(self.root)
        self._care_dlg = dlg
        dlg.title("电池保养")
        dlg.configure(bg=P["card"])
        dlg.transient(self.root)
        dlg.resizable(False, False)
        st, cfg = self.care_cfg()
        daily_on, last = self.daily_status_text()

        pad = tk.Frame(dlg, bg=P["card"])
        pad.pack(fill="both", expand=True, padx=24, pady=18)
        tk.Label(pad, text="保养与提醒", bg=P["card"], fg=P["text"],
                 font=(FONT, 16, "bold")).pack(anchor="w")
        tk.Label(pad, text="电池的寿命一半取决于怎么充。这几条都是可以自己做的，不需要装别的东西。",
                 bg=P["card"], fg=P["muted"], font=(FONT, 10), justify="left",
                 wraplength=430).pack(anchor="w", pady=(2, 8))

        body = tk.Frame(pad, bg=P["card"])
        body.pack(fill="x")
        self._care_rows = {}

        def make_row(key, title, desc, gap=9):
            f = tk.Frame(body, bg=P["card"])
            f.pack(fill="x", pady=(0, gap))
            ck = CheckBox(f, on=bool(cfg.get(key)),
                          command=lambda v, k=key: self.care_set(k, v))
            ck.pack(side="left", anchor="n", pady=(2, 0))
            t = tk.Frame(f, bg=P["card"])
            t.pack(side="left", fill="x", expand=True, padx=(8, 0))
            tk.Label(t, text=title, bg=P["card"], fg=P["text"],
                     font=(FONT, 10, "bold"), anchor="w").pack(fill="x")
            tk.Label(t, text=desc, bg=P["card"], fg=P["muted"], font=(FONT, 9),
                     anchor="w", justify="left", wraplength=384).pack(fill="x")
            self._care_rows[key] = ck
            return t

        make_row("charge_alert", "充到一定电量就提醒拔电",
                 "锂电池长期停在满电最伤容量。到阈值弹一次通知，一天只提醒一次。", gap=2)
        thr_box = tk.Frame(body, bg=P["card"])
        thr_box.pack(fill="x", padx=(26, 0), pady=(0, 10))
        tk.Label(thr_box, text="提醒阈值", bg=P["card"], fg=P["faint"],
                 font=(FONT, 9)).pack(side="left", padx=(0, 8))
        for val in (70, 80, 90):
            active = to_int(cfg.get("charge_to"), 80) == val
            RButton(thr_box, "%d%%" % val,
                    lambda v=val: self.care_pick_thr(v),
                    "primary" if active else "ghost", size=9,
                    height=25, padx=10, width=48).pack(side="left", padx=(0, 5))

        make_row("fullplug_alert", "长期插电时提醒一次",
                 "一天最多一次。整天挂着电源的人，电池会一直处于高压状态。")
        make_row("hot_alert", "温度过高时提醒",
                 "默认 40℃ 以上。边充边烤是最快的衰减方式，尤其放在被子或腿上。")
        make_row("monthly_cal", "每月提醒做一次校准",
                 "只在你做过第一次校准之后开始提醒，避免刚装就唠叨。")

        lf = tk.Frame(body, bg=P["card"])
        lf.pack(fill="x", pady=(0, 2))
        CheckBox(lf, on=login_agent_on(),
                 command=self.toggle_login).pack(side="left", anchor="n", pady=(2, 0))
        lt = tk.Frame(lf, bg=P["card"])
        lt.pack(side="left", fill="x", expand=True, padx=(8, 0))
        tk.Label(lt, text="登录时自动启动并后台记录", bg=P["card"], fg=P["text"],
                 font=(FONT, 10, "bold"), anchor="w").pack(fill="x")
        self._login_lbl = tk.Label(
            lt, bg=P["card"], fg=P["muted"], font=(FONT, 9), anchor="w",
            justify="left", wraplength=384,
            text=("已开启：下次登录会自动收进右上角小窗继续采样。"
                  if login_agent_on() else
                  "断电取证只在程序运行时有效。开启后登录自动后台记录，不弹大窗口。"))
        self._login_lbl.pack(fill="x")

        line = tk.Frame(pad, bg=P["line2"], height=1)
        line.pack(fill="x", pady=(6, 8))
        cal_last = st.get("cal_last") or "还没做过"
        tk.Label(pad, text="上次校准：%s　｜　每日体检：%s"
                          % (cal_last, "已开启" if daily_on else "未开启"),
                 bg=P["card"], fg=P["text2"], font=(FONT, 10)).pack(anchor="w")
        tk.Label(pad, text=last, bg=P["card"], fg=P["faint"], font=(FONT, 9),
                 wraplength=430, justify="left").pack(anchor="w", pady=(2, 0))

        btns = tk.Frame(pad, bg=P["card"])
        btns.pack(fill="x", pady=(12, 0))
        if daily_on:
            RButton(btns, "关闭每日体检", self.uninstall_daily, "secondary",
                    size=10).pack(side="left")
        else:
            RButton(btns, "开启每日体检", self.install_daily, "primary",
                    size=10).pack(side="left")
        RButton(btns, "校准向导", self.calibration_dialog, "secondary",
                size=10).pack(side="left", padx=8)
        RButton(btns, "完成", dlg.destroy, "ghost", size=10).pack(side="right")

        dlg.update_idletasks()
        w, h = 496, 560
        x = self.root.winfo_rootx() + (self.root.winfo_width() - w) // 2
        y = self.root.winfo_rooty() + max(16, (self.root.winfo_height() - h) // 3)
        dlg.geometry("%dx%d+%d+%d" % (w, h, x, y))

    def toggle_login(self, on):
        err = install_login_agent() if on else uninstall_login_agent()
        if err:
            messagebox.showerror("开机自启", "设置失败：%s" % err, parent=self.root)
            on = not on
        else:
            self.add_event("开机自启：" + ("已开启，下次登录生效" if on else "已关闭"), "info")
        try:
            self._login_lbl.configure(
                text=("已开启：下次登录会自动收进右上角小窗继续采样。" if on else
                      "已关闭。断电取证只在程序运行时有效，关掉后可能漏记。"),
                fg=P["muted"] if on else P["amber"])
        except Exception:
            pass

    def care_pick_thr(self, val):
        self.care_set("charge_to", val)
        self.maintenance_dialog()

    def install_daily(self):
        try:
            err = install_daily_agent()
            if err:
                raise RuntimeError(err)
            self.add_event("每日体检已开启：每天 9:00 自动检查。", "green")
            notify("电池医生", "每日体检已开启，每天 9:00 自动检查")
        except Exception as e:
            messagebox.showerror("开启失败", str(e))
            return
        self.maintenance_dialog()

    def uninstall_daily(self):
        try:
            subprocess.run(["/bin/launchctl", "unload", DAILY_PLIST],
                           capture_output=True, timeout=10)
            if os.path.exists(DAILY_PLIST):
                os.unlink(DAILY_PLIST)
            self.add_event("每日体检已关闭。", "info")
        except Exception as e:
            messagebox.showerror("关闭失败", str(e))
            return
        self.maintenance_dialog()

    def calibration_guide(self):
        messagebox.showinfo(
            "月度校准引导",
            "电池的电量计会随着时间漂移，每月做一次完整充放电可以让\n"
            "「健康度」「剩余电量」显示得更准：\n\n"
            "1. 正常使用，把电量用到 10% 以下（不必等到自动关机）\n"
            "2. 关机或睡眠状态下，连续充电 6–8 小时直到 100%\n"
            "3. 开机回到「体检概览」，看「满充容量」有没有回升\n\n"
            "注意：这块电池已提示「建议维修」，校准只能校准显示，\n"
            "无法让老化电芯恢复容量。")

    def export_pdf(self):
        text = self.build_report_text()
        name = "电池医生诊断报告-%s.pdf" % time.strftime("%Y%m%d-%H%M")
        try:
            from tkinter import filedialog
            path = filedialog.asksaveasfilename(
                title="导出诊断报告", initialfile=name,
                initialdir=os.path.expanduser("~/Desktop"),
                defaultextension=".pdf", filetypes=[("PDF 文件", "*.pdf")],
                parent=self.root)
        except Exception:
            path = os.path.join(os.path.expanduser("~/Desktop"), name)
        if not path:
            return
        try:
            text_to_pdf(text, path)
            self.add_event("诊断报告已导出 PDF：%s" % os.path.basename(path), "green")
            notify("电池医生", "诊断报告已导出 PDF")
        except Exception as e:
            messagebox.showerror("导出失败", "PDF 生成失败：%s\n\n"
                                 "可以先点「复制诊断报告」粘贴备用。" % e)

    def export_chart(self):
        rows = self._load_csv()
        if len(rows) < 2:
            messagebox.showinfo("导出图表", "还没有足够的采样数据，先去「体检概览」点「开始记录」。")
            return
        win = tk.Toplevel(self.root)
        win.title("导出预览")
        win.configure(bg="#FFFFFF")
        win.geometry("960x540+60+60")
        cv = tk.Canvas(win, width=960, height=540, bg="#FFFFFF", highlightthickness=0)
        cv.pack(fill="both", expand=True)
        # PostScript 不支持中文，导出图一律用 ASCII 标签
        cv.create_rectangle(0, 0, 960, 540, fill="#FFFFFF", outline="")
        pad_l, pad_r, pad_t = 64, 28, 56
        cw = 960 - pad_l - pad_r
        total = 540 - pad_t - 90
        top_h = total * 0.54
        bot_h = total * 0.40
        cv.create_text(pad_l, 24, anchor="w", fill="#1C1C1E",
                       font=("Helvetica", 16, "bold"),
                       text="Battery Doctor - Power Trend  %s" % time.strftime("%Y-%m-%d"))
        pct = [to_int(r.get("pct"), 0) for r in rows]
        ma = [to_int(r.get("mA"), 0) for r in rows]
        self._plot_export(cv, pad_l, pad_t, cw, top_h, pct, "Battery (%)", "#3D6C97", 0, 100)
        self._plot_export(cv, pad_l, pad_t + top_h + 40, cw, bot_h, ma, "Current (mA)",
                          "#A9721C", None, None)
        base_y = pad_t + top_h + 40 + bot_h + 16
        hits = [i for i, r in enumerate(rows)
                if "AC_BUT_DISCHARGING" in (r.get("note") or "")]
        for i in hits:
            x = pad_l + cw * i / max(1, len(rows) - 1)
            cv.create_line(x, pad_t, x, base_y, fill="#F0CDC7", width=1)
            cv.create_oval(x - 3, base_y - 3, x + 3, base_y + 3,
                           fill="#B8554A", outline="")
        cv.create_text(pad_l, base_y + 12, anchor="w", fill="#AFAFB4",
                       font=("Helvetica", 10),
                       text="red dots = discharging while plugged in (%d)" % len(hits))
        cv.create_text(pad_l + cw, base_y + 12, anchor="e", fill="#AFAFB4",
                       font=("Helvetica", 10),
                       text="%s -> %s" % (rows[0]["iso_time"][11:16],
                                          rows[-1]["iso_time"][11:16]))
        win.update()
        out = os.path.join(os.path.expanduser("~/Desktop"),
                           "电池医生趋势图-%s.png" % time.strftime("%Y%m%d-%H%M"))
        try:
            canvas_to_png(cv, out)
            self.add_event("趋势图已导出：%s" % os.path.basename(out), "green")
            notify("电池医生", "趋势图已保存到桌面")
        except Exception as e:
            messagebox.showerror("导出失败", str(e))
        finally:
            win.destroy()

    def _plot_export(self, c, x0, y0, w, h, series, title, color, vmin, vmax):
        n = len(series)
        lo = min(series) if vmin is None else vmin
        hi = max(series) if vmax is None else vmax
        if hi - lo < 1e-6:
            hi = lo + 1
        pad = (hi - lo) * 0.14
        if vmin is None:
            lo -= pad
        if vmax is None:
            hi += pad
        for i in range(4):
            y = y0 + h * i / 3.0
            c.create_line(x0, y, x0 + w, y, fill="#EFEFE9", width=1)
            v = hi - (hi - lo) * i / 3.0
            c.create_text(x0 - 8, y, text="%.0f" % v, fill="#AFAFB4",
                          font=("Helvetica", 9), anchor="e")
        pts = []
        for i, val in enumerate(series):
            x = x0 + w * i / max(1, n - 1)
            y = y0 + h * (1 - (val - lo) / (hi - lo))
            pts += [x, y]
        if len(pts) >= 4:
            c.create_line(*pts, fill=color, width=2, smooth=True)
        c.create_text(x0, y0 - 16, anchor="w", fill="#4A4A4E",
                      font=("Helvetica", 11, "bold"), text=title)

    # ---------------- 悬浮小窗
    def toggle_floatwin(self):
        fw = getattr(self, "_fw", None)
        if fw is not None:
            try:
                fw.destroy()
            except Exception:
                pass
            self._fw = None
            self.add_event("悬浮小窗已关闭。", "info")
            return
        fw = tk.Toplevel(self.root)
        self._fw = fw
        fw.overrideredirect(True)
        fw.attributes("-topmost", True)
        sw = fw.winfo_screenwidth()
        fw.geometry("104x34+%d+10" % (sw - 124))
        fw.configure(bg=P["card"])
        cv = tk.Canvas(fw, width=104, height=34, bg=P["card"], highlightthickness=1,
                       highlightbackground=P["line"])
        cv.pack(fill="both", expand=True)
        self._fw_cv = cv
        self._fw_drag_from = None
        cv.bind("<Button-1>", self._fw_press)
        cv.bind("<B1-Motion>", self._fw_motion)
        cv.bind("<Double-Button-1>", lambda e: self.toggle_floatwin())
        self._fw_update()
        self.add_event("悬浮小窗已开启：可拖动，双击关闭。", "green")

    def _fw_press(self, e):
        fw = getattr(self, "_fw", None)
        if fw:
            self._fw_drag_from = (e.x_root - fw.winfo_x(), e.y_root - fw.winfo_y())

    def _fw_motion(self, e):
        fw = getattr(self, "_fw", None)
        if fw and self._fw_drag_from:
            fw.geometry("+%d+%d" % (e.x_root - self._fw_drag_from[0],
                                    e.y_root - self._fw_drag_from[1]))

    def _fw_update(self):
        fw = getattr(self, "_fw", None)
        if fw is None:
            return
        try:
            if not fw.winfo_exists():
                self._fw = None
                return
        except Exception:
            self._fw = None
            return
        cv = self._fw_cv
        cv.delete("all")
        b = getattr(self, "battery", None)
        if not b:
            cv.create_text(52, 17, text="--", fill=P["muted"], font=(FONT, 12, "bold"))
            return
        col = P["accent"] if b.on_ac else (P["amber"] if b.pct < 20 else P["green"])
        if b.on_ac and b.ma < -300:
            col = P["red"]
        txt = "%d%%" % b.pct
        if b.limit is not None and b.limit < 80:
            txt += " %d%%" % b.limit
        cv.create_oval(10, 14, 17, 21, fill=col, outline="")
        cv.create_text(24, 17, anchor="w", text=txt, fill=P["text"],
                       font=(FONT, 12, "bold"))

    # ---------------- 存储建议 / 系统清理脚本
    def copy_storage_advice(self):
        rows = {name: kb for name, _p, kb in getattr(self, "_scan_result", [])}
        try:
            st = os.statvfs("/")
            free = human(st.f_bavail * st.f_frsize // 1024)
        except Exception:
            free = "?"
        lines = [
            "磁盘清理建议（电池医生 %s 生成于 %s）" % (VERSION, time.strftime("%Y-%m-%d %H:%M")),
            "当前可用空间：%s" % free,
            "",
            "一、可以放心清理（先移到废纸篓观察几天）：",
            "  · 用户缓存（%s）：关闭相关应用后可整个删除，会自动重建" % human(rows.get("用户缓存", 0)),
            "  · 废纸篓（%s）：清空立即释放" % human(rows.get("废纸篓", 0)),
            "  · 系统日志（%s）：保留最近一个月，旧的可删" % human(rows.get("系统日志", 0)),
            "",
            "二、要在应用内清理，不要直接删目录：",
            "  · 微信数据（%s）：微信 → 设置 → 通用 → 存储空间" % human(rows.get("微信数据", 0)),
            "  · 企业微信（%s）：企业微信 → 设置 → 存储空间" % human(rows.get("企业微信", 0)),
            "  · Docker（%s）：终端执行 docker system prune" % human(rows.get("Docker", 0)),
            "",
            "三、人工过一遍：",
            "  · 下载文件夹（%s）：旧安装包、大文件按需删除" % human(rows.get("下载", 0)),
            "",
            "四、也可以直接用本程序清：存储空间页 → 右上角「清理磁盘…」",
            "    先扫描出每一项多大，再逐项勾选，确认一次才动手。危险项默认不勾。",
        ]
        self.root.clipboard_clear()
        self.root.clipboard_append("\n".join(lines))
        self.add_event("清理建议已复制到剪贴板。", "green")

    def gen_system_script(self):
        exist = [p for p in SYSTEM_AGENTS if os.path.exists(p)]
        if not exist:
            self.add_event("没有发现需要处理的系统级启动项。", "info")
            messagebox.showinfo("生成脚本", "没有发现需要处理的系统级启动项。")
            return
        lines = [
            "#!/bin/bash",
            "# 电池医生生成：关闭 %d 个系统级后台启动项" % len(exist),
            "# 服务先停止，plist 移到 ~/Library/.batterydoctor-backup-system，",
            "# 想还原时把文件移回原路径即可。",
            "set -e",
            'BK="$HOME/Library/.batterydoctor-backup-system"',
            'mkdir -p "$BK"',
            'echo "正在停用系统级后台项（需要管理员密码）"',
            "",
        ]
        for p in exist:
            lines += [
                'echo "→ %s"' % os.path.basename(p),
                'sudo launchctl unload "%s" 2>/dev/null || true' % p,
                'sudo mv "%s" "$BK/" 2>/dev/null || true' % p,
                "",
            ]
        lines += ['echo "完成。备份目录：$BK"', ""]
        path = os.path.join(os.path.expanduser("~/Desktop"), "关闭系统级启动项.sh")
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            os.chmod(path, 0o755)
        except Exception as e:
            messagebox.showerror("生成失败", str(e))
            return
        self.root.clipboard_clear()
        self.root.clipboard_append('sudo bash "%s"' % path)
        self.add_event("清理脚本已写到桌面，运行命令已复制到剪贴板。", "green")
        notify("电池医生", "清理脚本已写到桌面，运行命令已复制")
        subprocess.run(["/usr/bin/open", os.path.expanduser("~/Desktop")])

    def _build_trend(self, page):
        self.trend_sub, _ = self._header(
            page, "趋势记录",
            "记录每一次电量与电流变化，断电前那一刻的数据也会保留。",
            [("export", "导出图表", self.export_chart, "secondary"),
             ("refresh", "刷新", self.draw_trend, "ghost")])

        wrap = tk.Frame(page, bg=P["bg"])
        wrap.pack(fill="both", expand=True, padx=26, pady=(0, 22))
        card = Card(wrap, pad=0)
        card.pack(fill="both", expand=True)
        self.trend_canvas = tk.Canvas(card, bg=P["card"], highlightthickness=0, height=420)
        self.trend_canvas.pack(fill="both", expand=True, padx=12, pady=12)
        self.trend_canvas.bind("<Configure>", lambda e: self.draw_trend())

        self.trend_hint = tk.Label(wrap, text="", bg=P["bg"], fg=P["faint"],
                                   font=(FONT, 10), anchor="w")
        self.trend_hint.pack(fill="x", pady=(10, 0))

    def _load_csv(self, limit=420):
        if not os.path.exists(CSV):
            return []
        rows = []
        try:
            with open(CSV, encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    rows.append(r)
        except Exception:
            return []
        return rows[-limit:]

    def draw_trend(self):
        c = self.trend_canvas
        w = max(400, c.winfo_width())
        h = max(320, c.winfo_height())
        c.delete("all")
        rows = self._load_csv()
        if len(rows) < 2:
            c.create_text(w / 2, h / 2 - 16, text="还没有采样数据",
                          fill=P["text2"], font=(FONT, 14, "bold"))
            c.create_text(w / 2, h / 2 + 12,
                          text="回到「体检概览」，点一下「开始记录」，之后这里会画出电量与电流曲线。",
                          fill=P["faint"], font=(FONT, 11), justify="center")
            self.trend_hint.configure(text="")
            return

        pct = [to_int(r.get("pct"), 0) for r in rows]
        ma = [to_int(r.get("mA"), 0) for r in rows]
        pad_l, pad_r, pad_t = 54, 24, 34
        cw = w - pad_l - pad_r
        # 预留底部说明区，避免文字被裁切
        total = h - pad_t - 108
        top_h = total * 0.54
        bot_h = total * 0.40

        self._legend(c, pad_l, pad_t - 22, "电量 %", P["blue"])
        self._plot(c, pad_l, pad_t, cw, top_h, pct, "电量（%）", P["blue"], 0, 100,
                   fill=True)
        self._legend(c, pad_l, pad_t + top_h + 22, "电流 mA", P["amber"])
        self._plot(c, pad_l, pad_t + top_h + 44, cw, bot_h, ma, "电流（mA）", P["amber"],
                   None, None, fill=False)

        base_y = pad_t + top_h + 44 + bot_h + 14
        hits = [i for i, r in enumerate(rows) if "AC_BUT_DISCHARGING" in (r.get("note") or "")]
        for i in hits:
            x = pad_l + cw * i / max(1, len(rows) - 1)
            c.create_line(x, pad_t, x, base_y, fill=P["red_line"], width=1)
            c.create_oval(x - 3, base_y - 3, x + 3, base_y + 3, fill=P["red"], outline="")
        c.create_text(pad_l, base_y + 14, anchor="w", fill=P["faint"],
                      font=(FONT, 10),
                      text="竖线与红点 = 检测到「插着电源却在放电」的时刻，共 %d 次" % len(hits))
        c.create_text(pad_l + cw, base_y + 14, anchor="e", fill=P["faint"],
                      font=(FONT, 10),
                      text="%s → %s" % (rows[0]["iso_time"][11:16],
                                        rows[-1]["iso_time"][11:16]))
        self.trend_hint.configure(
            text="共 %d 个采样点。曲线突然下坠的位置，就是断电前那一刻。" % len(rows))

    def _legend(self, c, x, y, text, color):
        c.create_oval(x, y + 3, x + 7, y + 10, fill=color, outline="")
        c.create_text(x + 13, y + 6, text=text, anchor="w", fill=P["text2"],
                      font=(FONT, 11, "bold"))

    def _plot(self, c, x0, y0, w, h, series, title, color, vmin, vmax, fill=False):
        n = len(series)
        lo = min(series) if vmin is None else vmin
        hi = max(series) if vmax is None else vmax
        if hi - lo < 1e-6:
            hi = lo + 1
        pad = (hi - lo) * 0.14
        if vmin is None:
            lo -= pad
        if vmax is None:
            hi += pad

        for i in range(4):
            y = y0 + h * i / 3.0
            c.create_line(x0, y, x0 + w, y, fill=P["line2"], width=1)
            fmt = "%.1f" if (hi - lo) < 5 else "%.0f"
            c.create_text(x0 - 8, y, text=fmt % (hi - (hi - lo) * i / 3.0),
                          fill=P["faint"], font=(MONO, 8), anchor="e")

        pts = []
        for i, v in enumerate(series):
            x = x0 + w * i / max(1, n - 1)
            y = y0 + h - h * (v - lo) / (hi - lo)
            pts.extend([x, y])

        if len(pts) >= 4 and fill:
            poly = [x0, y0 + h] + pts + [x0 + w, y0 + h]
            c.create_polygon(poly, fill=P["blue_soft"], outline="")
        if len(pts) >= 4:
            c.create_line(*pts, fill=color, width=1.6)
            c.create_text(x0 + w, y0 - 2, text="最新 %.0f" % series[-1],
                          fill=color, font=(FONT, 10), anchor="ne")

    # ---------------- 自测
    def _selftest(self):
        b = getattr(self, "battery", None)
        procs, perr = read_processes()
        out = {
            "banner": self.st_title.cget("text"),
            "desc": self.st_desc.cget("text"),
            "rows": {k: v.val.cget("text") for k, v in self.rows.items()},
            "hints": {k: v.hint.cget("text") for k, v in self.rows.items()},
            "pct": b.pct if b else None,
            "health": b.health if b else None,
            "ma": b.ma if b else None,
            "procs_ok": procs is not None,
            "procs_err": perr,
            "procs_count": len(procs) if procs else 0,
            "procs_top": procs[0][4] if procs else None,
            "startup_items": len(self._scan_startup()),
            "csv_rows": len(self._load_csv()),
            "pages": list(self.pages.keys()),
        }
        with open("/tmp/bd_selftest.json", "w") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        self.root.destroy()

    def _smoke(self):
        """遍历所有页面，捕获任何渲染异常"""
        report = {"errors": [], "counts": {}}
        for key in ["overview", "battery", "procs", "storage", "startup",
                    "network", "trend"]:
            try:
                self.show_page(key)
                self.root.update_idletasks()
                self.root.update()
                report["counts"][key] = len(list(walk(self.pages[key])))
            except Exception as e:
                report["errors"].append("%s: %r" % (key, e))
        try:
            self.grab_instant()
            report["instant_started"] = True
        except Exception as e:
            report["errors"].append("instant: %r" % (e,))
        self._smoke_report = report

        # 打开一键优化弹窗（演练模式，不实际改动）
        try:
            self.one_click_optimize()
            self.root.after(9000, self._smoke_opt)
        except Exception as e:
            report["errors"].append("optdialog: %r" % (e,))
            self._write_smoke()

    def _smoke_opt(self):
        dlg = getattr(self, "_optdlg", None)
        rep = self._smoke_report
        try:
            if dlg is not None and dlg.winfo_exists():
                rep["opt_counts"] = dlg.counts
                rep["opt_rows"] = [(r.title.cget("text"), r.detail.cget("text"))
                                   for r in dlg.rows]
                rep["opt_verdict"] = dlg.verdict_lbl.cget("text")
                rep["report_path"] = dlg.report_path
                dlg._close()
            else:
                rep["errors"].append("optdialog: 弹窗未创建")
        except Exception as e:
            rep["errors"].append("optdialog-read: %r" % (e,))
        self._write_smoke()

    def _write_smoke(self):
        with open("/tmp/bd_smoke.json", "w") as f:
            json.dump(self._smoke_report, f, ensure_ascii=False, indent=1)
        self.mark_clean_stop()
        self.root.destroy()


def main():
    if "--daily" in sys.argv:
        daily_checkup()
        return
    if "--install-daily" in sys.argv:
        err = install_daily_agent()
        print("每日体检注册：" + ("成功" if not err else err))
        return
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
