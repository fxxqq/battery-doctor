#!/bin/bash
# powerwatch.sh - 电源/电池异常监控与断电取证
# 用法:
#   ./powerwatch.sh              常驻采样（默认 5 秒一次）
#   ./powerwatch.sh -i 2         自定义采样间隔
#   ./powerwatch.sh report       打印健康摘要
#   ./powerwatch.sh incidents    查看历次异常断电记录
#   ./powerwatch.sh install      注册为开机自启的 LaunchAgent
#   ./powerwatch.sh uninstall    移除 LaunchAgent

BASE="$HOME/Library/Logs/PowerWatch"
CSV="$BASE/power.csv"
INC="$BASE/incidents.log"
BEAT="$BASE/.heartbeat"
CLEAN="$BASE/.clean_stop"
LOCK="$BASE/.running"
INTERVAL=5
MAX_LINES=120000
STALE_SEC=120

LABEL="com.local.powerwatch"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
SELF="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"

mkdir -p "$BASE"

LAST_LIMIT="na"
LIMIT_TICK=0

# 无符号 64 位电流 -> 带符号 mA（仅负值需要 bc）
signed_ma() {
  case "$1" in
    ''|*[!0-9]*) echo "0" ;;
    18446744073*) echo "$(echo "$1 - 18446744073709551616" | bc)" ;;
    *) echo "$1" ;;
  esac
}

# 一次性解析 ioreg，输出以 | 分隔的字段
read_battery() {
  local raw
  raw=$(ioreg -rn AppleSmartBattery -w0 2>/dev/null | tr ',' '\n' | awk '
    function v(s) { sub(/^[^=]*=[ \t]*/,"",s); gsub(/[" \t\r]/,"",s); sub(/[}\]]+$/,"",s); return s }
    /"AppleRawCurrentCapacity"/ { if (cur=="") { cur=v($0) } next }
    /"AppleRawMaxCapacity"/     { if (mx=="")  { mx=v($0) }  next }
    /"DesignCapacity"/          { if (dsg=="") { dsg=v($0) } next }
    /"InstantAmperage"/         { if (amp=="") { amp=v($0) } next }
    /"Voltage"/                 { if (vlt=="") { vlt=v($0) } next }
    /"Temperature"/             { if (tmp=="") { tmp=v($0) } next }
    /"CycleCount"/              { if (cyc=="") { cyc=v($0) } next }
    /"ExternalConnected"/       { if (ext=="") { ext=v($0) } next }
    /"IsCharging"/              { if (chg=="") { chg=v($0) } next }
    /"AdapterID"/               { if (aid=="") { aid=v($0) } next }
    END { printf "%s|%s|%s|%s|%s|%s|%s|%s|%s|%s", cur,mx,dsg,amp,vlt,tmp,cyc,ext,chg,aid }
  ')
  [ -z "$raw" ] && return 1

  local IFS_OLD="$IFS"
  IFS='|'
  set -- $raw
  IFS="$IFS_OLD"

  CUR_MAH="${1:-0}"
  MAX_MAH="${2:-0}"
  DESIGN_MAH="${3:-0}"
  AMP_RAW="${4:-0}"
  VOLT_MV="${5:-0}"
  TEMP_DS="${6:-0}"
  CYCLE="${7:-0}"
  EXT="${8:-No}"
  CHARGING="${9:-No}"
  local aid="${10:-}"

  case "$aid" in ''|*[!0-9]*) ADAPTER_ID="na" ;; *) ADAPTER_ID="$aid" ;; esac
  [ -z "$MAX_MAH" ] && MAX_MAH=0
  [ -z "$DESIGN_MAH" ] && DESIGN_MAH=0

  MA=$(signed_ma "$AMP_RAW")

  if [ "$EXT" = "Yes" ]; then SOURCE="AC"; else SOURCE="BAT"; fi

  if [ "$CUR_MAH" -gt 0 ] 2>/dev/null && [ "$MAX_MAH" -gt 0 ] 2>/dev/null; then
    PCT=$(( CUR_MAH * 100 / MAX_MAH ))
  else
    PCT="na"
  fi

  if [ "$TEMP_DS" -gt 0 ] 2>/dev/null; then
    TEMP_C=$(echo "scale=1; $TEMP_DS / 100" | bc)
  else
    TEMP_C="na"
  fi

  if [ "$DESIGN_MAH" -gt 0 ] 2>/dev/null && [ "$MAX_MAH" -gt 0 ] 2>/dev/null; then
    HEALTH=$(echo "scale=0; $MAX_MAH * 100 / $DESIGN_MAH" | bc)
  else
    HEALTH="na"
  fi

  # CPU 限速查询较重，每 5 次采样刷新一次
  LIMIT_TICK=$((LIMIT_TICK + 1))
  if [ $((LIMIT_TICK % 5)) -eq 1 ] || [ "$LAST_LIMIT" = "na" ]; then
    LAST_LIMIT=$(pmset -g therm 2>/dev/null | awk '/CPU_Speed_Limit/{print $3; exit}')
    [ -z "$LAST_LIMIT" ] && LAST_LIMIT="na"
  fi
  LIMIT="$LAST_LIMIT"

  return 0
}

diagnose() {
  local note=""
  if [ "$SOURCE" = "AC" ] && [ "$MA" -lt -300 ] 2>/dev/null; then
    note="AC_BUT_DISCHARGING"
  fi
  if [ "$LIMIT" != "na" ] && [ "$LIMIT" -lt 80 ] 2>/dev/null; then
    note="${note:+$note| }CPU_THROTTLED_${LIMIT}"
  fi
  if [ "$SOURCE" = "BAT" ] && [ "$PCT" != "na" ] && [ "$PCT" -lt 20 ] 2>/dev/null; then
    note="${note:+$note| }LOW_BATTERY"
  fi
  printf '%s' "$note"
}

rotate() {
  [ -f "$CSV" ] || return 0
  local n
  n=$(wc -l < "$CSV" | tr -d ' ')
  if [ "$n" -gt "$MAX_LINES" ]; then
    tail -n $((MAX_LINES / 2)) "$CSV" > "$CSV.tmp" && mv "$CSV.tmp" "$CSV"
  fi
}

check_previous_run() {
  [ -f "$BEAT" ] || return 0
  local last now gap
  last=$(tr -dc '0-9' < "$BEAT" 2>/dev/null)
  now=$(date +%s)
  [ -z "$last" ] && return 0
  gap=$((now - last))
  if [ "$gap" -gt "$STALE_SEC" ]; then
    local clean=0
    [ -f "$CLEAN" ] && clean=$(tr -dc '0-9' < "$CLEAN" 2>/dev/null)
    if [ -n "$clean" ] && [ "$clean" -ge "$last" ] 2>/dev/null; then
      return 0
    fi
    {
      echo "=============================================="
      echo "异常断电记录  $(date '+%Y-%m-%d %H:%M:%S')"
      echo "上次心跳: $(date -r "$last" '+%Y-%m-%d %H:%M:%S')"
      echo "心跳中断约 ${gap} 秒（阈值 ${STALE_SEC}s）"
      echo "---- 断电前最后 12 条采样 ----"
      if [ -f "$CSV" ]; then
        grep -v '^timestamp' "$CSV" | tail -12
      else
        echo "(无采样数据)"
      fi
      echo ""
    } >> "$INC"
    echo "[powerwatch] 检测到上次异常终止，已写入 $INC"
  fi
}

run_loop() {
  check_previous_run

  if [ -f "$LOCK" ]; then
    local oldpid
    oldpid=$(cat "$LOCK" 2>/dev/null)
    if [ -n "$oldpid" ] && kill -0 "$oldpid" 2>/dev/null; then
      echo "[powerwatch] 已有实例在运行 (pid $oldpid)，退出"
      exit 0
    fi
  fi
  echo $$ > "$LOCK"

  if [ ! -f "$CSV" ]; then
    echo "timestamp,iso_time,source,pct,cur_mAh,max_mAh,design_mAh,health_pct,mA,mV,temp_C,cycle,adapter_id,cpu_limit,charging,note" > "$CSV"
  fi

  cleanup() {
    date +%s > "$CLEAN" 2>/dev/null
    rm -f "$LOCK"
    echo "[powerwatch] 已停止 $(date '+%F %T')"
    exit 0
  }
  trap cleanup INT TERM

  echo "[powerwatch] 启动，间隔 ${INTERVAL}s，日志 $CSV"

  local seq=0 stamp sec iso note
  while true; do
    if read_battery; then
      note=$(diagnose)
      stamp=$(date '+%s %Y-%m-%d %H:%M:%S')
      sec=${stamp%% *}
      iso=${stamp#* }
      printf '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,"%s"\n' \
        "$sec" "$iso" "$SOURCE" "$PCT" "$CUR_MAH" "$MAX_MAH" "$DESIGN_MAH" \
        "$HEALTH" "$MA" "$VOLT_MV" "$TEMP_C" "$CYCLE" "$ADAPTER_ID" "$LIMIT" \
        "$CHARGING" "$note" >> "$CSV"
      echo "$sec" > "$BEAT"

      [ -n "$note" ] && echo "[${iso#* }] 异常: $note  (电量 ${PCT}%  电流 ${MA}mA  限速 ${LIMIT}%)"

      seq=$((seq + 1))
      [ $((seq % 240)) -eq 0 ] && rotate
    else
      echo "[$(date '+%T')] 读取电池信息失败" >&2
      date +%s > "$BEAT"
    fi
    sleep "$INTERVAL"
  done
}

report() {
  echo "=========== 电池健康 ==========="
  if read_battery; then
    echo "当前电量      : ${PCT}%  (${CUR_MAH} / ${MAX_MAH} mAh)"
    echo "设计容量      : ${DESIGN_MAH} mAh"
    echo "健康度        : ${HEALTH}%"
    echo "循环次数      : ${CYCLE}"
    echo "电池温度      : ${TEMP_C} °C"
    echo "供电来源      : ${SOURCE}   电流 ${MA} mA"
    echo "适配器 ID     : ${ADAPTER_ID}   (0 = 无法识别)"
    echo "CPU 限速      : ${LIMIT}%   (100 = 正常)"
  fi
  echo ""
  echo "=========== 采样概况 ==========="
  if [ -f "$CSV" ]; then
    local total first_ts last_ts
    total=$(( $(wc -l < "$CSV") - 1 ))
    first_ts=$(grep -v '^timestamp' "$CSV" | head -1 | cut -d, -f1)
    last_ts=$(grep -v '^timestamp' "$CSV" | tail -1 | cut -d, -f1)
    echo "采样条数      : $total"
    echo "时间范围      : $(date -r "${first_ts:-0}" '+%F %T') → $(date -r "${last_ts:-0}" '+%F %T')"
    echo "接电却放电    : $(grep -c 'AC_BUT_DISCHARGING' "$CSV" 2>/dev/null) 次"
    echo "CPU 被降频    : $(grep -c 'CPU_THROTTLED' "$CSV" 2>/dev/null) 次"
  else
    echo "暂无采样数据"
  fi
  echo ""
  echo "=========== 异常断电 ==========="
  if [ -f "$INC" ]; then
    echo "记录次数: $(grep -c '异常断电记录' "$INC")"
    echo "最近一次:"
    awk '/异常断电记录/{buf=""} {buf=buf"\n"$0} END{print buf}' "$INC" | tail -20
  else
    echo "暂无记录"
  fi
}

install_agent() {
  mkdir -p "$HOME/Library/LaunchAgents"
  cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>$SELF</string>
        <string>-i</string>
        <string>$INTERVAL</string>
    </array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>ThrottleInterval</key><integer>10</integer>
    <key>StandardOutPath</key><string>$BASE/agent.out.log</string>
    <key>StandardErrorPath</key><string>$BASE/agent.err.log</string>
</dict>
</plist>
PLISTEOF
  launchctl unload "$PLIST" 2>/dev/null
  launchctl load "$PLIST" 2>/dev/null || true
  echo "[powerwatch] 已安装: $PLIST"
  echo "[powerwatch] 进程状态: $(pgrep -f 'powerwatch.sh -i' | wc -l | tr -d ' ') 个实例"
}

uninstall_agent() {
  if [ -f "$PLIST" ]; then
    launchctl unload "$PLIST" 2>/dev/null
    rm -f "$PLIST"
    echo "[powerwatch] 已移除 LaunchAgent"
  else
    echo "[powerwatch] 未安装"
  fi
  rm -f "$LOCK"
}

case "${1:-run}" in
  install)   install_agent ;;
  uninstall) uninstall_agent ;;
  report)    report ;;
  incidents) [ -f "$INC" ] && cat "$INC" || echo "暂无异常断电记录" ;;
  run)       run_loop ;;
  -i)        INTERVAL="${2:-5}"; run_loop ;;
  -h|--help) sed -n '2,11p' "$0" ;;
  *)         INTERVAL="${1:-5}"; run_loop ;;
esac
