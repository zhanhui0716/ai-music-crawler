from openai import OpenAI


def ask_ai_to_choose(video_list, keyword, api_key):
    """
    核心：请AI分析视频列表并做出选择。
    :param video_list: 视频信息列表
    :param keyword: 当前搜索关键词，用于丰富提示词
    :return: AI选择的序号 (整数)
    """
    if not video_list:
        print("  视频列表为空，无法请求AI选择。")
        return 1  # 默认退回第一个

    # 1. 构建给AI看的清晰列表
    choices_text = ""
    for v in video_list:
        choices_text += f"【{v['index']}】{v['title']}\n"
        choices_text += f"    作者：{v['author']} | 时长：{v['duration']} | 日期：{v['date']}\n\n"

    # 2. 设计提示词
    prompt = f"""
    你是一个专业的音乐音频质量分析助手。请根据用户的需求，严格遵循以下规则从B站视频列表中为歌曲选择最佳音质的音频下载源。

    **搜索关键词**："{keyword}"

    **候选视频列表**：
    {choices_text}

    **你的核心任务**：
    1.  **理解歌曲**：首先理解用户通过“{keyword}”想搜索的正确歌曲是什么。
    2.  **筛选时长**：根据你对这首歌正常时长的了解（例如，歌曲通常在3-5分钟），**严格避免选择**时长异常的视频（如循环播放好几倍的“1小时单曲循环”版本）。请通过“时长”字段判断。
    3.  **排除 MV**：严格避免选择标题或描述中包含“MV”、“音乐视频”、“官方MV”、“官方版 MV”、“Live MV”等明显表示是音乐视频的条目。优先选择标题中包含“音频版”、“纯音频”、“录音棚版”、“Hi-Res 音频”等暗示纯音频的条目。如果所有视频都可能是 MV，则选择最可能接近纯音频的那个（例如标题不含“MV”但时长合理的普通视频）。
    4.  **音质优先**：在时长合理且非 MV 的基础上，按照以下标签的优先级选择条目（优先级递减）：
        a. 同时包含“百万录音棚”和“Hi-res无损音质”
        b. 包含“百万录音棚”或“百万豪装录音棚”
        c. 包含“Hi-res”或“Hi-res无损音质”
        d. 包含“日推歌单”
        e. 以上标签均无的普通视频
    5.  **综合决策**：如果多个视频符合相同音质等级，再参考发布时间（选更新的）、作者权威性等通用规则。

    **你的输出格式**：
    思考完成后，只输出最终选择的**数字序号**（例如：3），不要输出任何其他解释、标点或文字。
    如果列表为空或你完全无法判断，请输出“1”。
    """

    # 3. 调用DeepSeek API
    try:
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com", timeout=30.0)
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=10,
            stream=False
        )
        ai_answer = response.choices[0].message.content.strip()
        print(f"  AI原始回复: 「{ai_answer}」")

        # 4. 从AI回复中提取数字
        import re
        match = re.search(r'(\d+)', ai_answer)
        if match:
            choice = int(match.group(1))
            if 1 <= choice <= len(video_list):
                return choice
            else:
                print(f"  AI选择 {choice} 超出范围，将使用第一个。")
                return 1
        else:
            print(f"  无法从AI回复中解析数字，将使用第一个。")
            return 1

    except Exception as e:
        print(f"  DeepSeek API 调用失败 ({type(e).__name__})，将使用第一条候选。")
        return 1
