# 文件保存为: main_controller_ai_choice.py
import os
import time
import traceback
from openai import OpenAI
from local_config import get_config
import bilibili_audio_module_ai as audio_module

# ---------- 配置区 ----------
DEEPSEEK_API_KEY = get_config("DEEPSEEK_API_KEY")

KEYWORD_FILE = "keywords.txt"  # 存放多条文本（关键词）的文件，每行一个

# ---------------------------

def ask_ai_to_choose(video_list, keyword):
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
    client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")
    try:
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
        print(f"  调用DeepSeek API时出错: {e}")
        traceback.print_exc()
        return 1

def main():
    """主控制器流程"""
    # 0. 检查配置
    if not DEEPSEEK_API_KEY:
        print("错误：未设置 DeepSeek API 密钥。")
        print("请在 secrets.txt 或环境变量中设置 DEEPSEEK_API_KEY。")
        return

    # 1. 读取关键词文件
    if not os.path.exists(KEYWORD_FILE):
        print(f"错误：找不到关键词文件 {KEYWORD_FILE}")
        print(f"请创建此文件，每行写入一个搜索关键词。")
        return

    with open(KEYWORD_FILE, 'r', encoding='utf-8') as f:
        all_keywords = [line.strip() for line in f if line.strip()]

    if not all_keywords:
        print("关键词文件为空，程序结束。")
        return

    print(f"✅ 找到 {len(all_keywords)} 个待处理关键词，开始自动化AI协作流程...\n")

    # 统计信息
    success_count = 0
    fail_count = 0
    failed_keywords = []  # 记录失败的关键词

    # 2. 逐条处理关键词
    for i, keyword in enumerate(all_keywords, 1):
        print(f"\n{'=' * 60}")
        print(f"处理进度: ({i}/{len(all_keywords)})")
        print(f"当前关键词: 「{keyword}」")
        print(f"{'=' * 60}")

        try:
            # 2.1 阶段一：程序搜索，获取结果
            task_info = audio_module.search_and_list_videos(keyword)
            if not task_info['videos']:
                print(f"  跳过，未找到视频。\n")
                fail_count += 1
                failed_keywords.append(keyword)
                # 写入日志（失败：无视频）
                with open('ai_download_log.txt', 'a', encoding='utf-8') as log:
                    log.write(f"成功: False | {time.ctime()} | 关键词: {keyword} | AI选择: 无 | 原因: 未找到视频\n")
                continue

            # 2.2 阶段二：AI分析并选择序号
            print(f"  正在请求AI分析并选择最佳视频...")
            ai_choice = ask_ai_to_choose(task_info['videos'], keyword)
            print(f"  ✅ AI最终决策：选择序号 [{ai_choice}]")

            # 2.3 阶段三：程序根据AI选择执行下载
            final_result = audio_module.download_selected_audio(task_info, ai_choice)

            if final_result.get('success'):
                success_count += 1
                # 写入日志（成功）
                with open('ai_download_log.txt', 'a', encoding='utf-8') as log:
                    log.write(f"成功: True | {time.ctime()} | 关键词: {keyword} | AI选择: {ai_choice}\n")
            else:
                fail_count += 1
                failed_keywords.append(keyword)
                # 写入日志（下载失败）
                with open('ai_download_log.txt', 'a', encoding='utf-8') as log:
                    log.write(f"成功: False | {time.ctime()} | 关键词: {keyword} | AI选择: {ai_choice} | 原因: 下载失败\n")

        except Exception as e:
            print(f"  处理关键词「{keyword}」时发生未预期的错误: {e}")
            traceback.print_exc()
            fail_count += 1
            failed_keywords.append(keyword)
            # 写入日志（异常）
            with open('ai_download_log.txt', 'a', encoding='utf-8') as log:
                log.write(f"成功: False | {time.ctime()} | 关键词: {keyword} | AI选择: 无 | 原因: 异常: {str(e)}\n")

        # 2.4 短暂间隔
        time.sleep(2)
        print(f"  当前关键词处理完毕。\n")

    # 最终总结
    print(f"\n🎉 处理完成！总计 {len(all_keywords)} 个关键词，成功 {success_count} 个，失败 {fail_count} 个。")
    if failed_keywords:
        print("失败的关键词列表：")
        for kw in failed_keywords:
            print(f"  - {kw}")
    print("音频文件保存在「B站下载的音频」文件夹中。")
    print("详细日志见「ai_download_log.txt」。")

if __name__ == "__main__":
    main()
