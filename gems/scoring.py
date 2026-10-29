"""Evidence rules are proxies. Unmeasured novelty and value are NEVER filled in."""
import re
from datetime import date

EXCLUDE = re.compile(r'\b(sdk|framework|boilerplate|leetcode|prompt[s]?|mcp[- ]server|agent[- ]skills?|awesome[- ]|library for developers|api wrapper)\b', re.I)
HIGH_RISK = re.compile(r'curl[^\n]{0,160}\|\s*(?:sudo\s+)?(?:ba)?sh|disable (?:your )?(?:antivirus|sip|gatekeeper)|jailbreak|\brooting\b', re.I)
PAID = re.compile(r'\b(subscription|paid plan|payment required|credit card|api[_ -]?key|billing|buy credits)\b|付费|订阅|购买额度', re.I)
LICENSES = {'MIT', 'Apache-2.0', 'GPL-2.0', 'GPL-3.0', 'AGPL-3.0', 'BSD-2-Clause', 'BSD-3-Clause', 'MPL-2.0', 'ISC', 'Unlicense', 'CC0-1.0', 'LGPL-3.0', 'LGPL-2.1'}
# Each category has a narrow user action, rather than inferring from the repo name.
CATEGORIES = [
    ('照片管理', r'photo (?:manager|organizer|management)|照片管理|image (?:organizer|viewer)|photo viewer', '整理、浏览照片的用户'),
    ('图片处理', r'image (?:compress|convert|resiz|editor)|photo editor|image editing|图片压缩|图片编辑', '需要处理图片的用户'),
    ('屏幕工具', r'screen(?:shot| recorder| recording)|截屏|截图|录屏', '需要截图或录屏的用户'),
    ('跨设备', r'file (?:transfer|sharing)|share files|screen mirroring|second (?:screen|monitor)|across devices|跨设备|传输文件', '需要在设备间传文件或共享屏幕的用户'),
    ('剪贴板', r'clipboard (?:manager|history)|剪贴板', '经常复制粘贴内容的用户'),
    ('桌面效率', r'menu[- ]bar|menubar|desktop (?:app|application|widget)|window manager|窗口管理', '希望改善桌面操作的用户'),
    ('旧设备改造', r'old (?:phone|tablet|device)|repurpose|e[- ]ink|raspberry pi|旧手机|旧平板', '愿意动手改造闲置设备的用户'),
    ('文件整理', r'file (?:organizer|renamer)|rename files|batch renam|duplicate (?:file|finder)|文件整理|批量重命名', '需要整理文件的用户'),
    ('音视频', r'video (?:editor|player|compress)|audio (?:editor|transcri)|subtitle|字幕|视频剪辑', '需要处理音视频或字幕的用户'),
    ('生活工具', r'personal (?:finance|budget)|habit track|pomodoro|recipe (?:manager|organizer)|expense track|番茄钟|记账', '有相应生活管理需求的用户')]


def classify(text):
    for name, pattern, audience in CATEGORIES:
        m = re.search(pattern, text, re.I)
        if m:
            return name, audience, m.group(0)
    return None, None, None


def age(day, timestamp):
    try:
        return max(0, (date.fromisoformat(day) - date.fromisoformat(timestamp[:10])).days)
    except (ValueError, TypeError):
        return 9999


def fingerprint(text):
    return set(re.findall(r'[a-z]{4,}', text.lower())) - {'this', 'with', 'from', 'your', 'that', 'have', 'application', 'open', 'source'}


def similar(a, b):
    x, y = fingerprint(a), fingerprint(b)
    return bool(x and y) and len(x & y) / len(x | y) >= .55


def eligible(repo, day, config):
    text = (repo.get('description') or '') + ' ' + ' '.join(repo.get('topics', []))
    return (not any(repo.get(k) for k in ('fork', 'archived', 'disabled'))
            and 20 <= repo.get('stargazers_count', 0) <= config['max_stars']
            and age(day, repo.get('pushed_at')) <= config['max_inactive_days']
            and not EXCLUDE.search(text) and classify(text)[0] is not None)


def assess(repo, readme, release, day):
    desc = repo.get('description') or ''
    category, audience, match = classify(desc + ' ' + ' '.join(repo.get('topics', [])))
    spdx = (repo.get('license') or {}).get('spdx_id')
    assets = [a for a in (release or {}).get('assets', [])
              if re.search(r'\.(?:dmg|exe|msi|apk|appimage|deb|flatpakref|pkg)(?:$)', a.get('name', ''), re.I)]
    install = re.search(r'(?im)^#{1,4}\s+.*(?:install|download|getting started|quick start|安装|下载|使用)', readme)
    # Presence only; no fabricated visual inspection of images/video.
    visual = bool(re.search(r'!\[[^\]]*\]\([^\s)]+\)|<img\b|https://(?:user-images|github.com/user-attachments)|\.gif\b|youtu(?:\.be|be\.com)', readme, re.I))
    platforms = []
    for label, pattern in [('Windows', r'\bwindows\b'), ('macOS', r'\bmacos\b|\bmac os\b'), ('Linux', r'\blinux\b'), ('Android', r'\bandroid\b'), ('iOS', r'\bios\b')]:
        if re.search(pattern, readme, re.I):
            platforms.append(label)
    risks = []
    if HIGH_RISK.search(readme):
        risks.append('发现高风险安装或设备权限提示，自动推荐排除')
    if PAID.search(readme):
        risks.append('发现费用或 API Key 相关词，费用边界需人工确认')
    if category == '旧设备改造':
        risks.append('额外硬件、刷机兼容性与损坏成本需人工确认')
    accepted = bool(category and spdx in LICENSES and install and assets and platforms and not risks)
    facts = []
    for source, chinese in [
        ('Detailed statistics of work/study times', '统计工作和学习时长'),
        ('Customizable timer parameters', '可自定义计时参数'),
        ('clipboard history', '提供剪贴板历史记录'),
        ('batch rename', '支持批量重命名')]:
        if source.lower() in readme.lower():
            facts.append({'text': chinese, 'readme_evidence': source})
    dimensions = {
        '新意与惊喜感': {'earned': (6 if repo.get('stargazers_count', 99999) < 2000 else 3) + (4 if visual else 0), 'max': 30, 'pending': 20,
                   'basis': '小众程度与视觉资料仅作线索；独创性和惊喜感待编辑确认'},
        '普通用户实际价值': {'earned': (10 if category else 0) + (6 if assets else 0) + (4 if install else 0), 'max': 30, 'pending': 10,
                      'basis': '描述匹配使用场景、程序包及安装章节；真实体验待确认'},
        '可视化演示能力': {'earned': (12 if visual else 0) + (4 if assets else 0), 'max': 20, 'pending': 4,
                    'basis': 'README 媒体标记与可下载应用；未打开验证媒体和画面效果'},
        '可用性和维护状态': {'earned': (4 if age(day, repo.get('pushed_at')) <= 90 else 2) + (3 if release else 0) + (3 if spdx in LICENSES else 0), 'max': 10, 'pending': 0,
                       'basis': '最近推送、正式 Release 与明确许可证；推送不等于功能维护'},
        '成本与上手难度': {'earned': (5 if assets else 0) + (3 if install else 0), 'max': 10, 'pending': 2,
                     'basis': '安装包和安装章节；硬件、内购及运行成本仍需用户核对'}}
    return {'accepted': accepted, 'category': category, 'audience': audience,
            'feature_match': match, 'documented_facts': facts, 'license': spdx, 'platforms': platforms,
            'assets': [{'name': a['name'], 'url': a['browser_download_url']} for a in assets[:6]],
            'install_heading': install.group(0).strip() if install else None,
            'has_visual_markers': visual, 'risks': risks,
            'score': sum(d['earned'] for d in dimensions.values()), 'dimensions': dimensions,
            'pending_points': sum(d['pending'] for d in dimensions.values()),
            'verification': '仅公开文档核查；未下载、未运行、未验证二进制安全或功能'}
