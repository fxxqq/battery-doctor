#!/bin/bash
# optimize.sh - 启动项瘦身 + 可再生缓存清理（可回滚）
#
#   ./optimize.sh                 预览要处理的项目（不修改任何东西）
#   ./optimize.sh --apply         执行（用户级项目直接生效，系统级需 sudo）
#   sudo ./optimize.sh --apply    连系统级一起处理
#   ./optimize.sh --revert        全部还原
#   ./optimize.sh --clean-cache   把可再生缓存移到废纸篓

set -u

STAMP="20261115"
BACKUP="$HOME/Library/.startup-backup-$STAMP"
MANIFEST="$BACKUP/manifest.txt"
CACHE_SRC="$HOME/Library/Caches"

# 用户级：直接移动即可生效（下次登录不再自启）
USER_ITEMS=(
  "cn.macx.MacAppBoxHelper.plist"
  "com.adobe.AAM.Updater-1.0.plist"
  "com.google.keystone.agent.plist"
  "com.google.keystone.xpcservice.plist"
  "com.antssWu.shadowsocksX-NG.http.plist"
  "com.antssWu.shadowsocksX-NG.local.plist"
  "com.yicheng.ShadowsocksX-R.local.plist"
  "org.getlantern.plist"
  "org.virtualbox.vboxwebsrv.plist"
)

# 系统级：需要 root 才能移动
SYSTEM_ITEMS=(
  "/Library/LaunchDaemons/com.teamviewer.Helper.plist"
  "/Library/LaunchDaemons/com.teamviewer.teamviewer_service.plist"
  "/Library/LaunchAgents/com.teamviewer.teamviewer.plist"
  "/Library/LaunchAgents/com.teamviewer.teamviewer_desktop.plist"
  "/Library/LaunchDaemons/com.citrix.ctxusbd.plist"
  "/Library/LaunchDaemons/com.citrix.ctxworkspaceupdater.plist"
  "/Library/LaunchAgents/com.citrix.AuthManager_Mac.plist"
  "/Library/LaunchAgents/com.citrix.ReceiverHelper.plist"
  "/Library/LaunchAgents/com.citrix.ServiceRecords.plist"
  "/Library/LaunchAgents/com.citrix.safariadapter.plist"
  "/Library/LaunchDaemons/us.zoom.ZoomDaemon.plist"
  "/Library/LaunchDaemons/com.adobe.SwitchBoard.plist"
  "/Library/LaunchDaemons/com.microsoft.teams.TeamsUpdaterDaemon.plist"
  "/Library/LaunchDaemons/org.virtualbox.startup.plist"
  "/Library/LaunchDaemons/com.BlueStacks.AppPlayer.bstservice_helper.plist"
  "/Library/LaunchDaemons/com.netease.nemu.startup.plist"
)

# 可再生缓存（移到废纸篓，随时可清空回收空间）
CACHE_ITEMS=(
  "com.microsoft.VSCode.ShipIt"
  "com.apple.helpd"
  "JetBrains"
  "copilot"
  "com.sogou.SGSkinManager"
)

ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
skip() { printf '  \033[90m–\033[0m %s\n' "$1"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$1"; }

do_apply() {
  local is_root=0
  [ "$(id -u)" = "0" ] && is_root=1

  mkdir -p "$BACKUP/system"
  : >> "$MANIFEST"

  echo ""
  echo "【1】用户级启动项"
  local f
  for f in "${USER_ITEMS[@]}"; do
    if [ -f "$HOME/Library/LaunchAgents/$f" ]; then
      mv "$HOME/Library/LaunchAgents/$f" "$BACKUP/$f" 2>/dev/null \
        && { ok "$f"; echo "user|$f" >> "$MANIFEST"; } \
        || warn "$f 移动失败"
    else
      skip "$f（不存在）"
    fi
  done

  echo ""
  echo "【2】系统级启动项"
  local item path
  for item in "${SYSTEM_ITEMS[@]}"; do
    case "$item" in *:skip) skip "$(basename "${item%:skip}")（保留）"; continue ;; esac
    path="$item"
    if [ ! -f "$path" ]; then skip "$(basename "$path")（不存在）"; continue; fi
    if [ "$is_root" = "1" ]; then
      mkdir -p "$BACKUP/system$(dirname "$path")"
      if mv "$path" "$BACKUP/system$path" 2>/dev/null; then
        ok "$(basename "$path")"
        echo "system|$path" >> "$MANIFEST"
      else
        warn "$(basename "$path") 移动失败"
      fi
    else
      warn "$(basename "$path") 需 root，见下方命令"
    fi
  done

  if [ "$is_root" = "0" ]; then
    echo ""
    echo "  系统级项目请执行下面这一条（会提示输入密码）："
    echo "  sudo \"$(pwd)/$(basename "$0")\" --apply"
  fi

  echo ""
  echo "【3】说明"
  echo "  · 已移动的项目不会删除，随时可用 --revert 还原"
  echo "  · 当前已运行的进程不会立刻退出，注销或重启后彻底生效"
  echo "  · 保留未动：Cisco AnyConnect（工作 VPN）、深信服准入、Paragon NTFS、ClashX Pro、Sogou"
}

do_revert() {
  [ -f "$MANIFEST" ] || { echo "没有找到备份清单：$MANIFEST"; exit 1; }
  local kind name
  while IFS='|' read -r kind name; do
    case "$kind" in
      user)
        if [ -f "$BACKUP/$name" ]; then
          mv "$BACKUP/$name" "$HOME/Library/LaunchAgents/$name" && ok "还原 $name"
        fi ;;
      system)
        if [ -f "$BACKUP/system$name" ]; then
          if [ "$(id -u)" = "0" ]; then
            mv "$BACKUP/system$name" "$name" && ok "还原 $name"
          else
            warn "需 root 还原 $name"
          fi
        fi ;;
    esac
  done < "$MANIFEST"
  echo "还原完成，注销后生效"
}

do_preview() {
  echo "【用户级启动项 → 将移到 ${BACKUP}】"
  local f
  for f in "${USER_ITEMS[@]}"; do
    [ -f "$HOME/Library/LaunchAgents/$f" ] && ok "$f" || skip "$f"
  done
  echo ""
  echo "【系统级启动项 → 需 sudo】"
  local item
  for item in "${SYSTEM_ITEMS[@]}"; do
    case "$item" in *:skip) skip "$(basename "${item%:skip}")（保留）"; continue ;; esac
    [ -f "$item" ] && ok "$(basename "$item")" || skip "$(basename "$item")"
  done
  echo ""
  echo "【缓存 → 将移到废纸篓】"
  for f in "${CACHE_ITEMS[@]}"; do
    if [ -d "$CACHE_SRC/$f" ]; then
      printf '  ✓ %-38s %s\n' "$f" "$(du -sh "$CACHE_SRC/$f" 2>/dev/null | cut -f1)"
    else
      skip "$f"
    fi
  done
}

do_cache() {
  local moved_kb=0 f size kb
  echo ""
  echo "【清理可再生缓存 → ~/.Trash】"
  for f in "${CACHE_ITEMS[@]}"; do
    if [ -d "$CACHE_SRC/$f" ]; then
      size=$(du -sh "$CACHE_SRC/$f" 2>/dev/null | cut -f1)
      kb=$(du -sk "$CACHE_SRC/$f" 2>/dev/null | cut -f1)
      if mv "$CACHE_SRC/$f" "$HOME/.Trash/${f}.cache-$STAMP" 2>/dev/null; then
        ok "$f ($size) → 废纸篓"
        moved_kb=$((moved_kb + ${kb:-0}))
      else
        warn "$f 移动失败"
      fi
    fi
  done
  echo ""
  echo "  已移动 $(( moved_kb / 1024 )) MB 到废纸篓，清空废纸篓后即释放"
}

case "${1:-preview}" in
  --apply)       do_apply ;;
  --revert)      do_revert ;;
  --clean-cache) do_cache ;;
  *)             do_preview ;;
esac
