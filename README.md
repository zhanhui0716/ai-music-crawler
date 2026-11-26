# AI Music Crawler

Windows 桌面工具。输入歌名或搜索词，程序用本地规则选择 B 站音源，再用 FFmpeg 封装音频。无需 API Key。

## Windows 便携版

1. 解压 `AI-Music-Crawler-Windows-x64.zip` 到有写入权限的目录。
2. 将 `ffmpeg.exe` 放在解压目录，或将 FFmpeg 加入 PATH。便携版已包含 Python 运行时。
3. 双击 `AI-Music-Crawler.exe`。如需使用 B 站登录会话，可在 **设置** 中填写单行 Cookie。
4. 回到 **下载任务**，在关键词框里每行输入一条，再点 **开始下载**。界面会显示运行日志、进度和完成统计。默认并行处理 3 首，可在设置中调整为 1–10 首。每首选源后即可开始下载。
5. 音频默认保存在 EXE 同目录的「下载的音频」文件夹，可在 **设置** 中更改。点击 **打开保存目录** 查看音频。日志文件保存在 EXE 旁边。

程序优先选择页面返回的 FLAC 无损音轨，其次是杜比，再在普通 DASH 中按带宽从高到低尝试。下载或封装失败时会尝试备用地址与其余音轨。全程直接复制音频编码流，无需重新编码。

对于已下载且有记录的同名文件，如果音轨、格式和文件大小均匹配，程序会跳过重复下载。下载记录保存在音频目录的 `.music-crawler-cache` 子目录。

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
