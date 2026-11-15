#!/bin/bash
# build_dmg.sh - 把电池医生打包成自包含的 DMG
#   图标取自 assets/AppIcon.icns（仓库内，不会再被构建清理删掉）
#   版本号自动读取 app/batterydoctor.py 的 VERSION
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
PY_SRC="/Users/frank/.workbuddy/binaries/python/versions/3.13.12"
BUILD="$ROOT/build"
APP="BatteryDoctor.app"
APP_DIR="$BUILD/$APP"
CONT="$APP_DIR/Contents"
ICONS="$ROOT/assets/AppIcon.icns"
VERSION="$(sed -n 's/^VERSION = "\(.*\)"/\1/p' "$ROOT/app/batterydoctor.py" | head -1)"

echo "==> 1/7 清理构建目录"
rm -rf "$APP_DIR" "$BUILD/dmgroot" "$BUILD/dist"
mkdir -p "$CONT/MacOS" "$CONT/Resources" "$BUILD/dist"

echo "==> 2/7 复制应用代码"
cp "$ROOT/app/batterydoctor.py" "$CONT/Resources/batterydoctor.py"

cat > "$CONT/MacOS/BatteryDoctor" <<'LAUNCHER'
#!/bin/bash
RES="$(cd "$(dirname "$0")/../Resources" && pwd)"
exec "$RES/Python/bin/python3" "$RES/batterydoctor.py" "$@"
LAUNCHER
chmod +x "$CONT/MacOS/BatteryDoctor"

echo "==> 3/7 内嵌 Python 运行时（约 50MB，首次较慢）"
ditto "$PY_SRC" "$CONT/Resources/Python"
"$CONT/Resources/Python/bin/python3" -c "import tkinter; print('    内嵌 Python + Tk 验证通过')" || {
  echo "内嵌 Python 验证失败"; exit 1; }

echo "==> 4/7 写入 Info.plist 与 PkgInfo"
cat > "$CONT/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key><string>BatteryDoctor</string>
    <key>CFBundleDisplayName</key><string>电池医生</string>
    <key>CFBundleIdentifier</key><string>com.local.batterydoctor</string>
    <key>CFBundleVersion</key><string>$VERSION</string>
    <key>CFBundleShortVersionString</key><string>$VERSION</string>
    <key>CFBundleExecutable</key><string>BatteryDoctor</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleIconFile</key><string>AppIcon</string>
    <key>LSMinimumSystemVersion</key><string>10.13</string>
    <key>LSApplicationCategoryType</key><string>public.app-category.utilities</string>
    <key>NSHighResolutionCapable</key><true/>
    <key>NSHumanReadableCopyright</key><string>Built for personal use</string>
</dict>
</plist>
PLIST
printf 'APPL????' > "$CONT/PkgInfo"

echo "==> 5/7 应用图标"
if [ -f "$ICONS" ]; then
  cp "$ICONS" "$CONT/Resources/AppIcon.icns"
  echo "    AppIcon.icns 已复制"
else
  echo "    警告：assets/AppIcon.icns 不存在，app 将没有图标"
fi

echo "==> 6/7 Ad-hoc 签名"
if codesign --force --deep --sign - "$APP_DIR" 2>/dev/null; then
  codesign --verify --deep "$APP_DIR" && echo "    签名验证通过"
else
  echo "    警告：签名失败，本机使用不受影响（x86_64 可直接运行）"
fi

echo "==> 7/7 打包 DMG"
mkdir -p "$BUILD/dmgroot"
cp -R "$APP_DIR" "$BUILD/dmgroot/"
ln -s /Applications "$BUILD/dmgroot/Applications"
if [ -f "$ROOT/assets/first-open.html" ]; then
  cp "$ROOT/assets/first-open.html" "$BUILD/dmgroot/⚠️ 先读我：如何打开.html"
fi
cat > "$BUILD/dmgroot/使用说明.txt" <<README
电池医生 Battery Doctor $VERSION
================================

【安装三步】
  1. 把 BatteryDoctor.app 拖进右边的 Applications 文件夹
  2. 打开 Applications，右键点 BatteryDoctor →「打开」
     （不要直接双击！右键打开一次以后就能正常双击了）
  3. 弹窗里再点一次「打开」

如果提示"无法打开"或"已损坏"：
  双击 dmg 里的「⚠️ 先读我：如何打开.html」，复制里面的
  一行命令到终端执行即可。

功能
  · 实时读取 SMC 电池数据：健康度 / 电流 / 充电器识别 / CPU 限速 / 电芯偏差
  · 一键诊断供电异常（插电却放电、充电器无法识别、降频）
  · 充电养护：习惯评分 + Intel 机型 SMC BCLM 硬件限充（80/70/60%）
  · 网络诊断：Wi-Fi 信号 / IP / 网关 / DNS / 系统代理 / hosts，可一键修复联网
  · 开始监控：每 5 秒记录到 ~/Library/Logs/PowerWatch/power.csv
    异常断电自动取证（incidents.log）并弹系统通知
  · 一键优化：停用多余后台启动项（可还原，备份在
    ~/Library/.batterydoctor-backup）
  · 磁盘清理：先扫描每项大小，逐项勾选，二次确认才动手；
    清理中实时显示进度，可中途关闭
  · 电池详情：电芯级电压、电芯学到的容量（Qmax）与系统报的容量对照
  · 校准向导：记录校准前容量，校准后自动对比，判断是读数问题还是真老化
  · 负载压降测试：满载 8 秒测带载压降，换算内阻，给「一用就关机」做实证
  · 送修单导出：故障码 + 断电记录 + 处理顺序，一页纸给售后看
  · 每日体检：每天 9:00 自动检查，异常才发通知（体检页可开关）
  · 悬浮小窗：常驻屏幕角落显示电量与限速，可拖动、双击关闭
  · 检查更新：侧栏左下角，点了才联网（可选每周自动检查）
  · 导出：诊断报告 PDF / 趋势图 PNG / 清理建议 / 系统级清理脚本

隐私：全程本地运行，不联网（唯一联网处是网络诊断页，且需手动触发）。

系统级启动项（TeamViewer / Citrix / Zoom 等需要管理员权限）：
  在终端执行下方命令后按提示输入密码
  bash ~/Library/Application\ Support/BatteryDoctor/system-optimize.sh --apply
README
hdiutil create -volname "电池医生" -srcfolder "$BUILD/dmgroot" \
  -ov -format UDZO -o "$BUILD/dist/BatteryDoctor-$VERSION.dmg" >/dev/null

mkdir -p "$HOME/Library/Application Support/BatteryDoctor"
cp "$ROOT/optimize.sh" "$HOME/Library/Application Support/BatteryDoctor/system-optimize.sh" 2>/dev/null || true

DMG="$BUILD/dist/BatteryDoctor-$VERSION.dmg"
echo ""
echo "构建完成: $DMG ($(du -sh "$DMG" | cut -f1))"
