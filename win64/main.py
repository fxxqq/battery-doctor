# -*- coding: utf-8 -*-
"""电池医生 Windows 版 —— 入口

双击 exe / pythonw main.py 都能跑，异常会写进 app.log，
方便在别人的电脑上排查「闪退」这类问题。
"""

import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)


def _log_crash(text):
    try:
        import bd_core
        path = os.path.join(bd_core.BASE, "crash.log")
    except Exception:
        path = os.path.join(os.path.expanduser("~"), "batterydoctor-crash.log")
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n===== %s =====\n%s\n" % (
                __import__("time").strftime("%Y-%m-%d %H:%M:%S"), text))
    except Exception:
        pass
    return path


def main():
    try:
        import bd_ui
        bd_ui.run()
    except Exception:
        tb = traceback.format_exc()
        path = _log_crash(tb)
        try:
            import tkinter as tk
            from tkinter import messagebox
            r = tk.Tk()
            r.withdraw()
            messagebox.showerror("电池医生启动失败",
                                 "程序遇到了一个错误：\n\n%s\n\n详细日志：\n%s" % (tb[-500:], path))
            r.destroy()
        except Exception:
            sys.stderr.write(tb)


if __name__ == "__main__":
    main()
