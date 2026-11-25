from contextlib import redirect_stderr, redirect_stdout
import ctypes
import os
from pathlib import Path
from queue import Empty, SimpleQueue
from threading import Thread
from time import monotonic
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk

from bilibili_audio_module_ai import ffmpeg_command
from local_config import APP_DIR, get_config, read_local_config, save_credentials, write_local_text
from main_controller_ai_choice import KEYWORD_FILE, run_keywords


BACKGROUND = "#111722"
SIDEBAR = "#0B101A"
WHITE = "#182231"
INK = "#ECF2FA"
MUTED = "#A9B8CA"
BORDER = "#2A394B"
LOG_BACKGROUND = "#0E1722"
SELECTED = "#203747"
EDITOR_BACKGROUND = "#111B28"
ACCENT = "#80EDC7"
FONT = "Microsoft YaHei UI"
DEFAULT_OUTPUT_DIR = APP_DIR / "下载的音频"


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
        self.output_dir = DEFAULT_OUTPUT_DIR
        self.status = tk.StringVar(value="就绪")
        self.progress = tk.StringVar(value="")
        root.title("AI Music Crawler")
        scale = float(root.tk.call("tk", "scaling")) * 72 / 96
        screen_width, screen_height = root.winfo_screenwidth(), root.winfo_screenheight()
        width = min(round(1080 * scale), round(screen_width * 0.92))
        height = min(round(760 * scale), round(screen_height * 0.87))
        root.geometry(f"{width}x{height}+{(screen_width - width) // 2}+{(screen_height - height) // 2}")
        root.minsize(min(width, round(690 * scale)), min(height, round(510 * scale)))
        root.configure(bg=BACKGROUND)
        root.update_idletasks()
        if os.name == "nt":
            hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
            dark = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark), ctypes.sizeof(dark))
        icon_dir = Path(__file__).resolve().parent
        icon = icon_dir / "assets" / "app.ico"
        if icon.is_file():
            root.iconbitmap(str(icon))
        root.protocol("WM_DELETE_WINDOW", self.close)

        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("Action.TButton", font=(FONT, 10, "bold"), padding=(17, 9),
                        background=ACCENT, foreground="#102B25", borderwidth=0)
        style.map("Action.TButton", background=[("disabled", "#384C51"), ("active", "#A5F5DA")],
                  foreground=[("disabled", "#B7C7CD")])
        style.configure("Outline.TButton", font=(FONT, 10), padding=(13, 7),
                        background="#26374A", foreground=INK, borderwidth=0)
        style.map("Outline.TButton", background=[("active", "#31485E")])
        style.configure("Settings.TEntry", padding=10, foreground=INK, fieldbackground=EDITOR_BACKGROUND,
                        bordercolor=BORDER, lightcolor=EDITOR_BACKGROUND, darkcolor=EDITOR_BACKGROUND)
        style.map("Settings.TEntry", bordercolor=[("focus", ACCENT)],
                  fieldbackground=[("readonly", EDITOR_BACKGROUND)])
        style.configure("App.Vertical.TScrollbar", background="#40576B", troughcolor=EDITOR_BACKGROUND,
                        bordercolor=EDITOR_BACKGROUND, lightcolor="#40576B", darkcolor="#40576B", arrowsize=10)
        style.map("App.Vertical.TScrollbar", background=[("active", "#5C7890")])
        style.configure("Settings.TCheckbutton", background=WHITE, foreground=INK, font=(FONT, 10))
        style.map("Settings.TCheckbutton", background=[("active", WHITE)], foreground=[("active", ACCENT)])

        sidebar = tk.Frame(root, bg=SIDEBAR, width=round(174 * scale))
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        brand = tk.Frame(sidebar, bg=SIDEBAR)
        brand.pack(fill="x", padx=15, pady=(24, 28))
        if icon.is_file():
            try:
                self.brand_icon = tk.PhotoImage(file=str(icon.with_name("app.png"))).subsample(7, 7)
                tk.Label(brand, image=self.brand_icon, bg=SIDEBAR, borderwidth=0).pack(side="left", padx=(0, 8))
            except tk.TclError:
                pass
        label(brand, "AI Music\nCrawler", size=11, background=SIDEBAR, bold=True).pack(side="left")

        self.nav = {}
        for name, title in (("tasks", "下载任务"), ("settings", "设置")):
            button = tk.Button(
                sidebar, text=title, command=lambda page=name: self.show(page), anchor="w",
                bg=SIDEBAR, fg=MUTED, activebackground=SELECTED, activeforeground=ACCENT,
                font=(FONT, 10, "bold"), relief="flat", bd=0, padx=14, pady=11, cursor="hand2",
            )
            button.pack(fill="x", padx=11, pady=(0, 5))
            self.nav[name] = button

        ttk.Button(sidebar, text="打开保存目录", style="Outline.TButton", command=self.open_output).pack(
            side="bottom", fill="x", padx=12, pady=18
        )

        workspace = tk.Frame(root, bg=BACKGROUND)
        workspace.pack(side="left", fill="both", expand=True, padx=round(20 * scale), pady=round(18 * scale))
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
            button.configure(bg=SELECTED if name == page else SIDEBAR, fg=ACCENT if name == page else MUTED)

    def card(self, parent):
        return tk.Frame(parent, bg=WHITE, highlightbackground=BORDER, highlightthickness=1)

    def text_box(self, parent, *, height, bg, fg):
        frame = tk.Frame(parent, bg=bg, highlightbackground=BORDER, highlightthickness=1)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", style="App.Vertical.TScrollbar")
        box = tk.Text(
            frame, height=height, bg=bg, fg=fg, insertbackground=fg, wrap="word",
            yscrollcommand=scrollbar.set, relief="flat", padx=11, pady=8,
            font=(FONT, 11), undo=bg == EDITOR_BACKGROUND, highlightthickness=0,
            spacing1=2, spacing3=3, selectbackground="#34586D", selectforeground=INK,
        )
        scrollbar.configure(command=box.yview)
        scrollbar.pack(side="right", fill="y")
        box.pack(side="left", fill="both", expand=True)
        return frame, box

    def make_tasks(self, workspace):
        page = tk.Frame(workspace, bg=BACKGROUND)
        heading = tk.Frame(page, bg=BACKGROUND)
        heading.pack(fill="x", pady=(1, 16))
        label(heading, "下载任务", size=20, background=BACKGROUND, bold=True).pack(side="left")
        tk.Label(heading, textvariable=self.status, bg=SELECTED, fg=ACCENT,
                 font=(FONT, 10, "bold"), padx=12, pady=5).pack(side="right")

        panels = tk.Frame(page, bg=BACKGROUND)
        panels.pack(fill="both", expand=True)
        panels.grid_rowconfigure(0, weight=1)
        panels.grid_columnconfigure(0, weight=2, uniform="task")
        panels.grid_columnconfigure(1, weight=3, uniform="task")

        keywords = self.card(panels)
        keywords.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        label(keywords, "关键词", size=13, bold=True).pack(fill="x", padx=14, pady=(13, 2))
        label(keywords, "每行一个歌名或搜索词", color=MUTED).pack(fill="x", padx=14, pady=(0, 10))
        editor, self.editor = self.text_box(keywords, height=5, bg=EDITOR_BACKGROUND, fg=INK)
        editor.pack(fill="both", expand=True, padx=14, pady=(0, 12))
        self.start_button = ttk.Button(keywords, text="开始下载", style="Action.TButton", command=self.start)
        self.start_button.pack(fill="x", padx=14, pady=(0, 7))
        self.save_button = ttk.Button(keywords, text="保存关键词", style="Outline.TButton", command=self.save_keywords)
        self.save_button.pack(fill="x", padx=14, pady=(0, 14))

        logs = self.card(panels)
        logs.grid(row=0, column=1, sticky="nsew")
        label(logs, "运行日志", size=13, bold=True).pack(fill="x", padx=14, pady=(13, 2))
        tk.Label(logs, textvariable=self.progress, anchor="w", bg=WHITE, fg=MUTED,
                 font=(FONT, 9)).pack(fill="x", padx=14, pady=(0, 10))
        output, self.log = self.text_box(logs, height=5, bg=LOG_BACKGROUND, fg="#D9E7F7")
        output.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        self.log.configure(state="disabled")
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

        label(body, "下载位置", size=12, bold=True).pack(fill="x", pady=(0, 6))
        folder_row = tk.Frame(body, bg=WHITE)
        folder_row.pack(fill="x", pady=(0, 16))
        self.folder_selection = tk.StringVar(value=str(self.output_dir))
        ttk.Entry(folder_row, textvariable=self.folder_selection, style="Settings.TEntry",
                  state="readonly", font=(FONT, 10)).pack(side="left", fill="x", expand=True)
        ttk.Button(folder_row, text="选择文件夹", style="Outline.TButton",
                   command=self.choose_output).pack(side="left", padx=(8, 0))
        ttk.Button(folder_row, text="恢复默认", style="Outline.TButton",
                   command=lambda: self.folder_selection.set(str(DEFAULT_OUTPUT_DIR))).pack(side="left", padx=(8, 0))

        buttons = tk.Frame(body, bg=WHITE)
        buttons.pack(fill="x")
        self.save_settings_button = ttk.Button(
            buttons, text="保存设置", style="Action.TButton", command=self.save_settings
        )
        self.save_settings_button.pack(side="left")
        ttk.Button(
            buttons, text="打开 B 站", style="Outline.TButton", command=self.open_bilibili
        ).pack(side="left", padx=(8, 0))
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
            if configured_dir := config.get("DOWNLOAD_DIR"):
                self.output_dir = APP_DIR / configured_dir
            self.folder_selection.set(str(self.output_dir))
            self.api_key.set(config.get("DEEPSEEK_API_KEY", ""))
            self.cookie.set(config.get("BILIBILI_COOKIE", ""))
        except (OSError, UnicodeError):
            self.append_log("无法读取本地配置或关键词文件，请检查文件权限和 UTF-8 编码。\n")

    def open_bilibili(self):
        url = "https://www.bilibili.com/"
        try:
            opened = webbrowser.open_new_tab(url)
        except (OSError, webbrowser.Error):
            opened = False
        if opened:
            self.settings_status.set("已请求打开 B 站。如需配置 Cookie，请手动填写并保存。")
        else:
            messagebox.showinfo("打开 B 站", f"请在浏览器打开 {url}", parent=self.root)

    def toggle_visibility(self):
        for field in self.fields:
            field.configure(show="" if self.visible.get() else "*")

    def choose_output(self):
        current = Path(self.folder_selection.get())
        selected = filedialog.askdirectory(
            parent=self.root, title="选择下载文件夹",
            initialdir=str(current if current.is_dir() else APP_DIR),
        )
        if selected:
            self.folder_selection.set(str(Path(selected)))

    def save_settings(self):
        selected = Path(self.folder_selection.get())
        try:
            save_credentials(
                self.api_key.get(), self.cookie.get(),
                download_dir="" if selected == DEFAULT_OUTPUT_DIR else str(selected),
            )
        except ValueError:
            messagebox.showerror("设置未保存", "每项凭据必须是单行文本。", parent=self.root)
            return
        except (OSError, UnicodeError):
            messagebox.showerror("设置未保存", "无法写入配置。请检查程序所在目录的读写权限。", parent=self.root)
            return
        self.output_dir = selected
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
            self.output_dir.mkdir(parents=True, exist_ok=True)
            os.startfile(self.output_dir)
        except OSError:
            messagebox.showerror("无法打开目录", str(self.output_dir), parent=self.root)

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

        output_dir = self.output_dir
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            messagebox.showerror(
                "无法创建下载目录", str(output_dir), parent=self.root
            )
            return

        self.set_running(True)
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self.append_log(f"保存目录：{output_dir}\n")
        Thread(target=self.run_task, args=(keywords, api_key, cookie, output_dir), daemon=True).start()

    def run_task(self, keywords, api_key, cookie, output_dir):
        cookie_values = [part.partition("=")[2].strip() for part in cookie.split(";")]
        stream = TaskOutput(self.events, (api_key, cookie, *(v for v in cookie_values if len(v) >= 8)))
        try:
            with redirect_stdout(stream), redirect_stderr(stream):
                result = run_keywords(keywords, api_key, output_dir)
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
    if os.name == "nt":
        ctypes.windll.user32.SetProcessDPIAware()
    root = tk.Tk()
    MusicCrawlerWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
