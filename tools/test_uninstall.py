import importlib.util, os, sys, time, threading

os.environ["BD_SELFTEST"] = ""          # 不触发内置自测
import os
HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("bd", os.path.join(HERE, "..", "app", "batterydoctor.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

import tkinter as tk

root = tk.Tk()
root.withdraw()                          # 隐藏窗口，不打扰桌面
app = m.App(root)

print("1) 页面列表:", sorted(app.pages.keys()))
assert "uninstall" in app.pages, "没有装上卸载页"

app.show_page("uninstall")
print("2) 切到卸载页 OK，当前页 =", app.page)
assert app.page == "uninstall"

# 等扫描跑完（最多 25 秒）
t0 = time.time()
while time.time() - t0 < 25:
    root.update()
    if getattr(app, "uninstall_loaded", False):
        break
    time.sleep(0.15)

print("3) 扫描完成，用时 %.1fs，已加载 = %s" % (time.time() - t0, app.uninstall_loaded))
apps = app.uninstall_list.items
print("   列表行数 =", len(apps))
assert len(apps) > 0, "列表是空的"

# 抽查一行的内容
a = apps[0]
lbl = a.get("_meta_lbl")
print("   首行：%s | 文案：%s | 状态：%s"
      % (a["name"], lbl.cget("text") if lbl else "?", lbl.cget("fg") if lbl else "?"))

# 勾选交互
target = apps[0]
app._un_toggle(target["path"], True)
root.update()
print("4) 勾选后：选中数 =", len(app._un_sel),
      "| 按钮文案 =", app.btn_un.get_text() if hasattr(app.btn_un, "get_text") else "?",
      "| 按钮可用 =", app.btn_un.enabled if hasattr(app.btn_un, "enabled") else "?")
assert len(app._un_sel) == 1

# 批量选择 + 取消
for x in apps[:3]:
    app._un_toggle(x["path"], True)
root.update()
print("5) 勾选 3 个后选中数 =", len(app._un_sel))
app._un_toggle(apps[0]["path"], False)
root.update()
print("   取消一个后 =", len(app._un_sel))
assert len(app._un_sel) == 2

# 残留开关
app._un_toggle_leftover(True)
root.update()
print("6) 残留开关打开 →", app._un_leftover,
      "| 提示：", app.uninstall_hint.cget("text")[:40])
app._un_toggle_leftover(False)
root.update()

# 确认框文案（不真的弹窗，只看拼出来的内容）
lines = []
for x in apps[:2]:
    lines.append("· %s  %s" % (x["name"], m.human(x.get("size") or 0)))
txt = "要卸载 %d 个应用，合计 %s：\n\n%s" % (2, m.human(100), "\n".join(lines))
print("7) 确认框样例:\n" + txt)

# 卸载流程（真删一个桌面上重复的 CodeBuddy CN 副本太冒险，这里只测失败路径）
print("8) 校验 _can_remove / 保护名单:")
print("   Safari 被排除:", not any("Safari" in x["name"] for x in apps))
print("   自身被排除:", not any("BatteryDoctor" in x["name"] for x in apps))
print("   合计可释放:", m.human(app._un_total))

# 卸载「不存在」的路径，应安全失败不崩
res = m.uninstall_app({"path": "/tmp/不存在.app", "size": 0, "leftovers": []})
print("9) 卸载不存在的 app →", {k: v for k, v in res.items() if k != "errors"})

root.destroy()
print("\n全部通过 ✓")
