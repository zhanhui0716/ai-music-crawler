import argparse
from pathlib import Path
import time

import bilibili_audio_module_ai as audio_module
from ai_selector import ask_ai_to_choose_batch
from local_config import APP_DIR, get_config


KEYWORD_FILE = APP_DIR / "keywords.txt"
LOG_FILE = APP_DIR / "ai_download_log.txt"


def main():
    """主控制器流程"""
    parser = argparse.ArgumentParser(
        prog="AI Music Crawler",
        description="Search Bilibili and save audio selected by DeepSeek."
    )
    parser.add_argument(
        "--keywords",
        type=Path,
        default=KEYWORD_FILE,
        help="UTF-8 keyword file (default: keywords.txt beside the app)",
    )
    args = parser.parse_args()
    api_key = get_config("DEEPSEEK_API_KEY")

    # 0. 检查配置
    if not api_key:
        print("错误：未设置 DeepSeek API 密钥。")
        print("请在 secrets.txt 或环境变量中设置 DEEPSEEK_API_KEY。")
        return

    # 1. 读取关键词文件
    if not args.keywords.is_file():
        print(f"错误：找不到关键词文件 {args.keywords}")
        print(f"请创建此文件，每行写入一个搜索关键词。")
        return

    with args.keywords.open(encoding='utf-8-sig') as f:
        all_keywords = [line.strip() for line in f if line.strip()]

    if not all_keywords:
        print("关键词文件为空，程序结束。")
        return

    if not audio_module.ffmpeg_command():
        print("缺少 FFmpeg。请将它加入 PATH，或将 ffmpeg.exe 放在程序旁边。")
        return

    run_keywords(all_keywords, api_key)


def run_keywords(all_keywords, api_key, output_dir=audio_module.AUDIO_DIR):
    total = len(all_keywords)
    tasks = {}
    search_errors = {}
    print(f"[1/3] 搜索 {total} 个关键词")
    for task_id, keyword in enumerate(all_keywords, 1):
        print(f"\n[{task_id}/{total}] {keyword}")
        try:
            task = audio_module.search_and_list_videos(keyword)
            if task["videos"]:
                tasks[task_id] = task
            else:
                search_errors[task_id] = "未匹配到视频"
        except audio_module.SearchError as error:
            search_errors[task_id] = str(error)
        except Exception as error:
            search_errors[task_id] = f"搜索异常 ({type(error).__name__})"
        if task_id in search_errors:
            print(f"  [!] {search_errors[task_id]}")
        if task_id < total:
            time.sleep(2)

    choices = {}
    if tasks:
        print(f"\n[2/3] 一次提交 {len(tasks)} 首的候选给 DeepSeek")
        choices = ask_ai_to_choose_batch(tasks, api_key)
        print("\n[3/3] 按关键词顺序下载")
    else:
        print("\n没有可用候选，跳过 AI 选源和下载。")

    success_count = 0
    failed_keywords = []
    with LOG_FILE.open("a", encoding="utf-8", buffering=1) as log:
        for task_id, keyword in enumerate(all_keywords, 1):
            success = False
            ai_choice = choices.get(task_id)
            reason = search_errors.get(task_id, "")
            if task_id in tasks:
                print(f"\n[{task_id}/{total}] {keyword}")
                try:
                    success = audio_module.download_selected_audio(
                        tasks[task_id], ai_choice or 1, output_dir
                    )["success"]
                    if not success:
                        reason = "下载或封装失败"
                except Exception as error:
                    reason = f"下载异常 ({type(error).__name__})"
                if reason:
                    print(f"  [!] {reason}")

            if success:
                success_count += 1
            else:
                failed_keywords.append(keyword)
            choice_label = ai_choice if ai_choice is not None else "-"
            fallback = " | 回退候选: 1" if task_id in tasks and ai_choice is None else ""
            entry = f"成功: {success} | {time.ctime()} | 关键词: {keyword} | AI选择: {choice_label}{fallback}"
            log.write(f"{entry} | 原因: {reason}\n" if reason else entry + "\n")

    fail_count = len(failed_keywords)
    # 最终总结
    print(f"\n[Done] 处理完成！总计 {len(all_keywords)} 个关键词，成功 {success_count} 个，失败 {fail_count} 个。")
    if failed_keywords:
        print("失败的关键词列表：")
        for kw in failed_keywords:
            print(f"  - {kw}")
    if success_count:
        print(f"Audio: {output_dir}")
    print(f"日志：{LOG_FILE}")
    return success_count, fail_count

if __name__ == "__main__":
    main()
