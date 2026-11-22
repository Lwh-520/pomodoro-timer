# -*- coding: utf-8 -*-
"""
番茄闹钟 —— 桌面番茄工作法计时器
单文件、无第三方依赖（仅需系统自带 tkinter）。

用法：
  双击运行，或命令行:  pythonw 番茄闹钟.pyw
  打包成独立 exe:     pyinstaller -F -w 番茄闹钟.pyw
"""

import os
import sys
import time
import json
import tkinter as tk
from tkinter import messagebox

try:
    import winsound
except ImportError:
    winsound = None


APP_TITLE = "番茄闹钟"
CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(sys.argv[0])), "pomodoro_config.json"
)

DEFAULTS = {
    "work_min": 25,
    "short_min": 5,
    "long_min": 15,
    "long_every": 4,
    "auto_start": False,
    "always_on_top": False,
}

PHASE_WORK = 0
PHASE_SHORT = 1
PHASE_LONG = 2

PHASE_NAME = {PHASE_WORK: "工作", PHASE_SHORT: "短休息", PHASE_LONG: "长休息"}
PHASE_ACCENT = {
    PHASE_WORK: "#E74C3C",
    PHASE_SHORT: "#27AE60",
    PHASE_LONG: "#2980B9",
}

BG = "#F4F5F7"
TEXT = "#2C3E50"
MUTED = "#8A94A6"
RING_BG = "#E8EAEF"


def play_alert():
    """一段清脆的三音提示音，失败则退回系统提示。"""
    if winsound is not None:
        try:
            for freq, dur in ((784, 150), (988, 150), (1319, 240)):
                winsound.Beep(freq, dur)
            return
        except Exception:
            try:
                winsound.MessageBeep()
                return
            except Exception:
                pass
    try:
        sys.stdout.write("\a")
        sys.stdout.flush()
    except Exception:
        pass


class PomodoroApp:
    def __init__(self, root):
        self.root = root
        self.cfg = self._load_config()

        root.title(APP_TITLE)
        root.configure(bg=BG)
        root.geometry("400x620")
        root.resizable(False, False)

        self.phase = PHASE_WORK
        self.remaining = float(self.cfg["work_min"] * 60)
        self.total = self.remaining
        self.running = False
        self.pomodoro_count = 0   # 本次会话完成的工作番茄数
        self.cycle_count = 0      # 当前轮次内已完成的工作番茄数
        self._last = None
        self._after = None

        self.auto_start = tk.BooleanVar(value=bool(self.cfg["auto_start"]))
        self.topmost = tk.BooleanVar(value=bool(self.cfg["always_on_top"]))

        self._build_ui()
        self._apply_topmost()
        self._refresh()

        root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------- 配置 ----------
    def _load_config(self):
        cfg = dict(DEFAULTS)
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                for k in DEFAULTS:
                    if k in data:
                        cfg[k] = data[k]
        except (OSError, ValueError):
            pass
        return cfg

    def _save_config(self):
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self.cfg, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    # ---------- 界面 ----------
    def _build_ui(self):
        top = tk.Frame(self.root, bg=BG)
        top.pack(fill="x", padx=20, pady=(16, 4))
        tk.Label(top, text=APP_TITLE, font=("Microsoft YaHei UI", 15, "bold"),
                 bg=BG, fg=TEXT).pack(side="left")
        tk.Checkbutton(top, text="置顶", variable=self.topmost, command=self._apply_topmost,
                       bg=BG, fg=MUTED, activebackground=BG, selectcolor="#FFFFFF",
                       font=("Microsoft YaHei UI", 10)).pack(side="right")

        self.canvas = tk.Canvas(self.root, width=320, height=320, bg=BG, highlightthickness=0)
        self.canvas.pack(pady=(8, 0))
        self._draw_ring()

        self.phase_lbl = tk.Label(self.root, text="", font=("Microsoft YaHei UI", 16, "bold"),
                                  bg=BG, fg=TEXT)
        self.phase_lbl.pack(pady=(10, 0))
        self.dots_lbl = tk.Label(self.root, text="", font=("Microsoft YaHei UI", 13),
                                 bg=BG, fg=MUTED)
        self.dots_lbl.pack(pady=(2, 0))

        btns = tk.Frame(self.root, bg=BG)
        btns.pack(pady=14)
        self.start_btn = self._make_button(btns, "开始", self._toggle, "#2ECC71", "#FFFFFF")
        self.reset_btn = self._make_button(btns, "重置", self._reset, "#BDC3C7", "#FFFFFF")
        self.skip_btn = self._make_button(btns, "跳过", self._skip, "#BDC3C7", "#FFFFFF")
        for b in (self.start_btn, self.reset_btn, self.skip_btn):
            b.pack(side="left", padx=6)

        opts = tk.Frame(self.root, bg=BG)
        opts.pack(pady=(0, 6))
        tk.Checkbutton(opts, text="自动开始下一阶段", variable=self.auto_start,
                       bg=BG, fg=MUTED, activebackground=BG, selectcolor="#FFFFFF",
                       font=("Microsoft YaHei UI", 10)).pack(side="left")
        tk.Button(opts, text="⚙ 设置", command=self._open_settings, relief="flat",
                  bg=BG, fg="#3498DB", activebackground=BG,
                  font=("Microsoft YaHei UI", 10), cursor="hand2").pack(side="left", padx=(14, 0))

        self.counter_lbl = tk.Label(self.root, text="", font=("Microsoft YaHei UI", 10),
                                    bg=BG, fg=MUTED)
        self.counter_lbl.pack(pady=(2, 10))

    def _make_button(self, parent, text, command, bg, fg):
        return tk.Button(parent, text=text, command=command,
                         font=("Microsoft YaHei UI", 12, "bold"),
                         bg=bg, fg=fg, activebackground=bg, activeforeground=fg,
                         relief="flat", bd=0, padx=22, pady=8, cursor="hand2")

    def _draw_ring(self):
        pad = 20
        d = 320
        self.canvas.create_oval(pad, pad, d - pad, d - pad, outline=RING_BG, width=14)
        self._ring_fg = self.canvas.create_arc(
            pad, pad, d - pad, d - pad, start=90, extent=-360,
            style="arc", outline=PHASE_ACCENT[self.phase], width=14)
        self._time_text = self.canvas.create_text(
            d // 2, d // 2, text="25:00", font=("Consolas", 50, "bold"), fill=TEXT)

    # ---------- 状态刷新 ----------
    def _refresh(self):
        accent = PHASE_ACCENT[self.phase]
        self.canvas.itemconfigure(self._ring_fg, outline=accent)
        frac = max(0.0, min(1.0, self.remaining / self.total)) if self.total > 0 else 0.0
        extent = 360.0 * frac
        self.canvas.itemconfigure(self._ring_fg, extent=(-extent if extent > 0.5 else 0))

        secs = int(round(self.remaining))
        m, s = divmod(max(0, secs), 60)
        self.canvas.itemconfigure(self._time_text, text="%02d:%02d" % (m, s))

        self.phase_lbl.configure(text=PHASE_NAME[self.phase], fg=accent)
        n = self.cfg["long_every"]
        dots = "🍅" * self.cycle_count + "○" * (n - self.cycle_count)
        self.dots_lbl.configure(text=dots)
        self.counter_lbl.configure(text="本次已完成 %d 个番茄" % self.pomodoro_count)

        if self.running:
            self.start_btn.configure(text="暂停", bg="#E67E22")
        else:
            self.start_btn.configure(text="开始", bg="#2ECC71")

    # ---------- 计时 ----------
    def _phase_duration(self):
        if self.phase == PHASE_WORK:
            return self.cfg["work_min"] * 60
        if self.phase == PHASE_SHORT:
            return self.cfg["short_min"] * 60
        return self.cfg["long_min"] * 60

    def _toggle(self):
        if self.running:
            self._pause()
        else:
            self._start()

    def _start(self):
        if self.running:
            return
        self.running = True
        self._last = time.monotonic()
        self._refresh()
        self._schedule()

    def _pause(self):
        self.running = False
        if self._after is not None:
            try:
                self.root.after_cancel(self._after)
            except tk.TclError:
                pass
            self._after = None
        self._refresh()

    def _schedule(self):
        self._after = self.root.after(100, self._tick)

    def _tick(self):
        if not self.running:
            self._after = None
            return
        now = time.monotonic()
        if self._last is not None:
            self.remaining -= (now - self._last)
        self._last = now
        if self.remaining <= 0:
            self.remaining = 0
            self._refresh()
            self._on_end()
            return
        self._refresh()
        self._schedule()

    def _reset(self):
        self.running = False
        if self._after is not None:
            try:
                self.root.after_cancel(self._after)
            except tk.TclError:
                pass
            self._after = None
        self.remaining = self._phase_duration()
        self.total = self.remaining
        self._refresh()

    def _skip(self):
        self.running = False
        if self._after is not None:
            try:
                self.root.after_cancel(self._after)
            except tk.TclError:
                pass
            self._after = None
        self._advance()
        self._refresh()

    # ---------- 阶段切换 ----------
    def _on_end(self):
        self.running = False
        self._after = None
        play_alert()
        self._flash()
        self._advance()
        if self.auto_start.get():
            self._start()

    def _advance(self):
        if self.phase == PHASE_WORK:
            self.pomodoro_count += 1
            self.cycle_count += 1
            if self.cycle_count >= self.cfg["long_every"]:
                self.phase = PHASE_LONG
                self.cycle_count = 0
            else:
                self.phase = PHASE_SHORT
        else:
            self.phase = PHASE_WORK
        self.remaining = self._phase_duration()
        self.total = self.remaining

    # ---------- 提醒 ----------
    def _flash(self):
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.attributes("-topmost", True)
            self.root.after(800, lambda: self.root.attributes("-topmost", self.topmost.get()))
        except tk.TclError:
            pass
        self._set_title("⏰ 时间到！")
        self.root.after(2500, lambda: self._set_title(APP_TITLE))

    def _set_title(self, text):
        try:
            self.root.title(text)
        except tk.TclError:
            pass

    def _apply_topmost(self):
        try:
            self.root.attributes("-topmost", self.topmost.get())
        except tk.TclError:
            pass

    # ---------- 设置 ----------
    def _open_settings(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("设置")
        dlg.configure(bg=BG)
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.geometry("+%d+%d" % (self.root.winfo_rootx() + 50, self.root.winfo_rooty() + 130))

        rows = [
            ("工作时长（分钟）", "work_min", 1, 180),
            ("短休息（分钟）", "short_min", 1, 60),
            ("长休息（分钟）", "long_min", 1, 120),
            ("长休息间隔（个番茄）", "long_every", 2, 12),
        ]
        vars_ = {}
        body = tk.Frame(dlg, bg=BG)
        body.pack(padx=22, pady=18)
        for i, (label, key, lo, hi) in enumerate(rows):
            tk.Label(body, text=label, bg=BG, fg=TEXT,
                     font=("Microsoft YaHei UI", 11)).grid(row=i, column=0, sticky="w", pady=6)
            v = tk.IntVar(value=int(self.cfg[key]))
            vars_[key] = v
            tk.Spinbox(body, from_=lo, to=hi, textvariable=v, width=6, justify="center",
                       font=("Microsoft YaHei UI", 11)).grid(row=i, column=1, sticky="e",
                                                             padx=(24, 0), pady=6)

        def _save():
            for key in ("work_min", "short_min", "long_min", "long_every"):
                try:
                    self.cfg[key] = int(vars_[key].get())
                except (tk.TclError, ValueError):
                    continue
            self._save_config()
            if not self.running:
                self.remaining = self._phase_duration()
                self.total = self.remaining
            dlg.destroy()
            self._refresh()

        btns = tk.Frame(body, bg=BG)
        btns.grid(row=len(rows), column=0, columnspan=2, pady=(18, 0))
        self._make_button(btns, "取消", dlg.destroy, "#BDC3C7", "#FFFFFF").pack(side="left", padx=6)
        self._make_button(btns, "保存", _save, "#3498DB", "#FFFFFF").pack(side="left", padx=6)

    def _on_close(self):
        self._save_config()
        if self._after is not None:
            try:
                self.root.after_cancel(self._after)
            except tk.TclError:
                pass
        self.root.destroy()


def main():
    root = tk.Tk()
    PomodoroApp(root)
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        err = traceback.format_exc()
        try:
            messagebox.showerror(APP_TITLE, "程序出错：\n" + err)
        except Exception:
            sys.stderr.write(err)
        raise SystemExit(1)
