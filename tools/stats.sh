#!/usr/bin/env bash
# 统计下载量 —— 不需要任何后端、任何追踪代码。
#
# 原理：安装包是从你自己的服务器上发出去的，nginx 早就把每一次下载
# 记在 access.log 里了。这里只是远程读一遍日志（只读，不改任何东西），
# 数出「完整下载」「续传片段」「独立 IP」「更新检查次数」。
#
# 用法：
#   bash tools/stats.sh              # 统计全部日志
#   bash tools/stats.sh 7            # 只看最近 7 天的日志文件
#   BD_HOST=root@1.2.3.4 bash tools/stats.sh
#
# 注意：独立 IP ≠ 独立人数。同一个人的动态 IP、IPv6 临时地址会算成多个；
# 公司/学校共用一个出口 IP 的又会算成一个。它是「量级参考」，不是精确人数。

set -u
HOST="${BD_HOST:-root@47.95.66.103}"
SITE="${BD_SITE:-/battery}"
DAYS="${1:-0}"

ssh -o BatchMode=yes -o ConnectTimeout=10 "$HOST" "SITE='$SITE' DAYS='$DAYS' python3 -" <<'PY'
import collections
import glob
import gzip
import os
import re
import sys

site = os.environ.get("SITE", "/battery")
days = int(os.environ.get("DAYS", "0") or 0)

pat = re.compile(r'^(\S+) \S+ \S+ \[([^\]]+)\] "(\S+) (\S+)[^"]*" (\d+) (\d+)')
files = sorted(glob.glob("/var/log/nginx/access.log*"))
if days > 0:
    files = files[-days:]

dl = collections.Counter()                     # 文件 -> 请求数
dl_ip = collections.defaultdict(set)
full = collections.Counter()                   # 200 = 从头下
part = collections.Counter()                   # 206 = 断点续传
page_ip = collections.defaultdict(set)
dl_all_ip = set()
upd_ip = set()
upd_n = 0
day = collections.Counter()


def lines():
    for f in files:
        if f.endswith(".gz"):
            with gzip.open(f, "rt", errors="ignore") as fh:
                yield from fh
        else:
            with open(f, errors="ignore") as fh:
                yield from fh


for line in lines():
    m = pat.match(line)
    if not m:
        continue
    ip, ts, method, path, status, size = m.groups()
    if path.startswith(site + "/downloads/"):
        name = path.rsplit("/", 1)[-1]
        dl[name] += 1
        dl_ip[name].add(ip)
        dl_all_ip.add(ip)
        if status == "200":
            full[name] += 1
            day[ts.split(":")[0]] += 1
        elif status == "206":
            part[name] += 1
    elif path == site + "/version.json":
        upd_n += 1
        upd_ip.add(ip)
    elif path.rstrip("/") == site:
        page_ip["p"].add(ip)

print("已读日志 %d 个（含轮转归档）\n" % len(files))
print("%-32s %8s %8s %8s %8s" % ("文件", "请求", "完整下载", "续传", "独立IP"))
print("-" * 70)
tot_full = tot_ip = 0
for name, c in dl.most_common():
    print("%-32s %8d %8d %8d %8d" % (name, c, full[name], part[name], len(dl_ip[name])))
    tot_full += full[name]
    tot_ip += len(dl_ip[name])
print("-" * 70)
print("合计：完整下载 %d 次，涉及 %d 个独立 IP" % (tot_full, len(dl_all_ip)))

print("\n官网访问：%d 个独立 IP" % len(page_ip["p"]))
print("更新检查：%d 次 / %d 个独立 IP（≈ 开了自动检查的活跃安装数下界）"
      % (upd_n, len(upd_ip)))

if day:
    print("\n按天完整下载：")
    for d, c in sorted(day.items()):
        print("  %s  %d" % (d, c))
PY
