import html
from pathlib import Path
from string import Template


def safe_url(value):
    from urllib.parse import urlsplit
    try:
        u = urlsplit(value)
        return value if u.scheme == 'https' and u.hostname and not u.username else ''
    except ValueError:
        return ''


def fields(item):
    r, a = item['repository'], item['assessment']
    url = r['html_url']
    visual = ('有演示素材线索，适合进一步看片确认；3秒能否看懂、前后变化和分享理由尚未核实。'
              '可测试开头：看一下这个开源工具的实际操作。' if a['has_visual_markers'] else '暂不判断；未识别到官方视觉素材线索。')
    ref = item.get('readme_ref', r.get('default_branch', '未知'))
    purpose = '用番茄钟安排专注与休息计时。' if (a['feature_match'] or '').lower() == 'pomodoro' else '按官方描述归入「' + a['category'] + '」。'
    special = '；'.join(f['text'] for f in a.get('documented_facts', [])[:2])
    return [
        ('核心用途', purpose + '官方原文：' + (r.get('description') or '未提供')),
        ('特别之处', (special + '（正式版本 README 声明）' if special else '说明中识别到「' + a['feature_match'] + '」') + '；是否有独创性待编辑确认。'),
        ('适合用户', a['audience']),
        ('使用场景', '如果你有「' + a['category'] + '」需求，可先查看官方演示与兼容说明；本文未验证实际体验。'),
        ('使用步骤', '1. 查看 README 的 ' + a['install_heading'] + ' 章节；2. 在官方 Release 中核对系统、架构与安装说明；3. 确认权限和费用后自行决定是否安装。'),
        ('支持平台', '、'.join(a['platforms']) + '（README 出现的系统名称，具体版本和功能支持范围请核对原文）'),
        ('免费及成本', '源代码许可证：' + a['license'] + '。未在已读取片段识别出付费关键词，不等于确认完全免费；安装包收费、内购、硬件及服务成本未知。'),
        ('使用风险', '未运行或审计；安装前核对发布者、权限、隐私及安装包校验。涉及个人文件时先备份。'),
        ('最近更新', r['pushed_at'] + '（仓库推送时间，不代表 Release 日期或功能可用）'),
        ('正式 Release', (item.get('release') or {}).get('tag_name', '无') + '；' + ((item.get('release') or {}).get('published_at') or '日期未知')),
        ('抖音视频潜力', visual),
        ('规则分及依据', str(a['score']) + '/100，另有 ' + str(a['pending_points']) + ' 分待确认。' + '；'.join(k + ' ' + str(v['earned']) + '/' + str(v['max']) + '：' + v['basis'] for k, v in a['dimensions'].items())),
        ('核查边界', a['verification'] + '。README 依据版本：' + ref + '；文档声明不等于已验证的软件行为。')]


def render(root, day, items, log):
    n = len(items)
    subject = f'GitHub 冷门好物日报｜{day}｜今天发现的{n}个有趣项目' if n else f'GitHub 冷门好物日报｜{day}｜今日暂无通过核查的项目'
    intro = '零 AI 规则初筛版。分数只表示文档证据，不是质量认证；创意与实际体验待确认。'
    md = [f'# {subject}', '', intro, '']
    blocks = []
    for i, item in enumerate(items):
        r, a = item['repository'], item['assessment']
        role = '惊喜线索' if r['stargazers_count'] < 100 and a['has_visual_markers'] else '实用线索'
        title = f'{role}：{a["category"]} · {r["name"]}'
        url = safe_url(r['html_url'])
        md.extend([f'## {title}', '', f'[{r["full_name"]}]({url}) · {r["stargazers_count"]} Stars（采集时）', ''])
        body = []
        for label, value in fields(item):
            md.append(f'- **{label}**：{value}')
            body.append('<p><b>' + html.escape(label) + '：</b>' + html.escape(value) + '</p>')
        from urllib.parse import quote
        readme_url = url + '/tree/' + quote(item.get('readme_ref', r.get('default_branch', 'main')), safe='') + '#readme'
        links = [('README / 安装说明', readme_url), ('官方 Release', safe_url((item.get('release') or {}).get('html_url', '')))]
        if a['has_visual_markers']:
            links.append(('官方演示素材所在 README（媒体未验证）', readme_url))
        md.extend([''] + [f'[{label}]({link})' for label, link in links if link] + [''])
        blocks.append('<article><h2>' + html.escape(title) + '</h2><p><a href="' + html.escape(url, quote=True) + '">' + html.escape(r['full_name']) + '</a> · ' + str(r['stargazers_count']) + ' Stars</p>' + ''.join(body) + '<p>' + ' · '.join('<a href="' + html.escape(link, quote=True) + '">' + html.escape(label) + '</a>' for label, link in links if link) + '</p></article>')
    if not n:
        message = '今日没有足够证据支持自动推荐，未凑数。原因：' + ('；'.join(log['stops']) or '候选未通过安装包、许可证、场景、维护和风险筛选。')
        md.append(message)
        blocks.append('<article><p>' + html.escape(message) + '</p></article>')
    md.extend(['', '|项目|用途|规则分|使用门槛|视频潜力|', '|---|---|---|---|---|'])
    rows = []
    for x in items:
        r, a = x['repository'], x['assessment']
        values = [r['name'], a['category'], str(a['score']) + '/100（部分待确认）', '有安装包，具体步骤待核对', '有素材线索，待看片' if a['has_visual_markers'] else '未确认']
        md.append('|' + '|'.join(v.replace('|', '／') for v in values) + '|')
        rows.append('<tr>' + ''.join('<td>' + html.escape(v) + '</td>' for v in values) + '</tr>')
    pick = items[0]['repository']['name'] if items else '无'
    video = next((x['repository']['name'] for x in items if x['assessment']['has_visual_markers']), '无')
    tail = f'今日最值得安装：{pick}（仅优先了解，未实测）。今日最适合拍视频：{video}（待看片确认）。'
    resources = f'本次累计：程序 GitHub REST 请求 {log["github_api_requests"]}；候选 {log["candidates"]}；深查 {log["deep_checked"]}；推荐 {n}；LLM 调用 0，Tokens 0，AI API 费用 0 元。云平台账单／邮件剩余额度：不可获取。'
    md.extend(['', tail, '', resources])
    content = ''.join(blocks) + '<table><tr><th>项目</th><th>用途</th><th>规则分</th><th>门槛</th><th>视频</th></tr>' + ''.join(rows) + '</table><p>' + html.escape(tail) + '</p><p>' + html.escape(resources) + '</p>'
    template = Template((root / 'templates/email.html').read_text())
    html_text = template.substitute(subject=html.escape(subject), intro=html.escape(intro), content=content)
    out = root / 'reports' / day
    out.mkdir(parents=True, exist_ok=True)
    (out / 'daily.md').write_text('\n'.join(md) + '\n', encoding='utf-8')
    (out / 'daily.html').write_text(html_text, encoding='utf-8')
    return subject
