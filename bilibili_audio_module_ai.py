# 文件保存为: bilibili_audio_module_ai.py
import json
import re
import shutil
import subprocess
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, urljoin, urlsplit

import requests
from bs4 import BeautifulSoup
from local_config import APP_DIR, get_config, write_local_text


AUDIO_DIR = APP_DIR / "B站下载的音频"


def ffmpeg_command():
    local_ffmpeg = APP_DIR / "ffmpeg.exe"
    if local_ffmpeg.is_file():
        return str(local_ffmpeg)
    return shutil.which("ffmpeg")


def sanitize_filename(name):
    safe_name = re.sub(r'[\\/*?:"<>|\x00-\x1f]', "", name).strip().rstrip(".")[:120].rstrip(". ") or "audio"
    if safe_name.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
        safe_name = "_" + safe_name
    return safe_name


# 带重试的流式下载
def download_large_file(url, filepath, headers, max_retry=3):
    for attempt in range(max_retry):
        try:
            with requests.get(url, headers=headers, stream=True, timeout=(10, 30)) as r:
                r.raise_for_status()
                total_size = int(r.headers.get('content-length', 0))
                downloaded = 0
                last_update = 0

                with open(filepath, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=65536):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            now = time.monotonic()
                            if total_size > 0 and (now - last_update >= 0.25 or downloaded == total_size):
                                last_update = now
                                percent = downloaded / total_size * 100
                                print(f"\r下载中: {percent:.1f}%", end='', flush=True)
                print()
                if not downloaded:
                    raise requests.RequestException("Empty media response")
            return True
        except requests.RequestException as error:
            print(f"\n下载失败 ({attempt + 1}/{max_retry}): {type(error).__name__}")
            if attempt + 1 < max_retry:
                time.sleep(2)
    return False


class SearchError(RuntimeError):
    pass


def search_bilibili_videos(keyword, max_results=10):
    """根据关键词搜索B站视频，返回前max_results个视频信息"""
    try:
        url = 'https://search.bilibili.com/all'
        headers = {
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 Edg/132.0.0.0',
            'referer': 'https://www.bilibili.com/',
        }
        cookie = get_config("BILIBILI_COOKIE")
        if cookie:
            headers["Cookie"] = cookie
        res = requests.get(url, params={"keyword": keyword}, headers=headers, timeout=10)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, 'lxml')
        video_cards = soup.find_all('div', class_='bili-video-card')
        results = []
        count = 0
        for card in video_cards:
            if count >= max_results:
                break
            # 标题
            title_tag = card.find('h3', class_='bili-video-card__info--tit')
            if title_tag:
                title = title_tag.get_text(strip=True)
                title = re.sub(r'<em.*?>|</em>', '', title)
            else:
                continue
            # 链接
            link_tag = card.find('a')
            if link_tag and 'href' in link_tag.attrs:
                link = 'https:' + link_tag['href'] if link_tag['href'].startswith('//') else link_tag['href']
            else:
                continue
            # 作者
            author_tag = card.find('span', class_='bili-video-card__info--author')
            author = author_tag.get_text(strip=True) if author_tag else '未知作者'
            # 日期
            date_tag = card.find('span', class_='bili-video-card__info--date')
            date = date_tag.get_text(strip=True).replace('·', '').strip() if date_tag else '未知日期'
            # 时长 - 多种class兼容
            duration_tag = (
                card.find('span', class_='bili-video-card__info--duration')
                or card.find('span', class_='bili-video-card__stats__duration')
                or card.find('span', class_='so-imgTag_rb')
            )
            duration = duration_tag.get_text(strip=True) if duration_tag else '未知时长'

            # 跳过广告
            if author in ['去看看>', '广告']:
                continue
            results.append({
                'title': title,
                'link': link,
                'author': author,
                'date': date,
                'duration': duration
            })
            count += 1
        return results
    except requests.HTTPError as error:
        raise SearchError(f"B 站搜索返回 HTTP {error.response.status_code}。") from None
    except requests.RequestException as error:
        raise SearchError(f"B 站搜索请求失败 ({type(error).__name__})。") from None


# 查找最高质量音频流
def find_audio_streams(html_content):
    """Return the audio streams advertised for this playback session, in quality order."""
    match = re.search(r"window\.__playinfo__\s*=\s*(?=\{)", html_content)
    if not match:
        raise ValueError("未找到视频播放信息")

    playinfo, _ = json.JSONDecoder().raw_decode(html_content, match.end())
    data = playinfo.get("data") or {}
    dash = data.get("dash") or {}
    flac = (dash.get("flac") or {}).get("audio")
    dolby = (dash.get("dolby") or {}).get("audio")

    groups = {"FLAC": [], "Dolby": [], "DASH": []}
    for quality, entries in (
        ("FLAC", flac),
        ("Dolby", dolby),
        ("DASH", dash.get("audio")),
    ):
        if isinstance(entries, dict):
            entries = [entries]
        for entry in entries or []:
            codec = (entry.get("codecs") or "").lower()
            category = quality
            if codec.startswith("flac"):
                category = "FLAC"
            elif codec.startswith(("ec-3", "ac-3", "eac3")):
                category = "Dolby"
            groups[category].append(entry)

    extensions = {"FLAC": ".flac", "Dolby": ".mka", "DASH": ".m4a"}
    candidates = []
    seen = set()
    for quality, entries in groups.items():
        for entry in sorted(entries, key=lambda item: item.get("bandwidth") or 0, reverse=True):
            url = entry.get("base_url") or entry.get("baseUrl")
            backups = entry.get("backup_url") or entry.get("backupUrl") or []
            urls = [value for value in (url, *backups) if value]
            if not urls or urls[0] in seen:
                continue
            seen.add(urls[0])
            candidates.append({
                "url": urls[0],
                "stream_id": entry.get("id"),
                "backup_urls": urls[1:],
                "bandwidth": entry.get("bandwidth") or 0,
                "codec": entry.get("codecs") or "未知编码",
                "quality": quality,
                "extension": extensions[quality],
            })

    if not candidates:
        segments = data.get("durl") or []
        segments = [segment for segment in segments if segment.get("url")]
        if segments:
            segment = max(segments, key=lambda item: item.get("size") or 0)
            candidates.append({
                "url": segment["url"],
                "source_size": segment.get("size") or 0,
                "backup_urls": segment.get("backup_url") or [],
                "bandwidth": 0,
                "codec": "未知编码",
                "quality": "兼容音轨",
                "extension": ".m4a",
            })
        else:
            raise ValueError("未找到可用音轨")
    return candidates


def find_best_audio_stream(html_content):
    return {"audio": find_audio_streams(html_content)[0]}


def audio_cache_matches(output_path, receipt_path, source):
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        stat = output_path.stat()
    except (OSError, ValueError):
        return False
    return (
        isinstance(receipt, dict)
        and output_path.is_file()
        and receipt == {"source": source, "size": stat.st_size, "modified_ns": stat.st_mtime_ns}
        and stat.st_size > 0
    )


def save_audio_stream(stream, ffmpeg, headers, work_dir, output_dir, filename, video):
    extension = stream["extension"]
    codec = stream["codec"]
    bandwidth = stream["bandwidth"]
    description = f"{stream['quality']} / {codec}"
    if bandwidth:
        description += f" / {bandwidth / 1000:.0f} kb/s"
    output_path = output_dir / f"{filename}{extension}"
    receipt_path = output_dir / ".music-crawler-cache" / f"{output_path.name}.json"
    source = {
        "video": video,
        "media": urlsplit(stream["url"]).path.rsplit("/", 1)[-1],
        "stream_id": stream.get("stream_id"),
        "source_size": stream.get("source_size"),
        "quality": stream["quality"],
        "codec": codec,
        "bandwidth": bandwidth,
        "extension": extension,
    }
    if audio_cache_matches(output_path, receipt_path, source):
        print(f"已存在，跳过下载：{output_path.name}（{description}）")
        return True
    print(f"正在尝试音轨：{description}")

    temp_file = work_dir / "download.m4s"
    staged_output = work_dir / f"audio{extension}"
    for index, media_url in enumerate([stream["url"], *stream["backup_urls"]]):
        if index:
            print("尝试备用下载地址。")
        if not download_large_file(media_url, temp_file, headers):
            continue
        try:
            result = subprocess.run(
                [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i",
                 temp_file, "-map", "0:a:0", "-c:a", "copy", staged_output],
                capture_output=True, timeout=30,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except subprocess.TimeoutExpired:
            print("FFmpeg 封装超时（30 秒）。")
            continue
        if result.returncode != 0:
            print("封装失败: " + result.stderr.decode("utf-8", errors="replace").strip())
            continue

        completed = staged_output.stat()
        staged_output.replace(output_path)
        try:
            receipt_path.parent.mkdir(exist_ok=True)
            write_local_text(receipt_path, json.dumps({
                "source": source, "size": completed.st_size, "modified_ns": completed.st_mtime_ns,
            }, ensure_ascii=False))
        except OSError:
            print("音频已保存，但无法写入下载记录。")
        print(f"已保存：{output_path.name}（{description}）")
        return True
    return False


def download_audio(keyword, url, output_dir=AUDIO_DIR):
    """下载音频文件，所有文件以keyword命名"""
    headers = {
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
        'referer': 'https://www.bilibili.com/',
    }

    try:
        print(f"正在获取音频信息: {keyword}")
        page_headers = headers.copy()
        parsed = urlsplit(url)
        host = parsed.hostname or ""
        if parsed.scheme != "https" or not (host == "bilibili.com" or host.endswith(".bilibili.com")):
            raise ValueError("非 B 站视频地址")
        cookie = get_config("BILIBILI_COOKIE")
        if cookie:
            page_headers["Cookie"] = cookie
        res = requests.get(url, headers=page_headers, timeout=(10, 30))
        res.raise_for_status()

        streams = find_audio_streams(res.text)
        page = parse_qs(parsed.query).get("p", ["1"])[0]
        video = f"{parsed.path.rstrip('/')}?p={page}"
        ffmpeg = ffmpeg_command()
        if not ffmpeg:
            raise ValueError("找不到 FFmpeg")

        output_dir.mkdir(parents=True, exist_ok=True)
        filename = sanitize_filename(keyword)
        with TemporaryDirectory(prefix=".music-crawler-", dir=output_dir) as work_dir:
            for stream in streams:
                if save_audio_stream(stream, ffmpeg, headers, Path(work_dir), output_dir, filename, video):
                    return True
        print("所有可用音轨均下载或封装失败。")
        return False

    except (OSError, ValueError, requests.RequestException) as error:
        detail = type(error).__name__ if isinstance(error, (OSError, requests.RequestException)) else str(error)
        print(f"音频下载失败: {detail}")
        return False


def search_and_list_videos(keyword):
    """
    阶段一：搜索并列出视频。
    返回一个字典，包含关键词和详细的视频结果列表，用于展示给AI。
    """
    print(f"[AI决策阶段] 正在为关键词「{keyword}」搜索视频...")
    videos = search_bilibili_videos(keyword)  # 调用原有的搜索函数
    if not videos:
        print(f"  警告：未找到关键词「{keyword}」的相关视频。")
        return {'keyword': keyword, 'videos': []}

    # 格式化结果，方便后续组装提示词
    formatted_results = []
    for idx, v in enumerate(videos, 1):
        formatted_results.append({
            'index': idx,
            'title': v['title'],
            'author': v['author'],
            'duration': v['duration'],
            'date': v['date'],
            'link': v['link']
        })
    print(f"  成功找到 {len(formatted_results)} 个结果，已准备发送给AI进行选择。")
    return {'keyword': keyword, 'videos': formatted_results}


def download_selected_audio(task_info, selected_index, output_dir=AUDIO_DIR):
    """
    阶段二：根据AI选择的序号下载音频。
    :param task_info: 来自 search_and_list_videos 的返回字典
    :param selected_index: AI选择的序号（1-10之间的整数）
    :return: 下载结果字典
    """
    keyword = task_info['keyword']
    videos = task_info['videos']

    if not videos:
        return {'success': False, 'message': f'无可用视频，跳过下载。'}

    if not (1 <= selected_index <= len(videos)):
        print(f"  AI选择的序号 {selected_index} 无效，将自动选择第一个。")
        selected_index = 1

    selected_video = videos[selected_index - 1]  # 调整为列表索引
    video_title = selected_video['title']

    print(f"[程序执行阶段] AI已选择序号 {selected_index}: 《{video_title[:50]}...》")
    print(f"  开始下载音频...")

    download_url = urljoin("https://www.bilibili.com/", selected_video["link"])
    success = download_audio(keyword, download_url, output_dir)

    if success:
        msg = f"「{keyword}」音频下载完成！(基于AI选择：{selected_index})"
        print(f"  [OK] {msg}")
        return {'success': True, 'keyword': keyword, 'ai_choice': selected_index, 'message': msg}
    else:
        msg = f"「{keyword}」音频下载失败。"
        print(f"  [!] {msg}")
        return {'success': False, 'keyword': keyword, 'ai_choice': selected_index, 'message': msg}
