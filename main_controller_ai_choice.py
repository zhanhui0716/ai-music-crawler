import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path
from threading import Lock

import bilibili_audio_module_ai as audio_module
from candidate_selector import choose_candidate
from local_config import APP_DIR, DEFAULT_PARALLEL_JOBS, parse_parallel_jobs, read_local_config


KEYWORD_FILE = APP_DIR / "keywords.txt"
LOG_FILE = APP_DIR / "ai_download_log.txt"
LOG_KEYWORD = ContextVar("log_keyword", default="")


def main():
    """主控制器流程"""
    parser = argparse.ArgumentParser(
        prog="AI Music Crawler",
        description="Search Bilibili and save audio using local selection rules."
    )
    parser.add_argument(
        "--keywords",
        type=Path,
        default=KEYWORD_FILE,
        help="UTF-8 keyword file (default: keywords.txt beside the app)",
    )
    args = parser.parse_args()
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

    run_keywords(all_keywords, parallel_jobs=parse_parallel_jobs(read_local_config().get("PARALLEL_JOBS")))


def process_keyword(task_id, total, keyword, output_dir, output_lock):
    token = LOG_KEYWORD.set(keyword)
    try:
        print(f"[{task_id}/{total}] 开始处理")
        return search_and_download(keyword, output_dir, output_lock)
    finally:
        LOG_KEYWORD.reset(token)


def search_and_download(keyword, output_dir, output_lock):
    try:
        task = audio_module.search_and_list_videos(keyword)
        if not task["videos"]:
            return "failed", None, "未匹配到视频"
        selection = choose_candidate(task["videos"], keyword)
    except audio_module.SearchError as error:
        return "failed", None, str(error)
    except Exception as error:
        return "failed", None, f"搜索或选源异常 ({type(error).__name__})"

    try:
        with output_lock:
            result = audio_module.download_selected_audio(task, selection, output_dir)
        if result.get("skipped"):
            return "skipped", selection, ""
        if result["success"]:
            return "downloaded", selection, ""
        return "failed", selection, "下载或封装失败"
    except Exception as error:
        return "failed", selection, f"下载异常 ({type(error).__name__})"


def run_keywords(all_keywords, output_dir=audio_module.AUDIO_DIR, *, parallel_jobs=DEFAULT_PARALLEL_JOBS, on_result=None):
    total = len(all_keywords)
    if not total:
        return 0, 0
    workers = min(total, parse_parallel_jobs(parallel_jobs))
    print(f"共 {total} 首，同时处理最多 {workers} 首。每首选源后立即检查并下载。")
    output_locks = {}
    downloaded = skipped = 0
    failures = {}
    with LOG_FILE.open("a", encoding="utf-8", buffering=1) as log:
        log.write(f"\n[{datetime.now():%Y-%m-%d %H:%M:%S}] 开始批次 | 任务 {total} | 并发 {workers}\n")
        with ThreadPoolExecutor(max_workers=workers) as executor:
            pending = {}
            for task_id, keyword in enumerate(all_keywords, 1):
                output_name = audio_module.sanitize_filename(keyword).casefold()
                if output_name not in output_locks:
                    output_locks[output_name] = Lock()
                future = executor.submit(
                    process_keyword, task_id, total, keyword, output_dir, output_locks[output_name]
                )
                pending[future] = (task_id, keyword)

            for future in as_completed(pending):
                task_id, keyword = pending[future]
                outcome, selection, reason = future.result()
                if outcome == "downloaded":
                    downloaded += 1
                elif outcome == "skipped":
                    skipped += 1
                else:
                    failures[task_id] = keyword

                state = {"downloaded": "已下载", "skipped": "已跳过", "failed": "失败"}[outcome]
                context = LOG_KEYWORD.set(keyword)
                try:
                    print(f"[{state}]" + (f" {reason}" if reason else ""))
                finally:
                    LOG_KEYWORD.reset(context)
                choice_label = selection if selection is not None else "-"
                entry = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {state} | 关键词: {keyword} | 本地选源: {choice_label}"
                log.write(f"{entry} | 原因: {reason}\n" if reason else entry + "\n")
                if on_result is not None:
                    on_result(downloaded, skipped, len(failures), total)

        log.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] 批次结束 | 下载 {downloaded} | 跳过 {skipped} | 失败 {len(failures)}\n")

    failed_keywords = [failures[task_id] for task_id in sorted(failures)]
    fail_count = len(failed_keywords)
    success_count = downloaded + skipped
    print(f"\n[Done] 处理完成！总计 {len(all_keywords)} 个关键词，下载 {downloaded} 个，跳过 {skipped} 个，失败 {fail_count} 个。")
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
