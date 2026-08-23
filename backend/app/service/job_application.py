import re
from urllib.parse import unquote, urlparse


KNOWN_CHANNELS = {
    "jobs.bytedance.com": "字节跳动招聘",
    "join.qq.com": "腾讯招聘",
    "talent.baidu.com": "百度招聘",
    "career.huawei.com": "华为招聘",
    "jobs.alibaba.com": "阿里巴巴招聘",
    "www.nowcoder.com": "牛客",
    "www.zhipin.com": "BOSS直聘",
    "jobs.51job.com": "前程无忧",
    "www.liepin.com": "猎聘",
}


def _match_labeled_value(text: str, labels: tuple[str, ...]) -> str:
    joined = "|".join(re.escape(label) for label in labels)
    match = re.search(
        rf"(?:^|[\n,，;；])\s*(?:{joined})\s*[:：]\s*([^\n,，;；]+)", text, re.I
    )
    return match.group(1).strip() if match else ""


def infer_job_information(job_url: str, notes: str) -> dict[str, str]:
    parsed = urlparse(job_url)
    host = parsed.netloc.lower().removeprefix("www.")
    channel = next(
        (label for domain, label in KNOWN_CHANNELS.items() if domain in parsed.netloc.lower()),
        host or "招聘网站",
    )
    company = _match_labeled_value(notes, ("公司", "企业", "company"))
    role = _match_labeled_value(notes, ("岗位", "职位", "方向", "role", "position"))
    location = _match_labeled_value(notes, ("地点", "城市", "工作地", "location"))

    path_parts = [
        unquote(part).replace("-", " ").replace("_", " ").strip()
        for part in parsed.path.split("/")
        if part and not part.isdigit() and len(part) > 2
    ]
    if not company:
        company = channel.replace("招聘", "") if channel != host else host.split(".")[0].title()
    if not role:
        first_line = notes.strip().splitlines()[0].strip() if notes.strip() else ""
        role = first_line[:160] if first_line and ":" not in first_line and "：" not in first_line else ""
    if not role and path_parts:
        role = path_parts[-1][:160]
    return {
        "company": company or "待补充公司",
        "role": role or "待补充岗位",
        "location": location,
        "channel": channel,
    }
