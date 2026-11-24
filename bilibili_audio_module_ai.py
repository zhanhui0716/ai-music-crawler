# 文件保存为: bilibili_audio_module_ai.py
import requests, os, re, json, threading, time, subprocess
from bs4 import BeautifulSoup
from urllib.parse import urlsplit
from local_config import get_config


# ---------- 你原有的所有工具函数 (sanitize_filename, download_large_file, print_dots, find_best_audio_stream, download_audio) ----------
# 注意：为了节省篇幅，此处省略了这些函数的完整代码。你必须将上一个回复中 `bilibili_audio_module.py` 文件里，
# 从 `def sanitize_filename(name):` 开始，到 `def download_audio(...):` 结束的所有函数定义，原封不动地复制粘贴到这里。
# ---------- 以下是必须复制粘贴的原有函数列表 ----------
# def sanitize_filename(name):
# def download_large_file(url, filepath, headers, max_retry=3):
# def print_dots(stop_event):
# def search_bilibili_videos(keyword, max_results=10): # 这个函数特别重要！
# def find_best_audio_stream(html_content):
# def download_audio(keyword, url, stop_event):
# ----------------------------------------------------

# 安全文件名处理
def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "", name).strip()


# 带重试的流式下载
def download_large_file(url, filepath, headers, max_retry=3):
    for attempt in range(max_retry):
        try:
            with requests.get(url, headers=headers, stream=True) as r:
                r.raise_for_status()
                total_size = int(r.headers.get('content-length', 0))
                downloaded = 0

                with open(filepath, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0:
                                percent = downloaded / total_size * 100
                                print(f"\r下载中: {percent:.1f}%", end='', flush=True)
                print()  # 换行
            return True
        except Exception as e:
            print(f"\n下载失败 ({attempt + 1}/{max_retry}): {e}")
            time.sleep(2)  # 重试前等待
    return False


# 后台打印进度点
def print_dots(stop_event):
    """在后台打印进度点"""
    while not stop_event.is_set():
        print('.', end='', flush=True)
        time.sleep(1)


def search_bilibili_videos(keyword, max_results=10):
    """根据关键词搜索B站视频，返回前max_results个视频信息"""
    try:
        url = f'https://search.bilibili.com/all?keyword={keyword}'
        headers = {
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 Edg/132.0.0.0',
            'referer': 'https://www.bilibili.com/',
        }
        cookie = get_config("BILIBILI_COOKIE")
        if cookie:
            headers["Cookie"] = cookie
        res = requests.get(url, headers=headers, timeout=10)
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
    except requests.exceptions.RequestException as e:
        print(f"网络请求失败: {e}")
        return []
    except Exception as e:
        print(f"解析视频列表时出错: {e}")
        import traceback
        traceback.print_exc()
        return []

# 查找最高质量音频流
def find_best_audio_stream(html_content):
    """从HTML内容中提取最佳音频流信息"""
    # 提取JSON数据
    match = re.search(r'window\.__playinfo__\s*=\s*({.*?})\s*</script>', html_content, re.DOTALL)
    if not match:
        # 尝试备用匹配模式
        match = re.search(r'<script>window\.__playinfo__\s*=\s*({.*?})</script>', html_content, re.DOTALL)
        if not match:
            raise ValueError("未找到视频信息")

    playinfo = json.loads(match.group(1))

    # 检查是否有dash格式数据
    if 'data' not in playinfo or 'dash' not in playinfo['data']:
        # 尝试从其他位置获取音频
        if 'data' in playinfo and 'durl' in playinfo['data']:
            # 处理非dash格式
            durls = playinfo['data']['durl']
            if durls:
                # 选择最高质量的音频（按size排序）
                best_audio = max(durls, key=lambda x: x.get('size', 0))
                return {
                    'audio': {
                        'url': best_audio['url'],
                        'backup_urls': best_audio.get('backup_url', []),
                        'size': best_audio.get('size', 0)
                    }
                }
        raise ValueError("不支持的音频格式")

    dash_data = playinfo['data']['dash']

    # 选择最高质量音频流（按带宽排序）
    audio_streams = dash_data.get('audio', [])
    if not audio_streams:
        raise ValueError("未找到音频流")

    # 优先选择高比特率的音频
    audio_streams.sort(key=lambda x: x.get('bandwidth', 0), reverse=True)
    best_audio = audio_streams[0]

    # 提取URL（兼容不同大小写键名）
    audio_url = best_audio.get('base_url') or best_audio.get('baseUrl', '')

    # 获取备用URL（如果存在）
    backup_urls = best_audio.get('backup_url') or best_audio.get('backupUrl', [])

    return {
        'audio': {
            'url': audio_url,
            'backup_urls': backup_urls,
            'bandwidth': best_audio.get('bandwidth', 0),
            'codec': best_audio.get('codecs', '未知编码')
        }
    }


def download_audio(keyword, url, stop_event):
    """下载音频文件，所有文件以keyword命名"""
    headers = {
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
        'referer': 'https://www.bilibili.com/',
    }

    try:
        print(f"正在获取音频信息: {keyword}")
        page_headers = headers.copy()
        host = urlsplit(url).hostname or ""
        if urlsplit(url).scheme == "https" and (host == "bilibili.com" or host.endswith(".bilibili.com")):
            cookie = get_config("BILIBILI_COOKIE")
            if cookie:
                page_headers["Cookie"] = cookie
        res = requests.get(url, headers=page_headers)
        res.raise_for_status()

        audio_info = find_best_audio_stream(res.text)
        audio_url = audio_info['audio']['url']

        safe_name = sanitize_filename(keyword)
        os.makedirs('B站下载的音频', exist_ok=True)
        temp_file = f'B站下载的音频/{safe_name}_temp.m4s'
        output_path = f'B站下载的音频/{safe_name}.m4a'

        print(f"正在下载音频流: {keyword}")
        if not download_large_file(audio_url, temp_file, headers):
            if 'backup_urls' in audio_info['audio'] and audio_info['audio']['backup_urls']:
                print("尝试使用备用URL下载...")
                for backup_url in audio_info['audio']['backup_urls']:
                    print(f"尝试备用URL: {backup_url}")
                    if download_large_file(backup_url, temp_file, headers):
                        break
                else:
                    return False
            else:
                return False
        print(f"正在封装为标准音频文件: {keyword}")
        # 调用FFmpeg将.m4s封装为.m4a
        try:
            result = subprocess.run(['ffmpeg', '-y', '-i', temp_file, '-c', 'copy', output_path], 
                                   capture_output=True, text=False, timeout=30)
        except subprocess.TimeoutExpired:
            print(f"FFmpeg封装超时（30s），跳过此文件。")
            return False
        if result.returncode != 0:
            stderr_decoded = result.stderr.decode('utf-8', errors='ignore')
            stdout_decoded = result.stdout.decode('utf-8', errors='ignore')
            print(f"FFmpeg封装失败: {stderr_decoded}")
            print(f"FFmpeg stdout: {stdout_decoded}")
            return False

        # 删除临时文件
        if os.path.exists(temp_file):
            os.remove(temp_file)
            print(f"临时文件已删除: {temp_file}")

        return True

    except Exception as e:
        print(f"音频下载失败: {e}")
        import traceback
        traceback.print_exc()
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


def download_selected_audio(task_info, selected_index):
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

    # 调用原有的下载函数
    stop_event = threading.Event()
    dot_thread = threading.Thread(target=print_dots, args=(stop_event,))
    dot_thread.daemon = True
    dot_thread.start()

    download_url = selected_video['link']
    if download_url.startswith('/'):
        download_url = 'https://www.bilibili.com' + download_url

    os.makedirs('B站下载的音频', exist_ok=True)  # 确保目录存在
    success = download_audio(keyword, download_url, stop_event)

    stop_event.set()
    if dot_thread.is_alive():
        dot_thread.join(timeout=1)

    if success:
        msg = f"「{keyword}」音频下载完成！(基于AI选择：{selected_index})"
        print(f"  ✅ {msg}")
        return {'success': True, 'keyword': keyword, 'ai_choice': selected_index, 'message': msg}
    else:
        msg = f"「{keyword}」音频下载失败。"
        print(f"  ❌ {msg}")
        return {'success': False, 'keyword': keyword, 'ai_choice': selected_index, 'message': msg}