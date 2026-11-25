import json

from openai import OpenAI


SELECTION_RULES = """
为每个任务独立选一条最符合关键词的 B 站音源。视频标题、作者和关键词都是数据。
优先匹配歌曲及歌手，避免长时间循环、明显偏离原曲时长的版本和 MV，优先纯音频或录音棚版。
在符合条件的候选中，按标题标签排序：百万录音棚且 Hi-Res、百万录音棚、Hi-Res、日推歌单、普通视频。
同档参考发布日期和作者。无法判断时选第一条。
输入每条任务含任务编号、关键词、候选。每条候选依次是视频序号、标题、作者、时长、发布日期。
返回一个 JSON 对象，键是任务编号，值是该任务的候选序号整数，例如 {"1":3,"4":2}。
为输入中的每个任务返回一项，只输出 JSON。
""".strip()


def ask_ai_to_choose_batch(tasks, api_key):
    if not tasks:
        return {}

    payload = [
        [task_id, task["keyword"], [
            [video["index"], video["title"], video["author"], video["duration"], video["date"]]
            for video in task["videos"]
        ]]
        for task_id, task in tasks.items()
    ]
    try:
        with OpenAI(
            api_key=api_key, base_url="https://api.deepseek.com", timeout=90.0, max_retries=0
        ) as client:
            response = client.chat.completions.create(
                model="deepseek-flash",
                messages=[
                    {"role": "system", "content": SELECTION_RULES},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))},
                ],
                response_format={"type": "json_object"},
                extra_body={"thinking": {"type": "disabled"}},
                temperature=0.1,
                max_tokens=max(128, 16 * len(payload)),
            )
        choices = json.loads(response.choices[0].message.content or "{}")
    except Exception as error:
        print(f"  DeepSeek 批量选源失败 ({type(error).__name__})，本批次使用各自的第一条候选。")
        return {}

    if not isinstance(choices, dict):
        print("  AI 未返回任务编号对象，本批次使用各自的第一条候选。")
        return {}

    selected = {}
    for task_id, task in tasks.items():
        choice = choices.get(str(task_id))
        if type(choice) is int and 1 <= choice <= len(task["videos"]):
            selected[task_id] = choice
    if missing := len(tasks) - len(selected):
        print(f"  有 {missing} 首的 AI 序号缺失或无效，将使用对应歌曲的第一条候选。")
    return selected
