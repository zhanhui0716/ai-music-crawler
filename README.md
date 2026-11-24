# AI Music Crawler

按关键词搜索 B 站视频，由 DeepSeek 选择候选，并使用 FFmpeg 封装音频。

1. 将 FFmpeg 加入 PATH，然后执行 `python -m pip install -r requirements.txt`。
2. 在项目根目录复制 `secrets.example.txt` 为 `secrets.txt`，填入 `DEEPSEEK_API_KEY`。需要使用登录会话时，在 `BILIBILI_COOKIE` 中填入完整的 Cookie，保持单行。同名非空环境变量优先。
3. 编辑 `keywords.txt`，每行一个关键词。从项目根目录执行 `python main_controller_ai_choice.py`。

`secrets.txt` 是本地明文配置，已被 Git 忽略。提交示例文件时请保持凭据字段为空。
