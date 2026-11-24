from contextlib import redirect_stderr, redirect_stdout
import os
from pathlib import Path
from queue import Empty, SimpleQueue
from threading import Thread
from time import monotonic
import tkinter as tk
from tkinter import messagebox, ttk

from bilibili_audio_module_ai import ffmpeg_command
from local_config import APP_DIR, get_config, read_local_config, save_credentials, write_local_text
from main_controller_ai_choice import KEYWORD_FILE, run_keywords


BACKGROUND = "#F1F5FA"
WHITE = "#FFFFFF"
INK = "#132641"
MUTED = "#50627A"
BORDER = "#DCE5EF"
NAV = "#0D2039"
NAV_ACTIVE = "#233C59"
ACCENT = "#006B61"
FONT = "Segoe UI"


class TaskOutput:
    def __init__(self, events, secrets):
        self.events = events
        self.secrets = tuple(value for value in secrets if value)
        self.last_progress = 0

    def write(self, text):
        for secret in self.secrets:
            text = text.replace(secret, "[已隐藏]")
        if text.startswith("\r"):
            now = monotonic()
            if now - self.last_progress >= 0.35:
                self.events.put(("progress", text.strip()))
                self.last_progress = now
        elif text and text != ".":
            self.events.put(("log", text))
        return len(text)

    def flush(self):
        pass


def label(parent, text, *, size=10, color=INK, background=WHITE, bold=False):
    return tk.Label(
        parent, text=text, fg=color, bg=background, anchor="w",
        font=(FONT, size, "bold" if bold else "normal"),
    )


class MusicCrawlerWindow:
    def __init__(self, root):
        self.root = root
        self.events = SimpleQueue()
        self.running = False
        self.status = tk.StringVar(value="就绪")
        self.progress = tk.StringVar(value="")
        root.title("AI Music Crawler")
        root.geometry("1030x720")
        root.minsize(880, 660)
        root.configure(bg=BACKGROUND)
        icon_dir = Path(__file__).resolve().parent
        icon = icon_dir / "assets" / "app.ico"
        if icon.is_file():
            root.iconbitmap(str(icon))
        root.protocol("WM_DELETE_WINDOW", self.close)

        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("Action.TButton", font=(FONT, 10, "bold"), padding=(17, 9),
                        background=ACCENT, foreground=WHITE, borderwidth=0)
        style.map("Action.TButton", background=[("disabled", "#91AAA7"), ("active", "#00574F")])
        style.configure("Outline.TButton", font=(FONT, 10), padding=(13, 7),
                        background="#E8EFF7", foreground=INK, borderwidth=0)
        style.map("Outline.TButton", background=[("active", "#D4E3F1")])
        style.configure("Settings.TEntry", padding=9, foreground=INK, fieldbackground=WHITE)
        style.configure("Settings.TCheckbutton", background=WHITE, foreground=INK, font=(FONT, 10))

        sidebar = tk.Frame(root, bg=NAV, width=210)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        label(sidebar, "AI Music", size=21, color=WHITE, background=NAV, bold=True).pack(
            fill="x", padx=22, pady=(32, 0)
        )
        label(sidebar, "Crawler", size=21, color="#61E6CB", background=NAV, bold=True).pack(
            fill="x", padx=22, pady=(0, 31)
        )
        self.nav = {}
        for name, title in (("tasks", "下载任务"), ("settings", "设置")):
            button = tk.Button(
                sidebar, text=title, command=lambda page=name: self.show(page), anchor="w",
                bg=NAV, fg=WHITE, activebackground=NAV_ACTIVE, activeforeground=WHITE,
                font=(FONT, 11, "bold"), relief="flat", bd=0, padx=15, pady=11, cursor="hand2",
            )
            button.pack(fill="x", padx=12, pady=3)
            self.nav[name] = button
        label(sidebar, "Windows 桌面版", color="#B5C8DD", background=NAV).pack(
            side="bottom", fill="x", padx=22, pady=23
        )

        workspace = tk.Frame(root, bg=BACKGROUND)
        workspace.pack(side="left", fill="both", expand=True, padx=25, pady=21)
        workspace.grid_rowconfigure(0, weight=1)
        workspace.grid_columnconfigure(0, weight=1)
        self.pages = {
            "tasks": self.make_tasks(workspace),
            "settings": self.make_settings(workspace),
        }
        for page in self.pages.values():
            page.grid(row=0, column=0, sticky="nsew")
        self.show("tasks")
        self.load_files()
        root.after(70, self.drain_events)

    def show(self, page):
        self.pages[page].tkraise()
        for name, button in self.nav.items():
            button.configure(bg=NAV_ACTIVE if name == page else NAV)

    def card(self, parent):
        return tk.Frame(parent, bg=WHITE, highlightbackground=BORDER, highlightthickness=1)

    def text_box(self, parent, *, height, bg, fg):
        frame = tk.Frame(parent, bg=bg)
        scrollbar = ttk.Scrollbar(frame, orient="vertical")
        box = tk.Text(
            frame, height=height, bg=bg, fg=fg, insertbackground=fg, wrap="word",
            yscrollcommand=scrollbar.set, relief="flat", padx=11, pady=8,
            font=(FONT, 11), undo=bg == BACKGROUND, highlightthickness=0,
        )
        scrollbar.configure(command=box.yview)
        scrollbar.pack(side="right", fill="y")
        box.pack(side="left", fill="both", expand=True)
        return frame, box

    def make_tasks(self, workspace):
        page = tk.Frame(workspace, bg=BACKGROUND)
        label(page, "下载任务", size=23, background=BACKGROUND, bold=True).pack(fill="x")
        label(page, "输入歌曲名或搜索词，每行一条。", color=MUTED, background=BACKGROUND).pack(
            fill="x", pady=(2, 13)
        )

        keywords = self.card(page)
        keywords.pack(fill="x", pady=(0, 12))
        label(keywords, "关键词", size=12, bold=True).pack(fill="x", padx=15, pady=(9, 2))
        editor, self.editor = self.text_box(keywords, height=5, bg=BACKGROUND, fg=INK)
        editor.pack(fill="x", padx=15, pady=(3, 8))
        controls = tk.Frame(keywords, bg=WHITE)
        controls.pack(fill="x", padx=15, pady=(0, 11))
        self.start_button = ttk.Button(controls, text="开始下载", style="Action.TButton", command=self.start)
        self.start_button.pack(side="left")
        self.save_button = ttk.Button(controls, text="保存关键词", style="Outline.TButton", command=self.save_keywords)
        self.save_button.pack(side="left", padx=7)
        ttk.Button(controls, text="打开保存目录", style="Outline.TButton", command=self.open_output).pack(side="right")

        logs = self.card(page)
        logs.pack(fill="both", expand=True)
        toolbar = tk.Frame(logs, bg=WHITE)
        toolbar.pack(fill="x", padx=15, pady=(8, 3))
        label(toolbar, "运行日志", size=12, bold=True).pack(side="left")
        tk.Label(toolbar, textvariable=self.status, bg="#E5F4F1", fg=ACCENT,
                 font=(FONT, 10, "bold"), padx=9, pady=3).pack(side="right")
        output, self.log = self.text_box(logs, height=6, bg=NAV, fg="#E2EDF8")
        output.pack(fill="both", expand=True, padx=15, pady=(5, 5))
        self.log.configure(state="disabled")
        tk.Label(logs, textvariable=self.progress, anchor="w", bg=WHITE, fg=MUTED,
                 font=(FONT, 10)).pack(fill="x", padx=15, pady=(0, 6))
        return page

    def make_settings(self, workspace):
        page = tk.Frame(workspace, bg=BACKGROUND)
        label(page, "设置", size=23, background=BACKGROUND, bold=True).pack(fill="x")
        label(page, "凭据保存在程序旁边的 secrets.txt，同名环境变量优先。", color=MUTED,
              background=BACKGROUND).pack(fill="x", pady=(2, 13))
        panel = self.card(page)
        panel.pack(fill="x")
        body = tk.Frame(panel, bg=WHITE)
        body.pack(fill="x", padx=20, pady=19)
        self.api_key = tk.StringVar()
        self.cookie = tk.StringVar()
        self.visible = tk.BooleanVar()
        self.fields = []
        for title, hint, variable in (
            ("DeepSeek API Key", "用于让 DeepSeek 从搜索结果中选择音源。", self.api_key),
            ("B 站 Cookie（可选）", "需要使用登录会话时，粘贴完整 Cookie，保持单行。", self.cookie),
        ):
            label(body, title, size=12, bold=True).pack(fill="x")
            label(body, hint, color=MUTED).pack(fill="x", pady=(3, 6))
            field = ttk.Entry(body, textvariable=variable, show="*", style="Settings.TEntry", font=(FONT, 11))
            field.pack(fill="x", pady=(0, 16))
            self.fields.append(field)

        buttons = tk.Frame(body, bg=WHITE)
        buttons.pack(fill="x")
        self.save_settings_button = ttk.Button(
            buttons, text="保存设置", style="Action.TButton", command=self.save_settings
        )
        self.save_settings_button.pack(side="left")
        ttk.Checkbutton(buttons, text="显示凭据", variable=self.visible, command=self.toggle_visibility,
                        style="Settings.TCheckbutton").pack(side="left", padx=13)
        self.settings_status = tk.StringVar()
        tk.Label(body, textvariable=self.settings_status, bg=WHITE, fg=ACCENT, anchor="w", font=(FONT, 10)).pack(
            fill="x", pady=(12, 0)
        )
        return page

    def load_files(self):
        try:
            if KEYWORD_FILE.is_file():
                self.editor.insert("1.0", KEYWORD_FILE.read_text(encoding="utf-8-sig"))
            config = read_local_config()
            self.api_key.set(config.get("DEEPSEEK_API_KEY", ""))
            self.cookie.set(config.get("BILIBILI_COOKIE", ""))
        except (OSError, UnicodeError):
            self.append_log("无法读取本地配置或关键词文件，请检查文件权限和 UTF-8 编码。\n")

    def toggle_visibility(self):
        for field in self.fields:
            field.configure(show="" if self.visible.get() else "*")

    def save_settings(self):
        try:
            save_credentials(self.api_key.get(), self.cookie.get())
        except ValueError:
            messagebox.showerror("设置未保存", "每项凭据必须是单行文本。", parent=self.root)
            return
        except (OSError, UnicodeError):
            messagebox.showerror("设置未保存", "无法写入配置。请检查程序所在目录的读写权限。", parent=self.root)
            return
        self.settings_status.set("已保存到本机。")
        self.visible.set(False)
        self.toggle_visibility()

    def save_keywords(self, *, announce=True):
        text = self.editor.get("1.0", "end-1c")
        try:
            write_local_text(KEYWORD_FILE, text.rstrip() + "\n" if text.strip() else "")
        except OSError:
            messagebox.showerror("关键词未保存", "无法写入 keywords.txt，请检查目录权限。", parent=self.root)
            return None
        if announce:
            self.append_log("已保存 keywords.txt。\n")
        return [line.strip() for line in text.splitlines() if line.strip()]

    def open_output(self):
        try:
            os.startfile(APP_DIR)
        except OSError:
            messagebox.showerror("无法打开目录", str(APP_DIR), parent=self.root)

    def start(self):
        if self.running:
            return
        keywords = self.save_keywords(announce=False)
        if keywords is None:
            return
        if not keywords:
            messagebox.showinfo("需要关键词", "请至少输入一条关键词。", parent=self.root)
            return
        try:
            api_key = get_config("DEEPSEEK_API_KEY")
            cookie = get_config("BILIBILI_COOKIE")
        except (OSError, UnicodeError):
            messagebox.showerror("无法读取配置", "请检查 secrets.txt 的读取权限和 UTF-8 编码。", parent=self.root)
            return
        if not api_key:
            messagebox.showinfo("需要 API Key", "请在设置中填写并保存 DeepSeek API Key。", parent=self.root)
            self.show("settings")
            return
        if not ffmpeg_command():
            messagebox.showinfo("缺少 FFmpeg", "请将 ffmpeg.exe 放在程序旁边，或将 FFmpeg 加入 PATH。", parent=self.root)
            return

        self.set_running(True)
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self.append_log(f"保存目录：{APP_DIR}\n")
        Thread(target=self.run_task, args=(keywords, api_key, cookie), daemon=True).start()

    def run_task(self, keywords, api_key, cookie):
        cookie_values = [part.partition("=")[2].strip() for part in cookie.split(";")]
        stream = TaskOutput(self.events, (api_key, cookie, *(v for v in cookie_values if len(v) >= 8)))
        try:
            with redirect_stdout(stream), redirect_stderr(stream):
                result = run_keywords(keywords, api_key, APP_DIR)
            self.events.put(("complete", result))
        except Exception as error:
            self.events.put(("error", f"任务异常结束（{type(error).__name__}）。"))

    def set_running(self, running):
        self.running = running
        state = "disabled" if running else "normal"
        for button in (self.start_button, self.save_button, self.save_settings_button):
            button.configure(state=state)
        self.editor.configure(state=state)
        if running:
            self.status.set("运行中")
            self.progress.set("正在处理关键词…")

    def append_log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text)
        if int(self.log.index("end-1c").split(".")[0]) > 1600:
            self.log.delete("1.0", "201.0")
        self.log.see("end")
        self.log.configure(state="disabled")

    def drain_events(self):
        pending = []
        for _ in range(250):
            try:
                kind, value = self.events.get_nowait()
            except Empty:
                break
            if kind == "log":
                pending.append(value)
                continue
            if pending:
                self.append_log("".join(pending))
                pending.clear()
            if kind == "progress":
                self.progress.set(value)
            else:
                self.set_running(False)
                if kind == "complete":
                    success, failed = value
                    self.status.set(f"成功 {success} · 失败 {failed}")
                    self.progress.set("点击「打开保存目录」查看音频。" if success else "请查看上方日志中的失败原因。")
                else:
                    self.status.set("任务失败")
                    self.append_log(value + "\n")
                    self.progress.set("任务已停止，可以重新开始。")
        if pending:
            self.append_log("".join(pending))
        self.root.after(70, self.drain_events)

    def close(self):
        if self.running:
            messagebox.showinfo("任务正在运行", "请等待本轮任务结束后关闭窗口。", parent=self.root)
            return
        self.root.destroy()


def main():
    root = tk.Tk()
    MusicCrawlerWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
