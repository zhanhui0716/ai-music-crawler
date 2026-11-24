import argparse
from pathlib import Path
import time
import traceback

import bilibili_audio_module_ai as audio_module
from ai_selector import ask_ai_to_choose
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
    print(f"[OK] 找到 {len(all_keywords)} 个待处理关键词，开始自动化AI协作流程...\n")

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
                with LOG_FILE.open('a', encoding='utf-8') as log:
                    log.write(f"成功: False | {time.ctime()} | 关键词: {keyword} | AI选择: 无 | 原因: 未找到视频\n")
                continue

            # 2.2 阶段二：AI分析并选择序号
            print(f"  正在请求AI分析并选择最佳视频...")
            ai_choice = ask_ai_to_choose(task_info['videos'], keyword, api_key)
            print(f"  [OK] AI最终决策：选择序号 [{ai_choice}]")

            # 2.3 阶段三：程序根据AI选择执行下载
            final_result = audio_module.download_selected_audio(task_info, ai_choice, output_dir)

            if final_result.get('success'):
                success_count += 1
                # 写入日志（成功）
                with LOG_FILE.open('a', encoding='utf-8') as log:
                    log.write(f"成功: True | {time.ctime()} | 关键词: {keyword} | AI选择: {ai_choice}\n")
            else:
                fail_count += 1
                failed_keywords.append(keyword)
                # 写入日志（下载失败）
                with LOG_FILE.open('a', encoding='utf-8') as log:
                    log.write(f"成功: False | {time.ctime()} | 关键词: {keyword} | AI选择: {ai_choice} | 原因: 下载失败\n")

        except Exception as e:
            print(f"  处理关键词「{keyword}」时发生未预期的错误: {e}")
            traceback.print_exc()
            fail_count += 1
            failed_keywords.append(keyword)
            # 写入日志（异常）
            with LOG_FILE.open('a', encoding='utf-8') as log:
                log.write(f"成功: False | {time.ctime()} | 关键词: {keyword} | AI选择: 无 | 原因: 异常: {str(e)}\n")

        # 2.4 短暂间隔
        time.sleep(2)
        print(f"  当前关键词处理完毕。\n")

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
