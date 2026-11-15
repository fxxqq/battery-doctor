#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""电池医生下载量统计 —— 服务器端，只读 nginx 日志。

设计要点：
1. 不装任何客户端埋点。数字来自「安装包是从这台服务器发出去的」这一事实。
2. nginx 日志会轮转（默认保留约 10 天），所以不能每次都重算总数，
   否则旧日志一删数字就倒退。这里用 state 文件按天存，每天只增不减。
3. 只统计完整的下载请求（HTTP 200）；断点续传（206）不算一次新下载。
4. 输出一个 stats.json 给官网读，前端没有任何第三方脚本。

由 cron 每日调用一次，也可以手动执行。
"""

import collections
import glob
import gzip
import json
import os
import re
import sys
import time

SITE_DIR = "/opt/pocket-code/dist/battery"
OUT = os.path.join(SITE_DIR, "stats.json")
STATE = "/opt/pocket-code/var/battery-dl-state.json"
LOG_GLOB = "/var/log/nginx/access.log*"
PREFIX = "/battery/downloads/"

PAT = re.compile(r'^(\S+) \S+ \S+ \[([^\]]+)\] "(\S+) (\S+) [^"]*" (\d+) (\d+)')
MONTHS = {m: i + 1 for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}


def read_state():
    try:
        with open(STATE, encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict) and isinstance(d.get("days"), dict):
            return d
    except Exception:
        pass
    return {"since": None, "days": {}}


def log_lines():
    for path in sorted(glob.glob(LOG_GLOB)):
        if path.endswith(".gz"):
            with gzip.open(path, "rt", errors="ignore") as fh:
                yield from fh
        else:
            with open(path, errors="ignore") as fh:
                yield from fh


def day_key(ts):
    """'15/Nov/2026:22:30:01 +0800' -> ('2026-11-15', 可排序)"""
    d = ts.split(":")[0]                      # 15/Nov/2026
    try:
        dd, mon, yy = d.split("/")
        return "%s-%02d-%02d" % (yy, MONTHS[mon[:3]], int(dd))
    except Exception:
        return d


def classify(name):
    n = name.lower()
    if n.endswith(".dmg"):
        return "mac"
    if n.endswith((".exe", ".zip")):
        return "win"
    return None


def main():
    st = read_state()
    days = st.get("days", {})
    seen = collections.defaultdict(lambda: {"mac": 0, "win": 0})

    total_req = 0
    for line in log_lines():
        m = PAT.match(line)
        if not m:
            continue
        _ip, ts, _meth, path, status, _size = m.groups()
        if not path.startswith(PREFIX) or status != "200":
            continue
        total_req += 1
        kind = classify(path.rsplit("/", 1)[-1])
        if kind:
            seen[day_key(ts)][kind] += 1

    # 同一天只增不减：日志还在时数字会涨，日志轮转掉了就用历史值
    for day, c in seen.items():
        old = days.get(day) or {}
        days[day] = {"mac": max(int(old.get("mac", 0)), c["mac"]),
                     "win": max(int(old.get("win", 0)), c["win"])}

    mac = sum(int(d.get("mac", 0)) for d in days.values())
    win = sum(int(d.get("win", 0)) for d in days.values())
    since = min(days) if days else None

    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump({"since": since, "days": days,
                   "updated": int(time.time())}, f, ensure_ascii=False)

    out = {"total": mac + win, "mac": mac, "win": win,
           "since": since,
           "updated": time.strftime("%Y-%m-%dT%H:%M:%S")}
    os.makedirs(SITE_DIR, exist_ok=True)
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    os.replace(tmp, OUT)

    print("本次扫描完整下载请求 %d 条；累计 macOS %d / Windows %d / 合计 %d（起始 %s）"
          % (total_req, mac, win, mac + win, since))
    return 0


if __name__ == "__main__":
    sys.exit(main())
