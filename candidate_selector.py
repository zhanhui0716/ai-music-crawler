import re
import unicodedata


ALTERNATE_VERSION = re.compile(
    r"伴奏|消音|翻唱|改编|混剪|合唱|现场|演唱会|串烧|片段|循环|加速|降速|空耳|卡拉[โอoＯ]?[kK]|"
    r"\b(?:cover|live|karaoke|instrumental|remix|loop|sped up|slowed)\b", re.I
)
MUSIC_VIDEO = re.compile(r"音乐视频|\b(?:mv|music video)\b", re.I)
STUDIO = re.compile(r"纯音频|音频版|录音室|录音棚|录音版|\b(?:audio|studio)\b", re.I)
HI_RES = re.compile(r"hi[\s-]*res|无损|\bflac\b", re.I)


def normalize(text):
    return unicodedata.normalize("NFKC", text).casefold()


def match_text(text):
    return "".join(char for char in normalize(text) if char.isalnum())


def duration_score(duration):
    parts = duration.split(":")
    if len(parts) not in (2, 3) or not all(part.isdecimal() and len(part) <= 3 for part in parts):
        return 1
    seconds = 0
    for part in parts:
        seconds = seconds * 60 + int(part)
    if 90 <= seconds <= 480:
        return 3
    if 45 <= seconds <= 900:
        return 2
    return 0


def choose_candidate(videos, keyword):
    """Select the candidate number using only local data and deterministic rules."""
    tokens = [match_text(token) for token in re.findall(r"[^\W_]+", normalize(keyword))]
    tokens = [token for token in tokens if token]
    query = match_text(keyword)

    def rank(video):
        title = normalize(video["title"])
        title_text = match_text(title)
        author_text = match_text(video.get("author", ""))
        version_penalty = bool(ALTERNATE_VERSION.search(title)) + bool(MUSIC_VIDEO.search(title))
        mentions = sum(token in title_text for token in tokens)
        author_mentions = sum(token in author_text for token in tokens)
        return (
            bool(query and query in title_text) or bool(tokens and mentions == len(tokens)),
            mentions,
            -version_penalty,
            duration_score(video.get("duration", "")),
            bool(STUDIO.search(title)),
            bool(HI_RES.search(title)),
            author_mentions,
            -video["index"],
        )

    return max(videos, key=rank)["index"]
