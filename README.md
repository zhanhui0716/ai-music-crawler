# AI Music Crawler

Windows 桌面工具。输入歌曲名或搜索词，由 DeepSeek 根据 B 站搜索结果选择音源，再用 FFmpeg 封装成音频文件。

## Windows 便携版

1. 解压 `AI-Music-Crawler-Windows-x64.zip` 到有写入权限的目录。
2. 将 `ffmpeg.exe` 放在解压目录，或将 FFmpeg 加入 PATH。便携版已包含 Python 运行时。
3. 双击 `AI-Music-Crawler.exe`。打开左侧 **设置**，填写并保存自己的 DeepSeek API Key。B 站 Cookie 可选，填入时请使用单行的完整值。
4. 回到 **下载任务**，在关键词框里每行输入一条，再点 **开始下载**。界面会保存 `keywords.txt` 并显示运行日志、进度和完成统计。
5. 点击 **打开保存目录** 查看音频。桌面版的 `.m4a` 和日志文件保存在 EXE 旁边。

凭据保存在同目录的本地明文 `secrets.txt`。同名非空环境变量优先。ZIP 内只有空白凭据模板。

## 从源码运行

```powershell
python -m pip install -r requirements.txt
pythonw desktop_app.pyw
```

原命令行入口仍可使用 `python main_controller_ai_choice.py`，其音频输出位于项目根目录下的 `B站下载的音频` 文件夹。

## 构建与发布

使用 Windows x64 Python，安装 `requirements.txt` 中的依赖，再执行以下命令。

```powershell
python -m pip install pyinstaller
python build_windows.py
```

将本地 `dist/AI-Music-Crawler-Windows-x64.zip` 上传到 GitHub Release 的附件区。Git 忽略了凭据、音频、日志和构建输出。
