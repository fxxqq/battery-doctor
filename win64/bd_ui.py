# -*- coding: utf-8 -*-
"""电池医生 Windows 版 —— 界面层

配色与 Mac 版保持一致：低饱和的暖白底 + 单色强调，只有真正的红才用红。
所有系统调用都走 bd_core，界面只负责表达和编排。
"""

import csv
import html
import math
import os
import queue
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox, ttk

import bd_core as core

APP_NAME = core.APP_NAME
VERSION = core.VERSION

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

FONT = "Microsoft YaHei UI"
MONO = "Consolas"
CUR = "hand2"

CAND_FONTS = ["Microsoft YaHei UI", "Microsoft YaHei", "微软雅黑", "PingFang SC",
              "Segoe UI", "SimHei", "SimSun"]
CAND_MONO = ["Cascadia Mono", "Consolas", "Courier New"]


def pick_fonts(root):
    """按可用性挑中文字体，避免打包到不同机器上字体缺失"""
    global FONT, MONO
    try:
        fams = set(tkfont.families(root))
    except Exception:
        return
    for f in CAND_FONTS:
        if f in fams:
            FONT = f
            break
    for f in CAND_MONO:
        if f in fams:
            MONO = f
            break


def to_int(s, d=0):
    return core.to_int(s, d)


def human(kb):
    return core.human(kb)


def round_rect(c, x1, y1, x2, y2, r, **kw):
    r = min(r, abs(x2 - x1) / 2.0, abs(y2 - y1) / 2.0)
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
           x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
           x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return c.create_polygon(pts, smooth=True, **kw)


def walk(w):
    yield w
    for ch in w.winfo_children():
        for x in walk(ch):
            yield x


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


# --------------------------------------------------------------- 控件
class Card(tk.Frame):
    def __init__(self, master, pad=16, bg=None, line=None, **kw):
        self.c_bg = bg or P["card"]
        super().__init__(master, bg=self.c_bg, highlightthickness=1,
                         highlightbackground=line or P["line"],
                         highlightcolor=line or P["line"], bd=0, **kw)
        self.body = tk.Frame(self, bg=self.c_bg)
        self.body.pack(fill="both", expand=True, padx=pad, pady=pad)


class RButton(tk.Canvas):
    STYLES = {
        "primary":   (P["accent"], P["accent2"], "#FFFFFF"),
        "secondary": ("#EFEFE9", "#E3E3DB", P["text"]),
        "ghost":     (P["card"], P["hover"], P["text2"]),
        "danger":    (P["red_soft"], "#F5DCD8", P["red"]),
    }

    def __init__(self, master, text, command, kind="secondary", height=32,
                 size=11, padx=16, bg=None, width=None):
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
                         highlightthickness=0, bd=0, cursor=CUR)
        self._draw()
        self.bind("<Button-1>", self._click)
        self.bind("<Enter>", lambda e: self._fill(self.fill_hover))
        self.bind("<Leave>", lambda e: self._fill(self.fill))

    @staticmethod
    def _bg_of(master):
        try:
            return master.cget("bg")
        except Exception:
            return P["bg"]

    def _draw(self):
        self.delete("all")
        h = to_int(self.cget("height"))
        round_rect(self, 0, 1, self.w, h - 1, h / 2 - 1, fill=self.fill, outline="")
        self.create_text(self.w / 2, h / 2, text=self.text, fill=self.fg,
                         font=(FONT, self.size, "bold" if self.kind == "primary" else "normal"))

    def _fill(self, color):
        if not self.enabled:
            return
        h = to_int(self.cget("height"))
        self.delete("all")
        round_rect(self, 0, 1, self.w, h - 1, h / 2 - 1, fill=color, outline="")
        self.create_text(self.w / 2, h / 2, text=self.text, fill=self.fg,
                         font=(FONT, self.size, "bold" if self.kind == "primary" else "normal"))

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
        self.configure(cursor=CUR if on else "arrow")
        self.fg = self.STYLES.get(self.kind)[2] if on else P["faint"]
        self._draw()


class Chip(tk.Frame):
    def __init__(self, master, text="", fg=None, bg=None, dot=None, size=9):
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
        super().__init__(master, bg=P["sidebar"], height=38, cursor=CUR)
        self.pack_propagate(False)
        self.key = key
        self.command = command
        self.bar = tk.Frame(self, bg=P["sidebar"], width=3)
        self.bar.pack(side="left", fill="y")
        self.lbl = tk.Label(self, text=text, bg=P["sidebar"], fg=P["text2"],
                            font=(FONT, 10), anchor="w", padx=12)
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
            self.lbl.configure(fg=P["accent"], font=(FONT, 10, "bold"))
            self.bar.configure(bg=P["accent"])
        else:
            self._paint(P["sidebar"])
            self.lbl.configure(fg=P["text2"], font=(FONT, 10))
            self.bar.configure(bg=P["sidebar"])


class MetricCard(Card):
    def __init__(self, master, label, hint="", pad=12):
        super().__init__(master, pad=0)
        inner = tk.Frame(self, bg=P["card"])
        inner.pack(fill="both", expand=True, padx=pad, pady=pad - 2)
        self.name = tk.Label(inner, text=label, bg=P["card"], fg=P["muted"],
                             font=(FONT, 9), anchor="w")
        self.name.pack(anchor="w")
        self.val = tk.Label(inner, text="--", bg=P["card"], fg=P["text"],
                            font=(FONT, 15, "bold"), anchor="w")
        self.val.pack(anchor="w", pady=(1, 2))
        self.hint = tk.Label(inner, text=hint, bg=P["card"], fg=P["faint"],
                             font=(FONT, 8), anchor="w", justify="left",
                             wraplength=150)
        self.hint.pack(anchor="w")

    def set(self, text, color=None, hint=None):
        self.val.configure(text=text, fg=color or P["text"])
        if hint is not None:
            self.hint.configure(text=hint)


class RowList(tk.Frame):
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
        for w in (self.canvas, self.inner):
            w.bind("<MouseWheel>", self._wheel)

        self.items = []
        self.rows = {}
        self.sel = None

    def _on_scroll(self, first, last):
        self.vs.set(first, last)
        if float(first) <= 0.001 and float(last) >= 0.999:
            self.vs.pack_forget()
        elif not self.vs.winfo_ismapped():
            self.vs.pack(side="right", fill="y")

    def _inner_cfg(self, _):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _canvas_cfg(self, e):
        self.canvas.itemconfigure(self.win, width=e.width)

    def _wheel(self, e):
        bb = self.canvas.bbox("all")
        if bb and bb[3] > self.canvas.winfo_height():
            step = -1 * int(e.delta / 120) if abs(e.delta) >= 120 else (-1 if e.delta > 0 else 1)
            self.canvas.yview_scroll(step, "units")

    def set_items(self, items):
        self.items = items
        for w in list(self.inner.winfo_children()):
            w.destroy()
        self.rows.clear()

        if not items:
            tk.Label(self.inner, text=self.empty, bg=self.list_bg,
                     fg=P["faint"], font=(FONT, 10), pady=30).pack(fill="x")
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
                tk.Frame(self.inner, bg=P["line2"], height=1).pack(fill="x")
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
                w.configure(cursor=CUR)
            except Exception:
                pass

    def _mark(self, row, on):
        recolor(row, P["accent_soft"] if on else self.list_bg,
                only=(self.list_bg, P["hover"], P["accent_soft"]))

    def selected_key(self):
        return self.sel


class Ring(tk.Canvas):
    def __init__(self, master, size=168):
        super().__init__(master, width=size, height=size, bg=P["card"],
                         highlightthickness=0)
        self.size = size

    def draw(self, pct, health, level_color, sub="当前电量"):
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
        c.create_text(cx, cy - 14, text="%d%%" % pct, fill=P["text"],
                      font=(FONT, 32, "bold"))
        c.create_text(cx, cy + 14, text=sub, fill=P["muted"], font=(FONT, 9))
        c.create_text(cx, cy + 34, text="健康 %d%%" % health, fill=level_color,
                      font=(FONT, 10, "bold"))


# --------------------------------------------------------------- 一键体检
class StepRow:
    def __init__(self, parent, title):
        self.frame = tk.Frame(parent, bg=P["card"])
        self.frame.pack(fill="x", pady=2)
        self.dot = tk.Canvas(self.frame, width=18, height=18, bg=P["card"],
                             highlightthickness=0)
        self.dot.pack(side="left", padx=(0, 8))
        self._circle(P["faint"], "")
        self.t = tk.Label(self.frame, text=title, bg=P["card"], fg=P["text2"],
                          font=(FONT, 10), anchor="w")
        self.t.pack(side="left", fill="x", expand=True)
        self.d = tk.Label(self.frame, text="", bg=P["card"], fg=P["faint"],
                          font=(FONT, 9), anchor="e")
        self.d.pack(side="right")

    def _circle(self, color, glyph):
        self.dot.delete("all")
        self.dot.create_oval(1, 1, 17, 17, outline=color, width=1.6)
        if glyph:
            self.dot.create_text(9, 9, text=glyph, fill=color, font=(FONT, 8, "bold"))

    def set(self, state, detail=None):
        color = {"ok": P["green"], "warn": P["amber"], "fail": P["red"],
                 "run": P["accent"], "wait": P["faint"]}.get(state, P["faint"])
        glyph = {"ok": "✓", "warn": "!", "fail": "×", "run": "…", "wait": ""}.get(state, "")
        self._circle(color, glyph)
        self.t.configure(fg=P["text"] if state != "wait" else P["muted"])
        if detail is not None:
            self.d.configure(text=detail[:38], fg=color if state in ("fail", "warn") else P["faint"])

    def destroy(self):
        self.frame.destroy()


class CheckupDialog(tk.Toplevel):
    """一键体检：把「为什么关机」这件事从头查到尾，最后给一句人话结论"""

    STEPS = ["读取电池与供电状态", "生成官方电池健康报告", "扫描异常关机记录",
             "检查温度与降频", "检查高耗电进程", "检查磁盘空间",
             "检查启动项", "检查电源计划", "汇总结论"]

    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.title("一键体检")
        self.configure(bg=P["card"])
        self.resizable(False, False)
        self.transient(app.root)
        self.grab_set()

        self.w, self.h = 560, 520
        self._center()
        self.q = queue.Queue()
        self.rows = []
        self.result = {}
        self.report_path = ""
        self.finished = False

        tk.Label(self, text="一键体检", bg=P["card"], fg=P["text"],
                 font=(FONT, 16, "bold")).pack(anchor="w", padx=24, pady=(20, 2))
        tk.Label(self, text="从供电、电池、温度、进程、磁盘、启动项六个方向查一遍，"
                            "重点是找出「为什么会自己关机」。",
                 bg=P["card"], fg=P["muted"], font=(FONT, 9), anchor="w",
                 justify="left", wraplength=500).pack(anchor="w", padx=24)

        sbox = tk.Frame(self, bg=P["card"])
        sbox.pack(fill="x", padx=22, pady=(14, 6))
        for s in self.STEPS:
            self.rows.append(StepRow(sbox, s))

        self.bar = tk.Canvas(self, height=6, bg=P["card"], highlightthickness=0)
        self.bar.pack(fill="x", padx=24, pady=(6, 0))
        self.bar.bind("<Configure>", lambda e: self._prog(self.done, len(self.STEPS)))

        self.verdict = tk.Label(self, text="", bg=P["card"], fg=P["text2"],
                                font=(FONT, 10), anchor="w", justify="left",
                                wraplength=500)
        self.verdict.pack(fill="x", padx=24, pady=(12, 0))

        btns = tk.Frame(self, bg=P["card"])
        btns.pack(fill="x", padx=20, pady=14, side="bottom")
        self.b_copy = RButton(btns, "复制结论", self._copy, kind="ghost", size=10)
        self.b_copy.pack(side="right", padx=4)
        self.b_open = RButton(btns, "打开报告", self._open, kind="secondary", size=10)
        self.b_open.pack(side="right", padx=4)
        self.b_close = RButton(btns, "关闭", self._close, kind="ghost", size=10)
        self.b_close.pack(side="right", padx=4)

        self.done = 0
        self._prog(0, len(self.STEPS))
        self.after(180, self._start)
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _center(self):
        self.app.root.update_idletasks()
        x = self.app.root.winfo_x() + (self.app.root.winfo_width() - self.w) // 2
        y = self.app.root.winfo_y() + (self.app.root.winfo_height() - self.h) // 2
        self.geometry("%dx%d+%d+%d" % (self.w, self.h, max(0, x), max(0, y)))

    def _prog(self, n, total):
        c = self.bar
        c.delete("all")
        w = max(10, c.winfo_width())
        round_rect(c, 0, 0, w, 6, 3, fill=P["track"], outline="")
        if n:
            round_rect(c, 0, 0, max(6, w * n / float(total)), 6, 3,
                       fill=P["accent"], outline="")

    def _start(self):
        threading.Thread(target=self._worker, daemon=True).start()
        self.after(120, self._poll)

    def _worker(self):
        put = self.q.put
        r = self.result
        try:
            put(("step", 0, "run"))
            b = core.Battery.read()
            r["battery"] = b
            put(("step", 0, "ok" if b.ok else "warn",
                 "%d%% · %s" % (b.pct, b.source)))

            put(("step", 1, "run"))
            rep = core.battery_report(force=True)
            if rep["design"] > 0:
                put(("step", 1, "ok", "设计 %d mWh" % rep["design"]))
            else:
                put(("step", 1, "warn", "报告不完整"))

            put(("step", 2, "run"))
            evts = core.shutdown_events(limit=40, force=True)
            bad = [e for e in evts if e["id"] in (41, 6008)]
            r["events"] = evts
            if bad:
                put(("step", 2, "fail", "发现 %d 次异常关机" % len(bad)))
            else:
                put(("step", 2, "ok", "无异常关机"))

            put(("step", 3, "run"))
            r["load"] = core.cpu_load()
            r["limit"] = core.thermal_limit()
            if b.temp_c >= 60:
                put(("step", 3, "warn", "电池 %.0f℃" % b.temp_c))
            elif r["limit"] and r["limit"] < 75:
                put(("step", 3, "warn", "CPU 限速 %d%%" % r["limit"]))
            else:
                put(("step", 3, "ok", "温度正常"))

            put(("step", 4, "run"))
            rows, err = core.read_processes(8)
            r["procs"] = rows or []
            if rows:
                put(("step", 4, "ok", "最高 %d%% CPU" % int(rows[0][1])))
            else:
                put(("step", 4, "warn", err or "读取失败"))

            put(("step", 5, "run"))
            ds = core.drives()
            r["drives"] = ds
            low = [d for d in ds if d[4] >= 90]
            if low:
                put(("step", 5, "warn", "%s 盘只剩 %.1f GB" % (low[0][0], low[0][3])))
            else:
                put(("step", 5, "ok", "%d 个磁盘" % len(ds)))

            put(("step", 6, "run"))
            su = core.startup_items()
            r["startup"] = su
            put(("step", 6, "warn" if len(su) > 12 else "ok", "共 %d 项" % len(su)))

            put(("step", 7, "run"))
            r["scheme"] = core.power_scheme()[0]
            r["fastboot"] = core.fast_startup()
            put(("step", 7, "ok", r["scheme"][:14] or "--"))

            put(("step", 8, "run"))
            r["verdict"] = self._verdict()
            path = self._save_report()
            r["report"] = path
            put(("step", 8, "ok", "已保存到桌面"))
        except Exception as e:
            put(("error", str(e)))
            put(("finish", None))
        else:
            put(("finish", None))

    def _verdict(self):
        """把各项证据拼成一句人话，并给出先后顺序"""
        r = self.result
        b = r.get("battery")
        evts = r.get("events") or []
        bad = [e for e in evts if e["id"] in (41, 6008)]
        lines, level = [], "green"

        if bad:
            level = "red"
            last = bad[0]
            lines.append("【最关键的证据】系统里有 %d 次非正常断电，最近一次 %s。"
                         "这说明关机不是系统主动安排的，而是电被切断了。"
                         % (len(bad), last["time"]))
        if b and b.health and b.health < 80:
            if level != "red":
                level = "amber"
            lines.append("电池容量只剩 %d%%，老化电池在负载突增时会瞬间撑不住电压，"
                         "表现就是「用一会儿突然黑屏」。建议优先换电池。" % b.health)
        if b and b.temp_c >= 60:
            lines.append("电池温度 %.0f℃，偏高。过热保护会直接切断电源。" % b.temp_c)
        if r.get("limit") and r["limit"] < 75:
            lines.append("CPU 当前只有额定频率的 %d%%，常见于供电不足或过热降频。" % r["limit"])
        low = [d for d in (r.get("drives") or []) if d[4] >= 90]
        if low:
            lines.append("%s 盘只剩 %.1f GB，系统在空间极低时也会不稳定。"
                         % (low[0][0], low[0][3]))
        if len(r.get("startup") or []) > 12:
            lines.append("开机启动项有 %d 项，进入桌面后 CPU 和磁盘会持续吃满一段时间。"
                         % len(r["startup"]))
        procs = r.get("procs") or []
        if procs and procs[0][1] >= 40:
            lines.append("当前 %s 占了 %d%% 的 CPU，持续高负载会加速发热。"
                         % (procs[0][4], int(procs[0][1])))

        if not lines:
            lines.append("没有发现会导致突然关机的证据。供电、电池、温度、磁盘都在正常范围，"
                         "建议继续保持监控，下次真的关机了再回来看断电前的数据。")
        if bad:
            lines.append("")
            lines.append("建议顺序：① 换原装充电器试一晚 ② 电池健康低于 80% 就换电池 "
                         "③ 若换过电池仍断电，检查主板供电（DC 接口/供电电路）。")
        return (level, "\n".join(lines))

    def _save_report(self):
        r = self.result
        b = r.get("battery")
        L = []
        L.append("%s 体检报告（Windows）" % APP_NAME)
        L.append("时间：%s" % time.strftime("%Y-%m-%d %H:%M:%S"))
        L.append("机器：%s" % (core.cpu_name() or "未知"))
        L.append("系统：%s" % core.ps("(Get-CimInstance Win32_OperatingSystem).Caption", 12).strip())
        L.append("")
        L.append("=== 结论 ===")
        L.append(r.get("verdict", (0, ""))[1])
        L.append("")
        L.append("=== 电池 ===")
        if b:
            L.append("电量 %d%% · 供电来源 %s · 健康 %d%% · 循环 %d 次"
                     % (b.pct, b.source, b.health, b.cycle))
            L.append("电压 %.2f V · 电流 %d mA · 温度 %.1f℃"
                     % (b.volt / 1000.0, b.ma, b.temp_c))
            L.append(b.note or "")
        L.append("")
        L.append("=== 异常关机记录 ===")
        evts = r.get("events") or []
        if not evts:
            L.append("（事件日志里没有相关记录）")
        for e in evts[:12]:
            lvl, name, _ = core.event_name(e["id"])
            L.append("%s  [%s] %s  %s" % (e["time"], e["id"], name, e["msg"][:90]))
        L.append("")
        L.append("=== 资源 ===")
        for d in (r.get("drives") or []):
            L.append("%s 盘：总 %.1f GB，剩余 %.1f GB（占用 %d%%）"
                     % (d[0], d[1], d[3], d[4]))
        L.append("CPU 负载 %d%% · 频率 %s · 电源方案 %s · 快速启动 %s"
                 % (r.get("load", 0),
                    ("%d%%" % r["limit"]) if r.get("limit") else "--",
                    r.get("scheme", "--"),
                    "开" if r.get("fastboot") else "关"))
        L.append("")
        L.append("=== 高占用进程 ===")
        for p in (r.get("procs") or [])[:8]:
            L.append("%-28s %5.0f%% CPU  %6.1f%% 内存  %s"
                     % (p[4][:28], p[1], p[2], human(p[3])))
        L.append("")
        L.append("=== 启动项（%d）===" % len(r.get("startup") or []))
        for s in (r.get("startup") or [])[:20]:
            L.append("%-30s %s" % (s[0][:30], s[1][:70]))
        L.append("")
        L.append("—— 由 %s %s 生成" % (APP_NAME, VERSION))

        text = "\n".join(L)
        path = os.path.join(core.desktop_dir(),
                            "电池医生诊断报告-%s.txt" % time.strftime("%Y%m%d-%H%M"))
        try:
            with open(path, "w", encoding="utf-8-sig") as f:
                f.write(text)
        except Exception:
            path = os.path.join(core.BASE, "report.txt")
            with open(path, "w", encoding="utf-8-sig") as f:
                f.write(text)
        self.report_text = text
        return path

    def _poll(self):
        try:
            while True:
                item = self.q.get_nowait()
                kind = item[0]
                if kind == "step":
                    _, idx, state = item[0], item[1], item[2]
                    detail = item[3] if len(item) > 3 else None
                    if idx < len(self.rows):
                        self.rows[idx].set(state, detail)
                    if state in ("ok", "warn", "fail"):
                        self.done = max(self.done, idx + 1)
                        self._prog(self.done, len(self.STEPS))
                elif kind == "error":
                    self.verdict.configure(text="体检过程出错：%s" % item[1], fg=P["red"])
                elif kind == "finish":
                    self._finish()
                    return
        except queue.Empty:
            pass
        if not self.finished:
            self.after(120, self._poll)

    def _finish(self):
        self.finished = True
        lvl, text = self.result.get("verdict", ("green", "体检完成"))
        color = {"red": P["red"], "amber": P["amber"], "green": P["accent"]}.get(lvl, P["text"])
        self.verdict.configure(text=text, fg=color)
        self.app.on_checkup_done(lvl, text, self.result.get("report", ""))

    def _copy(self):
        try:
            self.clipboard_clear()
            self.clipboard_append(getattr(self, "report_text", self.verdict.cget("text")))
        except Exception:
            pass

    def _open(self):
        p = self.result.get("report")
        if p and os.path.exists(p):
            core.open_path(p)

    def _close(self):
        self.grab_release()
        self.destroy()


# --------------------------------------------------------------- 网络修复
class NetRepairDialog(tk.Toplevel):
    STEPS = ["备份当前网络设置", "关闭系统代理", "重置 DNS 为公共 DNS",
             "清空 DNS 缓存", "重新获取 IP 地址", "重启网络适配器", "重新检测"]

    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.title("网络修复")
        self.configure(bg=P["card"])
        self.resizable(False, False)
        self.transient(app.root)
        self.grab_set()

        self.w, self.h = 540, 460
        self._center()

        tk.Label(self, text="网络修复", bg=P["card"], fg=P["text"],
                 font=(FONT, 15, "bold")).pack(anchor="w", padx=24, pady=(20, 2))
        tk.Label(self, text="按顺序重置代理、DNS 和网络适配器，不会删除任何数据。",
                 bg=P["card"], fg=P["muted"], font=(FONT, 9), anchor="w").pack(anchor="w", padx=24)

        box = tk.Frame(self, bg=P["card"])
        box.pack(fill="x", padx=22, pady=(14, 8))
        self.q = queue.Queue()
        self.rows = [StepRow(box, s) for s in self.STEPS]
        self.done = 0

        self.tip = tk.Label(self, text="", bg=P["card"], fg=P["text2"], font=(FONT, 9),
                            anchor="w", justify="left", wraplength=480)
        self.tip.pack(fill="x", padx=24, pady=(6, 0))

        btns = tk.Frame(self, bg=P["card"])
        btns.pack(fill="x", padx=20, pady=12, side="bottom")
        RButton(btns, "关闭", self._close, kind="ghost", size=9).pack(side="right", padx=4)

        self.after(150, self._start)
        self.after(120, self._poll)
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _center(self):
        self.app.root.update_idletasks()
        x = self.app.root.winfo_x() + (self.app.root.winfo_width() - self.w) // 2
        y = self.app.root.winfo_y() + (self.app.root.winfo_height() - self.h) // 2
        self.geometry("%dx%d+%d+%d" % (self.w, self.h, max(0, x), max(0, y)))

    def _start(self):
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        put = self.q.put
        admin = core.is_admin()
        nb = self.app.net or core.net_basic()
        adapter = nb.get("adapter") or ""

        put(("step", 0, "ok", "已记录当前设置"))

        put(("step", 1, "run"))
        ok = core.set_proxy_off()
        put(("step", 1, "ok" if ok else "warn", "代理已关闭" if ok else "无需处理"))

        put(("step", 2, "run"))
        if not adapter:
            put(("step", 2, "fail", "找不到网络适配器"))
        elif not admin:
            put(("step", 2, "warn", "需要管理员权限"))
        else:
            ok, msg = core.set_dns(adapter, core.DNS_SUGGEST)
            put(("step", 2, "ok" if ok else "fail", "223.5.5.5"))

        put(("step", 3, "run"))
        ok, _ = core.flush_dns()
        put(("step", 3, "ok" if ok else "warn", "缓存已清"))

        put(("step", 4, "run"))
        if adapter and admin:
            ok, _ = core.renew_ip(adapter)
            put(("step", 4, "ok" if ok else "warn", "已重新获取"))
        else:
            put(("step", 4, "warn", "需要管理员权限"))

        put(("step", 5, "run"))
        if adapter and admin:
            ok = core.restart_adapter(adapter)
            time.sleep(2)
            put(("step", 5, "ok" if ok else "warn", "已重启"))
        else:
            put(("step", 5, "warn", "需要管理员权限"))

        put(("step", 6, "run"))
        self.app.net = core.net_basic()
        ok = core.port_open("223.5.5.5", 443) or core.dns_probe()[1]
        put(("step", 6, "ok" if ok else "fail", "连通正常" if ok else "仍不通"))
        put(("finish", ok))

    def _poll(self):
        try:
            while True:
                it = self.q.get_nowait()
                if it[0] == "step":
                    idx, st = it[1], it[2]
                    if idx < len(self.rows):
                        self.rows[idx].set(st, it[3] if len(it) > 3 else None)
                elif it[0] == "finish":
                    ok = bool(it[1])
                    self.tip.configure(
                        text=("已经修好了，可以回去刷一下网页试试。" if ok else
                              "还是不通。这通常意味着问题在路由器或运营商那一侧，"
                              "或者需要重置 Winsock（设置 → 网络 → 网络重置）。"),
                        fg=P["accent"] if ok else P["red"])
                    self.app.refresh_net()
                    self.after(1200, self._close)
                    return
        except queue.Empty:
            pass
        self.after(150, self._poll)

    def _close(self):
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()


# --------------------------------------------------------------- 主程序
class App:
    def __init__(self, root):
        self.root = root
        pick_fonts(root)
        root.title("%s %s（Windows）" % (APP_NAME, VERSION))
        root.configure(bg=P["bg"])
        root.geometry("1160x760")
        root.minsize(1020, 690)
        self._set_icon()

        self.b = core.Battery()
        self.net = {}
        self.procs = []
        self.samples = []
        self.events = []
        self.page = "overview"
        self.monitoring = True
        self.q = queue.Queue()
        self.last_sample = None
        self.incident_count = 0
        self.load_pct = 0
        self.cpu_label = ""
        self.sample_count = len(self._load_samples())
        self._last_t = time.time()

        self._build_shell()
        self._build_pages()
        self.show_page("overview")

        threading.Thread(target=self._monitor_loop, daemon=True).start()
        self.root.after(300, self._pump)
        self.root.after(600, self.refresh)
        self.check_previous_run()

    def _set_icon(self):
        for base in (core.resource_dir(), core.app_dir()):
            for name in ("icon.ico", "icon.png"):
                p = os.path.join(base, name)
                if not os.path.exists(p):
                    continue
                try:
                    if name.endswith(".ico"):
                        self.root.iconbitmap(p)
                    else:
                        self._ico = tk.PhotoImage(file=p)
                        self.root.iconphoto(True, self._ico)
                    return
                except Exception:
                    continue

    # ---------- 布局
    def _build_shell(self):
        side = tk.Frame(self.root, bg=P["sidebar"], width=196)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)

        tk.Label(side, text="电池医生", bg=P["sidebar"], fg=P["text"],
                 font=(FONT, 13, "bold"), anchor="w").pack(fill="x", padx=18, pady=(18, 0))
        self.sb_sub = tk.Label(side, text="正在读取…", bg=P["sidebar"], fg=P["muted"],
                               font=(FONT, 8), anchor="w")
        self.sb_sub.pack(fill="x", padx=18, pady=(2, 14))

        self.nav = {}
        items = [("overview", "总览"), ("procs", "进程"), ("storage", "存储"),
                 ("startup", "启动项"), ("network", "网络"), ("trend", "趋势")]
        for key, label in items:
            it = NavItem(side, label, key, self.show_page)
            it.pack(fill="x", padx=8, pady=1)
            self.nav[key] = it

        bottom = tk.Frame(side, bg=P["sidebar"])
        bottom.pack(side="bottom", fill="x", padx=10, pady=12)

        self.mon_chip = Chip(bottom, "监控中", fg=P["accent"], bg=P["accent_soft"], dot=P["accent"])
        self.mon_chip.pack(anchor="w", pady=(0, 8))
        self.mon_btn = RButton(bottom, "暂停监控", self.toggle_monitor, kind="ghost",
                               size=9, width=150)
        self.mon_btn.pack(fill="x", pady=2)
        if not core.is_admin():
            RButton(bottom, "以管理员重启", self._elevate, kind="ghost", size=9,
                    width=150).pack(fill="x", pady=2)

        self.main = tk.Frame(self.root, bg=P["bg"])
        self.main.pack(side="left", fill="both", expand=True)

    def _header(self, parent, title, subtitle, actions=()):
        h = tk.Frame(parent, bg=P["bg"])
        h.pack(fill="x", padx=22, pady=(16, 10))
        left = tk.Frame(h, bg=P["bg"])
        left.pack(side="left")
        tk.Label(left, text=title, bg=P["bg"], fg=P["text"],
                 font=(FONT, 15, "bold"), anchor="w").pack(anchor="w")
        tk.Label(left, text=subtitle, bg=P["bg"], fg=P["muted"],
                 font=(FONT, 9), anchor="w").pack(anchor="w", pady=(1, 0))
        right = tk.Frame(h, bg=P["bg"])
        right.pack(side="right")
        for txt, cmd, kind in actions:
            RButton(right, txt, cmd, kind=kind, size=9).pack(side="left", padx=4)
        return h

    def _build_pages(self):
        self.pages = {}
        self.pages["overview"] = self._build_overview()
        self.pages["procs"] = self._build_procs()
        self.pages["storage"] = self._build_storage()
        self.pages["startup"] = self._build_startup()
        self.pages["network"] = self._build_network()
        self.pages["trend"] = self._build_trend()

    def show_page(self, key):
        self.page = key
        for k, p in self.pages.items():
            if k == key:
                p.pack(fill="both", expand=True)
            else:
                p.pack_forget()
        for k, it in self.nav.items():
            it.set_active(k == key)
        if key == "procs":
            self.refresh_procs()
        elif key == "storage":
            self.refresh_storage()
        elif key == "startup":
            self.refresh_startup()
        elif key == "network":
            self.refresh_net()
        elif key == "trend":
            self.draw_trend()

    # ---------- 总览
    def _build_overview(self):
        page = tk.Frame(self.main, bg=P["bg"])
        self._header(page, "总览", "每 5 秒看一眼供电和电池，有异常会立刻记下来",
                     [("一键体检", self.run_checkup, "primary")])

        body = tk.Frame(page, bg=P["bg"])
        body.pack(fill="both", expand=True, padx=18, pady=(0, 14))

        top = tk.Frame(body, bg=P["bg"])
        top.pack(fill="x")

        ring_card = Card(top, pad=10)
        ring_card.pack(side="left")
        self.ring = Ring(ring_card.body)
        self.ring.pack()

        metrics = tk.Frame(top, bg=P["bg"])
        metrics.pack(side="left", fill="both", expand=True, padx=(12, 0))
        self.m = {}
        specs = [("健康度", "电芯满充 / 设计容量"), ("循环次数", "累计充放电"),
                 ("温度", "电池温度"), ("预计续航", "当前负载下"),
                 ("供电", "当前电力来源"), ("系统负载", "CPU 平均占用")]
        for i, (label, hint) in enumerate(specs):
            c = MetricCard(metrics, label, hint)
            c.grid(row=i // 3, column=i % 3, sticky="nsew", padx=4, pady=4)
            self.m[label] = c
        for i in range(3):
            metrics.grid_columnconfigure(i, weight=1, uniform="m")
        metrics.grid_rowconfigure(0, weight=1)
        metrics.grid_rowconfigure(1, weight=1)

        lower = tk.Frame(body, bg=P["bg"])
        lower.pack(fill="both", expand=True, pady=(12, 0))

        # 先放右侧（定宽），再放左侧（占满剩余）——Windows 的 pack 按顺序切分空间
        right = Card(lower, pad=0, width=322)
        right.pack(side="right", fill="y", padx=(12, 0))
        right.pack_propagate(False)
        tk.Label(right.body, text="结论与建议", bg=P["card"], fg=P["text"],
                 font=(FONT, 10, "bold"), anchor="w").pack(fill="x", padx=14, pady=(12, 4))
        self.advice = tk.Text(right.body, bg=P["card"], fg=P["text2"], bd=0,
                              highlightthickness=0, font=(FONT, 9), wrap="word",
                              spacing1=2, spacing3=5, cursor="arrow")
        self.advice.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        self.advice.configure(state="disabled")

        left = tk.Frame(lower, bg=P["bg"])
        left.pack(side="left", fill="both", expand=True)

        self.status_card = Card(left, pad=16)
        self.status_card.pack(fill="x")
        self.st_title = tk.Label(self.status_card.body, text="正在体检…", bg=P["card"],
                                 fg=P["text"], font=(FONT, 12, "bold"), anchor="w")
        self.st_title.pack(fill="x")
        self.st_desc = tk.Label(self.status_card.body, text="", bg=P["card"], fg=P["text2"],
                                font=(FONT, 9), anchor="w", justify="left", wraplength=396)
        self.st_desc.pack(fill="x", pady=(4, 0))
        self.st_steps = tk.Frame(self.status_card.body, bg=P["card"])
        self.st_steps.pack(fill="x", pady=(6, 0))

        ev_card = Card(left, pad=0)
        ev_card.pack(fill="both", expand=True, pady=(10, 0))
        head = tk.Frame(ev_card.body, bg=P["card"])
        head.pack(fill="x", padx=14, pady=(10, 4))
        tk.Label(head, text="最近的关机与断电记录", bg=P["card"], fg=P["text"],
                 font=(FONT, 10, "bold")).pack(side="left")
        self.ev_chip = Chip(head, "--", fg=P["muted"])
        self.ev_chip.pack(side="right")
        self.ev_list = RowList(ev_card.body, self._ev_row, lambda e: e["time"] + str(e["id"]),
                               empty="没有异常关机记录")
        self.ev_list.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        return page

    def _ev_row(self, parent, e, idx):
        lvl, name, why = core.event_name(e["id"])
        color = {"red": P["red"], "amber": P["amber"], "info": P["muted"]}[lvl]
        f = tk.Frame(parent, bg=P["card"])
        f.pack(fill="x", padx=6, pady=6)
        tk.Label(f, text=e["time"][5:16], bg=P["card"], fg=P["faint"],
                 font=(MONO, 8), width=12, anchor="w").pack(side="left")
        tk.Label(f, text=name, bg=P["card"], fg=color,
                 font=(FONT, 9, "bold"), width=10, anchor="w").pack(side="left")
        tk.Label(f, text=(e["msg"] or why)[:46], bg=P["card"], fg=P["muted"],
                 font=(FONT, 8), anchor="w").pack(side="left", fill="x", expand=True)

    # ---------- 进程
    def _build_procs(self):
        page = tk.Frame(self.main, bg=P["bg"])
        self._header(page, "进程", "按 CPU 排序，找出正在偷偷吃电的那一个",
                     [("结束进程", self.kill_selected, "danger"),
                      ("刷新", self.refresh_procs, "secondary")])
        card = Card(page, pad=0)
        card.pack(fill="both", expand=True, padx=18, pady=(0, 16))
        self.proc_list = RowList(card.body, self._proc_row, lambda r: r[0],
                                 empty="正在读取进程…")
        self.proc_list.pack(fill="both", expand=True, padx=8, pady=8)
        return page

    def _proc_row(self, parent, p, idx):
        pid, cpu, mem, rss, name, path = p
        f = tk.Frame(parent, bg=P["card"])
        f.pack(fill="x", padx=6, pady=5)
        tk.Label(f, text="%4.0f%%" % cpu, bg=P["card"],
                 fg=P["red"] if cpu >= 40 else P["text"],
                 font=(MONO, 9, "bold"), width=6, anchor="w").pack(side="left")
        tk.Label(f, text=name[:26], bg=P["card"], fg=P["text"],
                 font=(FONT, 9), width=26, anchor="w").pack(side="left")
        tk.Label(f, text="%5.1f%% 内存" % mem, bg=P["card"], fg=P["muted"],
                 font=(FONT, 8), width=12, anchor="w").pack(side="left")
        tk.Label(f, text=human(rss), bg=P["card"], fg=P["faint"],
                 font=(FONT, 8), width=10, anchor="w").pack(side="left")
        tk.Label(f, text="PID %d" % pid, bg=P["card"], fg=P["faint"],
                 font=(MONO, 8), anchor="e").pack(side="right", padx=4)

    def refresh_procs(self):
        def work():
            rows, err = core.read_processes(60)
            self.q.put(("procs", rows, err))
        threading.Thread(target=work, daemon=True).start()

    def kill_selected(self):
        key = self.proc_list.selected_key()
        if not key:
            messagebox.showinfo("提示", "先在列表里点一行，再点结束进程。")
            return
        row = next((r for r in self.procs if r[0] == key), None)
        if not row:
            return
        if not messagebox.askyesno("结束进程", "确定结束 %s（PID %d）？\n"
                                   "未保存的内容会丢失。" % (row[4], row[0])):
            return
        ok, msg = core.kill_process(row[0])
        if not ok:
            messagebox.showwarning("没能结束", msg)
        self.refresh_procs()

    # ---------- 存储
    def _build_storage(self):
        page = tk.Frame(self.main, bg=P["bg"])
        self._header(page, "存储", "空间不足会让系统变慢，也会让更新和缓存写失败",
                     [("清理临时文件", self.clean_temp, "secondary"),
                      ("重新扫描", self.refresh_storage, "primary")])
        wrap = tk.Frame(page, bg=P["bg"])
        wrap.pack(fill="both", expand=True, padx=18, pady=(0, 16))

        self.drive_box = tk.Frame(wrap, bg=P["bg"])
        self.drive_box.pack(fill="x")

        card = Card(wrap, pad=0)
        card.pack(fill="both", expand=True, pady=(12, 0))
        tk.Label(card.body, text="占用大头", bg=P["card"], fg=P["text"],
                 font=(FONT, 10, "bold"), anchor="w").pack(fill="x", padx=14, pady=(10, 2))
        self.sto_list = RowList(card.body, self._sto_row, lambda r: r[0],
                                empty="正在统计（大目录需要一点时间）…")
        self.sto_list.pack(fill="both", expand=True, padx=8, pady=6)
        return page

    def _sto_row(self, parent, it, idx):
        name, path, kb = it[0], it[1], it[2]
        real = it[3] if len(it) > 3 else path
        f = tk.Frame(parent, bg=P["card"])
        f.pack(fill="x", padx=6, pady=6)
        tk.Label(f, text=name, bg=P["card"], fg=P["text"],
                 font=(FONT, 9), width=16, anchor="w").pack(side="left")
        tk.Label(f, text=human(kb) if kb >= 0 else "无法读取", bg=P["card"],
                 fg=P["text2"] if kb >= 0 else P["faint"],
                 font=(MONO, 9), width=10, anchor="w").pack(side="left")
        tk.Label(f, text=path[:58], bg=P["card"], fg=P["faint"],
                 font=(FONT, 8), anchor="w").pack(side="left", fill="x", expand=True)
        RButton(f, "打开", lambda p=real: core.open_path(p), kind="ghost",
                size=8, width=54, height=24).pack(side="right")

    def refresh_storage(self):
        for w in self.drive_box.winfo_children():
            w.destroy()
        for d in core.drives():
            L, total, used, free, pct = d
            c = Card(self.drive_box, pad=12)
            c.pack(side="left", fill="x", expand=True, padx=(0, 8))
            tk.Label(c.body, text="%s 盘" % L, bg=P["card"], fg=P["muted"],
                     font=(FONT, 9), anchor="w").pack(fill="x")
            tk.Label(c.body, text="剩 %.1f GB" % free, bg=P["card"],
                     fg=P["red"] if pct >= 90 else P["text"],
                     font=(FONT, 14, "bold"), anchor="w").pack(fill="x")
            bar = tk.Canvas(c.body, height=5, bg=P["card"], highlightthickness=0)
            bar.pack(fill="x", pady=(4, 2))

            def draw(_=None, bar=bar, pct=pct):
                bar.delete("all")
                w = max(10, bar.winfo_width())
                round_rect(bar, 0, 0, w, 5, 2.5, fill=P["track"], outline="")
                col = P["red"] if pct >= 90 else (P["amber"] if pct >= 80 else P["accent"])
                round_rect(bar, 0, 0, max(4, w * pct / 100.0), 5, 2.5, fill=col, outline="")
            bar.bind("<Configure>", draw)
            tk.Label(c.body, text="总 %.1f GB · 已用 %d%%" % (total, pct), bg=P["card"],
                     fg=P["faint"], font=(FONT, 8), anchor="w").pack(fill="x")

        def work():
            items = []
            home = os.path.expanduser("~")
            for name, path in core.storage_targets():
                kb = core.du_kb(path, budget=6)
                if kb > 0:
                    items.append((name, path.replace(home, "~"), kb, path))
            items.sort(key=lambda x: -x[2])
            self.q.put(("storage", items[:14]))
        threading.Thread(target=work, daemon=True).start()

    def clean_temp(self):
        if not messagebox.askyesno("清理临时文件",
                                   "会删除用户临时目录和 Windows\\Temp 里的文件。\n"
                                   "正在运行的程序占用的文件会自动跳过。继续？"):
            return
        freed, msg = core.clean_temp()
        messagebox.showinfo("清理完成", "%s\n释放约 %s" % (msg, human(freed)))
        self.refresh_storage()

    # ---------- 启动项
    def _build_startup(self):
        page = tk.Frame(self.main, bg=P["bg"])
        self._header(page, "启动项", "开机就跟着起来的程序，太多会拖慢开机并持续耗电",
                     [("禁用选中", self.disable_startup, "danger"),
                      ("刷新", self.refresh_startup, "secondary")])
        card = Card(page, pad=0)
        card.pack(fill="both", expand=True, padx=18, pady=(0, 16))
        self.su_list = RowList(card.body, self._su_row, lambda r: r[0] + r[1],
                               empty="正在读取启动项…")
        self.su_list.pack(fill="both", expand=True, padx=8, pady=8)
        return page

    def _su_row(self, parent, it, idx):
        name, cmd, loc, user = it
        f = tk.Frame(parent, bg=P["card"])
        f.pack(fill="x", padx=6, pady=6)
        tk.Label(f, text=name[:30], bg=P["card"], fg=P["text"],
                 font=(FONT, 9), width=30, anchor="w").pack(side="left")
        tk.Label(f, text=(loc or "")[:22], bg=P["card"], fg=P["muted"],
                 font=(FONT, 8), width=22, anchor="w").pack(side="left")
        tk.Label(f, text=(cmd or "")[:60], bg=P["card"], fg=P["faint"],
                 font=(MONO, 8), anchor="w").pack(side="left", fill="x", expand=True)

    def refresh_startup(self):
        def work():
            self.q.put(("startup", core.startup_items()))
        threading.Thread(target=work, daemon=True).start()

    def disable_startup(self):
        key = self.su_list.selected_key()
        if not key:
            messagebox.showinfo("提示", "先点一行选中要禁用的启动项。")
            return
        it = next((s for s in self.startup if s[0] + s[1] == key), None)
        if not it:
            return
        if not messagebox.askyesno("禁用启动项",
                                   "把「%s」从开机启动里去掉？\n"
                                   "（只是改名备份，不是删除，可以恢复）" % it[0]):
            return
        ok, msg = core.disable_startup(it[0], it[1])
        (messagebox.showinfo if ok else messagebox.showwarning)("结果", msg)
        self.refresh_startup()

    # ---------- 网络
    def _build_network(self):
        page = tk.Frame(self.main, bg=P["bg"])
        self._header(page, "网络", "连不上网时，先看是哪一段断了，再动手修",
                     [("一键修复", self.run_net_repair, "primary"),
                      ("重新检测", self.refresh_net, "secondary")])
        wrap = tk.Frame(page, bg=P["bg"])
        wrap.pack(fill="both", expand=True, padx=18, pady=(0, 16))

        top = Card(wrap, pad=14)
        top.pack(fill="x")
        self.net_head = tk.Label(top.body, text="正在检测…", bg=P["card"], fg=P["text"],
                                 font=(FONT, 12, "bold"), anchor="w")
        self.net_head.pack(fill="x")
        self.net_sub = tk.Label(top.body, text="", bg=P["card"], fg=P["muted"],
                                font=(FONT, 9), anchor="w", justify="left",
                                wraplength=700)
        self.net_sub.pack(fill="x", pady=(3, 0))

        card = Card(wrap, pad=0)
        card.pack(fill="both", expand=True, pady=(12, 0))
        self.net_rows = {}
        inner = card.body
        for i, (key, label) in enumerate(core.NET_CHECKS):
            f = tk.Frame(inner, bg=P["card"])
            f.pack(fill="x", padx=16, pady=(9 if i == 0 else 0))
            cv = tk.Canvas(f, width=18, height=18, bg=P["card"], highlightthickness=0)
            cv.pack(side="left", padx=(0, 10))
            tk.Label(f, text=label, bg=P["card"], fg=P["text2"],
                     font=(FONT, 9), width=10, anchor="w").pack(side="left")
            val = tk.Label(f, text="—", bg=P["card"], fg=P["faint"],
                           font=(FONT, 9), anchor="w")
            val.pack(side="left", fill="x", expand=True)
            self.net_rows[key] = (cv, val)
            if i < len(core.NET_CHECKS) - 1:
                tk.Frame(inner, bg=P["line2"], height=1).pack(fill="x", padx=16, pady=8)
        return page

    def _net_mark(self, key, state, text):
        cv, val = self.net_rows[key]
        color = {"ok": P["green"], "warn": P["amber"], "fail": P["red"],
                 "run": P["faint"], "skip": P["faint"]}.get(state, P["faint"])
        glyph = {"ok": "✓", "warn": "!", "fail": "×", "run": "…"}.get(state, "")
        cv.delete("all")
        cv.create_oval(2, 2, 16, 16, outline=color, width=1.5)
        if glyph:
            cv.create_text(9, 9, text=glyph, fill=color, font=(FONT, 8, "bold"))
        val.configure(text=text, fg=color if state in ("fail", "warn") else P["text2"])

    def refresh_net(self):
        for k, _ in core.NET_CHECKS:
            self._net_mark(k, "run", "检测中…")

        def work():
            nb = core.net_basic()
            self.net = nb
            out = {"net": nb}
            out["dns_ms"], out["dns_ok"] = core.dns_probe()
            out["ping"] = core.ping_avg(nb.get("gw") or "223.5.5.5", 2) if nb.get("gw") else -1
            out["in"] = core.port_open("223.5.5.5", 443)
            out["px_on"], out["px_srv"] = core.proxy_state()
            out["hosts_n"], out["hosts_hits"] = core.hosts_suspicious()
            self.q.put(("net", out))

        threading.Thread(target=work, daemon=True).start()

    def _render_net(self, d):
        nb = d["net"]
        has_link = bool(nb.get("adapter"))
        self._net_mark("wifi", "ok" if has_link else "fail",
                       "%s %s" % (nb.get("type") or "网络", nb.get("adapter") or "未连接"))
        sig = nb.get("signal") or 0
        if nb.get("type") == "无线":
            self._net_mark("signal", "ok" if sig >= 60 else ("warn" if sig >= 35 else "fail"),
                           "%s 信号 %d%%" % (nb.get("ssid") or "-", sig))
        else:
            self._net_mark("signal", "skip", "有线连接，无需信号")

        self._net_mark("ip", "ok" if nb.get("ip") else "fail", nb.get("ip") or "没有拿到 IP")
        self._net_mark("gateway", "ok" if nb.get("gw") else "fail",
                       "%s%s" % (nb.get("gw") or "无网关",
                                 "" if d["ping"] < 0 else " · 延迟 %d ms" % d["ping"]))
        dns = ", ".join(nb.get("dns") or []) or "未配置"
        if d["dns_ok"]:
            self._net_mark("dns", "ok" if d["dns_ms"] < 400 else "warn",
                           "%s · %d ms" % (dns, d["dns_ms"]))
        else:
            self._net_mark("dns", "fail", "%s · 解析失败" % dns)
        self._net_mark("internet", "ok" if d["in"] else "fail",
                       "可以连通外网" if d["in"] else "外网不通")
        self._net_mark("proxy", "warn" if d["px_on"] else "ok",
                       ("开着：%s" % d["px_srv"]) if d["px_on"] else "未开启")
        if d["hosts_hits"]:
            self._net_mark("hosts", "warn", "%d 条异常：%s" % (d["hosts_n"], ", ".join(d["hosts_hits"][:3])))
        else:
            self._net_mark("hosts", "ok", "%d 条正常记录" % d["hosts_n"])

        if not has_link:
            self.net_head.configure(text="没有可用的网络连接")
            self.net_sub.configure(text="先确认网线插好或 Wi-Fi 已打开。")
        elif d["in"]:
            self.net_head.configure(text="网络是通的", fg=P["accent"])
            self.net_sub.configure(text="如果某些网站打不开，多半是 DNS 或代理设置，"
                                        "可以点「一键修复」把这两处重置。")
        else:
            self.net_head.configure(text="连上了路由器，但出不去", fg=P["red"])
            self.net_sub.configure(text="这种最常见：DNS 被改坏、代理残留、或者运营商线路问题。"
                                        "点「一键修复」会依次重置代理和 DNS 并重新获取地址。")

    def run_net_repair(self):
        if not core.is_admin():
            if messagebox.askyesno("需要管理员权限",
                                   "重置 DNS、重启网卡需要管理员权限。\n"
                                   "现在以管理员身份重启本程序吗？\n"
                                   "（重启后请再点一次一键修复）"):
                core.elevate()
            return
        NetRepairDialog(self)

    def run_checkup(self):
        CheckupDialog(self)

    def on_checkup_done(self, level, text, report):
        self.add_event("体检完成：" + text.split("\n")[0][:40],
                       "red" if level == "red" else "info")
        if report:
            self.add_event("报告已保存到桌面", "info")

    # ---------- 趋势
    def _build_trend(self):
        page = tk.Frame(self.main, bg=P["bg"])
        self._header(page, "趋势", "把电量、健康度和温度画出来，异常会很明显",
                     [("导出 HTML 报告", self.export_trend, "secondary"),
                      ("刷新", self.draw_trend, "ghost")])
        card = Card(page, pad=10)
        card.pack(fill="both", expand=True, padx=18, pady=(0, 16))
        self.chart = tk.Canvas(card.body, bg=P["card"], highlightthickness=0)
        self.chart.pack(fill="both", expand=True)
        self.chart.bind("<Configure>", lambda e: self.draw_trend())
        return page

    def draw_trend(self):
        if not hasattr(self, "chart"):
            return
        c = self.chart
        c.delete("all")
        rows = self._load_samples()
        w = max(400, c.winfo_width())
        h = max(280, c.winfo_height())
        pad_l, pad_r, pad_t, pad_b = 44, 16, 18, 30

        if len(rows) < 2:
            c.create_text(w / 2, h / 2, text="数据还太少，让它跑一会儿再来看",
                          fill=P["faint"], font=(FONT, 11))
            return

        pcts = [r["pct"] for r in rows]
        temps = [r["temp"] for r in rows]
        n = len(rows)
        plot_w, plot_h = w - pad_l - pad_r, h - pad_t - pad_b

        for i in range(5):
            y = pad_t + plot_h * i / 4.0
            c.create_line(pad_l, y, w - pad_r, y, fill=P["line2"])
            c.create_text(pad_l - 8, y, text="%d" % (100 - i * 25), anchor="e",
                          fill=P["faint"], font=(FONT, 8))

        def xy(i, v):
            x = pad_l + plot_w * (i / float(max(1, n - 1)))
            y = pad_t + plot_h * (1 - max(0, min(100, v)) / 100.0)
            return x, y

        pts = []
        for i, v in enumerate(pcts):
            pts.extend(xy(i, v))
        if len(pts) >= 4:
            c.create_line(*pts, fill=P["accent"], width=2, smooth=False)
            # 断电点：相邻采样跌幅超过 8% 或时间间隔超过 2 分钟
            for i in range(1, n):
                gap = (rows[i]["t"] - rows[i - 1]["t"]) > 120
                drop = (pcts[i - 1] - pcts[i]) > 8
                if gap or drop:
                    x, y = xy(i, pcts[i])
                    c.create_oval(x - 3.5, y - 3.5, x + 3.5, y + 3.5,
                                  fill=P["red"], outline="")

        tpts = []
        for i, v in enumerate(temps):
            tpts.extend(xy(i, min(100, v * 2)))   # 温度 0-50℃ 映射到 0-100
        if len(tpts) >= 4:
            c.create_line(*tpts, fill=P["amber"], width=1, dash=(3, 4))

        c.create_text(pad_l, pad_t - 6, text="电量 %", anchor="w", fill=P["faint"],
                      font=(FONT, 8))
        c.create_text(w - pad_r, pad_t - 6, text="橙线=温度(×2)", anchor="e",
                      fill=P["faint"], font=(FONT, 8))
        c.create_text(pad_l, h - pad_b + 12,
                      text=rows[0]["time"][5:16], anchor="w", fill=P["faint"],
                      font=(FONT, 8))
        c.create_text(w - pad_r, h - pad_b + 12,
                      text=rows[-1]["time"][5:16], anchor="e", fill=P["faint"],
                      font=(FONT, 8))
        c.create_text(w / 2, h - pad_b + 12,
                      text="共 %d 个采样点" % n, fill=P["faint"], font=(FONT, 8))

    def _load_samples(self):
        out = []
        if not os.path.exists(core.CSV):
            return out
        try:
            with open(core.CSV, "r", encoding="utf-8", errors="ignore") as f:
                for r in csv.DictReader(f):
                    try:
                        out.append({"t": float(r["timestamp"]), "time": r["iso_time"],
                                    "pct": float(r["pct"]), "temp": float(r["temp_C"]),
                                    "health": float(r["health_pct"])})
                    except Exception:
                        continue
        except Exception:
            pass
        return out[-600:]

    def export_trend(self):
        rows = self._load_samples()
        if not rows:
            messagebox.showinfo("提示", "还没有采样数据。")
            return
        path = os.path.join(core.desktop_dir(),
                            "电池医生趋势-%s.html" % time.strftime("%Y%m%d-%H%M"))
        W, H, PL, PT = 900, 360, 50, 20
        n = len(rows)
        pts = []
        for i, r in enumerate(rows):
            x = PL + (W - PL - 20) * i / float(max(1, n - 1))
            y = PT + (H - PT - 40) * (1 - r["pct"] / 100.0)
            pts.append("%.1f,%.1f" % (x, y))
        svg = ['<svg viewBox="0 0 %d %d" width="%d" height="%d" '
               'xmlns="http://www.w3.org/2000/svg" style="background:#fff">' % (W, H, W, H)]
        for i in range(5):
            y = PT + (H - PT - 40) * i / 4.0
            svg.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#EFEFE9"/>'
                       % (PL, y, W - 20, y))
            svg.append('<text x="%d" y="%.1f" fill="#AFAFB4" font-size="11" '
                       'text-anchor="end" font-family="Microsoft YaHei">%d</text>'
                       % (PL - 8, y + 4, 100 - i * 25))
        svg.append('<polyline fill="none" stroke="#2F7D66" stroke-width="2" points="%s"/>'
                   % " ".join(pts))
        for i in range(1, n):
            if rows[i - 1]["pct"] - rows[i]["pct"] > 8 or rows[i]["t"] - rows[i - 1]["t"] > 120:
                x, y = pts[i].split(",")
                svg.append('<circle cx="%s" cy="%s" r="4" fill="#B8554A"/>' % (x, y))
        svg.append('<text x="%d" y="%d" fill="#8B8B90" font-size="11" '
                   'font-family="Microsoft YaHei">%s</text>' % (PL, H - 12, rows[0]["time"]))
        svg.append('<text x="%d" y="%d" fill="#8B8B90" font-size="11" text-anchor="end" '
                   'font-family="Microsoft YaHei">%s</text>' % (W - 20, H - 12, rows[-1]["time"]))
        svg.append("</svg>")
        body = "".join(svg)
        doc = ("<!doctype html><meta charset='utf-8'><title>电池医生趋势</title>"
               "<body style='margin:0;background:#F6F6F3;font-family:Microsoft YaHei'>"
               "<div style='max-width:960px;margin:24px auto;background:#fff;padding:24px;"
               "border-radius:12px'>"
               "<h2 style='margin:0 0 4px;font-size:18px'>电池医生 · 电量趋势</h2>"
               "<p style='color:#8B8B90;font-size:12px;margin:0 0 16px'>"
               "红点=疑似断电点（跌幅超过 8%% 或采样中断超过 2 分钟）</p>"
               "%s</div></body>" % body)
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(doc)
            core.open_path(path)
        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    # ---------- 事件 / 刷新
    def add_event(self, text, level="info"):
        core.log(text)
        self.ev_list.set_items(list(reversed(self._recent_log(24))))

    def _recent_log(self, n=24):
        out = []
        if not os.path.exists(core.APPLOG):
            return out
        try:
            with open(core.APPLOG, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()[-n:]
            for line in lines:
                s = line.strip()
                if not s:
                    continue
                t = s[:19]
                out.append({"id": 0, "time": t, "provider": "app", "msg": s[20:120]})
        except Exception:
            pass
        return out

    def refresh(self):
        try:
            b = core.Battery.read()
        except Exception as e:
            core.log("读取电池失败：%s" % e)
            return
        self.b = b
        lvl, title, desc, steps = b.explain()
        color = {"green": P["accent"], "amber": P["amber"], "red": P["red"]}[lvl]

        self.ring.draw(b.pct, b.health or 0, color,
                       "充电中" if b.charging == "Yes" else ("已接通电源" if b.on_ac else "电池供电"))
        self.m["健康度"].set("%d%%" % b.health if b.health else "--",
                          P["red"] if b.health and b.health < 60 else P["text"],
                          "满充 %d / 设计 %d" % (b.maxcap, b.design) if b.design else "读不到设计容量")
        self.m["循环次数"].set("%d" % b.cycle if b.cycle else "--", hint="超过 800 次算高损耗")
        self.m["温度"].set("%.1f℃" % b.temp_c if b.temp else "--",
                         P["red"] if b.temp_c >= 75 else P["text"], "电池温度")
        rt = b.runtime
        self.m["预计续航"].set(("%d 小时 %02d 分" % (rt // 60, rt % 60)) if rt > 0 else "--",
                            hint="充满电还能用多久")
        self.m["供电"].set(b.source, color, "已接电源" if b.on_ac else "未接电源")
        self.m["系统负载"].set("%d%%" % self.load_pct,
                            P["red"] if self.load_pct >= 85 else P["text"],
                            "CPU 平均占用（%s）" % (self.cpu_label or "本机"))

        self.st_title.configure(text=title, fg=color)
        self.st_desc.configure(text=desc)
        for w in self.st_steps.winfo_children():
            w.destroy()
        for s in steps[:4]:
            row = tk.Frame(self.st_steps, bg=P["card"])
            row.pack(fill="x", pady=1)
            tk.Label(row, text="·", bg=P["card"], fg=color,
                     font=(FONT, 9, "bold")).pack(side="left", padx=(0, 6))
            tk.Label(row, text=s, bg=P["card"], fg=P["text2"], font=(FONT, 9),
                     anchor="w", wraplength=386, justify="left").pack(side="left")

        self.advice.configure(state="normal")
        self.advice.delete("1.0", "end")
        body = ["%s\n" % title]
        if steps:
            body.append("建议：")
            for i, s in enumerate(steps, 1):
                body.append("%d. %s" % (i, s))
        body.append("")
        body.append("监控状态：%s" % ("运行中，每 5 秒一次" if self.monitoring else "已暂停"))
        body.append("本次记录：%d 个采样点" % self.sample_count)
        if self.incident_count:
            body.append("已发现疑似断电：%d 次" % self.incident_count)
        self.advice.insert("1.0", "\n".join(body))
        self.advice.configure(state="disabled")

        self.sb_sub.configure(text="%s · %d%% · %s" % (b.source, b.pct,
                                                       "充电" if b.charging == "Yes" else "放电"))

    # ---------- 监控线程
    def _monitor_loop(self):
        tick = 0
        while True:
            try:
                if tick == 0:
                    self.cpu_label = core.cpu_name().replace("(R)", "").replace("(TM)", "")[:22]
                if tick % 6 == 0:
                    self.load_pct = core.cpu_load()
                if self.monitoring:
                    b = core.Battery.read()
                    self.q.put(("sample", b))
                tick += 1
                time.sleep(5 if self.monitoring else 2)
            except Exception as e:
                core.log("监控异常：%s" % e)
                time.sleep(5)

    def _write_csv(self, b):
        new = not os.path.exists(core.CSV)
        try:
            with open(core.CSV, "a", encoding="utf-8", newline="") as f:
                w = csv.writer(f)
                if new:
                    w.writerow(core.CSV_HEADER.split(","))
                w.writerow([int(time.time()), time.strftime("%Y-%m-%d %H:%M:%S"),
                            b.source, b.pct, b.cur, b.maxcap, b.design, b.health,
                            b.ma, b.volt, b.temp_c, b.cycle, b.adapter,
                            b.limit if b.limit is not None else "", b.charging, ""])
            self.sample_count += 1
        except Exception as e:
            core.log("写采样失败：%s" % e)

    def _detect_incident(self, b):
        prev = self.last_sample
        now = time.time()
        dt = now - self._last_t
        self._last_t = now          # 每个采样点都要推进，否则间隔会一直累积
        self.last_sample = b
        if not prev:
            return
        drop = prev.pct - b.pct
        if (dt > 120 and prev.pct > 25) or drop >= 8:
            self.incident_count += 1
            line = ("%s 疑似断电：上次 %d%% (%s) → 现在 %d%% (%s)，间隔 %.0f 分钟"
                    % (time.strftime("%Y-%m-%d %H:%M:%S"), prev.pct, prev.source,
                       b.pct, b.source, dt / 60.0))
            try:
                with open(core.INCIDENT, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except Exception:
                pass
            self.add_event(line, "red")
            core.notify("检测到断电", line)
        self._last_t = time.time()

    def _pump(self):
        try:
            while True:
                kind, *rest = self.q.get_nowait()
                if kind == "sample":
                    b = rest[0]
                    self._write_csv(b)
                    if not hasattr(self, "_last_t"):
                        self._last_t = time.time()
                    self._detect_incident(b)
                    if self.page == "overview":
                        self.refresh()
                elif kind == "procs":
                    rows, err = rest
                    self.procs = rows or []
                    self.proc_list.set_items(self.procs)
                elif kind == "storage":
                    self.sto_list.set_items(rest[0])
                elif kind == "startup":
                    self.startup = rest[0]
                    self.su_list.set_items(self.startup)
                elif kind == "net":
                    self._render_net(rest[0])
                elif kind == "events":
                    self.events = rest[0]
                    self.ev_list.set_items(self.events)
                    bad = sum(1 for e in self.events if e["id"] in (41, 6008))
                    self.ev_chip.set("%d 次异常" % bad if bad else "正常",
                                     fg=P["red"] if bad else P["accent"],
                                     bg=P["red_soft"] if bad else P["green_soft"],
                                     dot=P["red"] if bad else P["accent"])
        except queue.Empty:
            pass
        self.root.after(400, self._pump)

    def load_events(self):
        def work():
            self.q.put(("events", core.shutdown_events(20)))
        threading.Thread(target=work, daemon=True).start()

    def toggle_monitor(self):
        self.monitoring = not self.monitoring
        if self.monitoring:
            self.mon_chip.set("监控中", fg=P["accent"], bg=P["accent_soft"], dot=P["accent"])
            self.mon_btn.set_text("暂停监控")
        else:
            self.mon_chip.set("已暂停", fg=P["muted"], bg=P["card2"], dot=P["faint"])
            self.mon_btn.set_text("恢复监控")
        self.refresh()

    def _elevate(self):
        if core.elevate():
            self.root.after(400, self.root.destroy)

    def check_previous_run(self):
        """上次如果不是点关闭退出，说明中间断过电 —— 这本身就是证据"""
        try:
            rows = self._load_samples()
            if rows and os.path.exists(core.CSV):
                last_ts = rows[-1]["t"]
                clean_ts = (os.path.getmtime(core.CLEAN)
                            if os.path.exists(core.CLEAN) else 0)
                if clean_ts and last_ts > clean_ts + 180:
                    self.add_event("%s 程序没有正常关闭（随后系统断电，采样停在 %d%%）"
                                   % (rows[-1]["time"], int(rows[-1]["pct"])), "red")
        except Exception as e:
            core.log("检查上次退出失败：%s" % e)
        self.load_events()
        self.startup = []
        self.refresh_procs()

    def on_close(self):
        try:
            with open(core.CLEAN, "w", encoding="utf-8") as f:
                f.write(time.strftime("%Y-%m-%d %H:%M:%S"))
        except Exception:
            pass
        self.root.destroy()


def run():
    root = tk.Tk()
    app = App(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)

    # 自检钩子：BD_SMOKE=1 时把所有页面过一遍再退出，用于验证界面不会崩
    if os.environ.get("BD_SMOKE"):
        def smoke():
            try:
                for k in ("procs", "storage", "startup", "network", "trend", "overview"):
                    app.show_page(k)
                    root.update()
                    time.sleep(0.15)
                app.refresh()
                root.update()
                d1 = CheckupDialog(app)
                for _ in range(30):
                    root.update()
                    time.sleep(0.1)
                d1._close()
                d2 = NetRepairDialog(app)
                for _ in range(30):
                    root.update()
                    time.sleep(0.1)
                d2._close()
                print("SMOKE OK: %d pages, checkup+repair dialogs closed cleanly"
                      % len(app.pages))
            except Exception:
                import traceback
                traceback.print_exc()
            finally:
                root.after(80, root.destroy)
        root.after(1500, smoke)

    root.mainloop()
