import json
import os
import subprocess
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TZ = timezone(timedelta(hours=8))


def today():
    return datetime.now(TZ).date().isoformat()


def load(path, default):
    return json.loads(path.read_text()) if path.exists() else default


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    with tmp.open('w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)


@contextmanager
def lock(root):
    import fcntl
    (root / 'data').mkdir(parents=True, exist_ok=True)
    with (root / 'data/.lock').open('w') as f:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


class Store:
    def __init__(self, root=ROOT, day=None):
        self.root = Path(root)
        self.day = day or today()
        self.path = self.root / 'data/state.json'
        self.data = load(self.path, {'version': 1, 'days': {}, 'repositories': {}})
        self.log = self.data['days'].setdefault(self.day, {
            'date': self.day, 'github_api_requests': 0, 'candidates': 0,
            'deep_checked': 0, 'recommendations': 0, 'llm_calls': 0,
            'llm_input_tokens': 0, 'llm_output_tokens': 0, 'ai_cost_cny': 0,
            'ai_cost_basis': '程序没有模型接口或模型调用路径',
            'program_seconds': 0, 'actions_job_seconds': None,
            'actions_billed_cost': None, 'provider_remaining_quota': None,
            'cloud_runs': [], 'email_result': 'not_configured', 'smtp_attempts': 0,
            'retry_used': False, 'over_budget': False, 'stops': [], 'api_events': []})

    def save(self):
        write(self.path, self.data)
        write(self.root / 'reports' / self.day / 'usage.json', self.log)
        month = self.day[:7]
        logs = [x for d, x in self.data['days'].items() if d.startswith(month)]
        write(self.root / 'reports' / (month + '-summary.json'), {
            'month': month, 'smtp_accepted_reports': sum(x['email_result'] == 'accepted' for x in logs),
            'github_api_requests': sum(x['github_api_requests'] for x in logs),
            'llm_tokens': sum(x['llm_input_tokens'] + x['llm_output_tokens'] for x in logs),
            'confirmed_ai_cost_cny': sum(x['ai_cost_cny'] for x in logs),
            'cloud_runs_observed': sum(len(x['cloud_runs']) for x in logs),
            'actions_billed_cost': '不可获取；未把本机计时当作账单数据',
            'provider_remaining_quota': '不可获取',
            'scope': '仅本系统记录；不包含账号其他工作流、Git 传输或平台内部请求'})

    def stop(self, reason):
        if reason not in self.log['stops']:
            self.log['stops'].append(reason)
        self.save()

    def checkpoint(self):
        """Persist intent BEFORE SMTP DATA. Never send after a failed remote push."""
        self.save()
        if os.getenv('GITHUB_ACTIONS') != 'true':
            return
        if os.getenv('PERSIST_STATE') != 'git':
            raise RuntimeError('cloud_persistence_not_enabled')
        for args in [
            ['git', 'add', 'data', 'reports'],
            ['git', '-c', 'user.name=hidden-gems-bot', '-c',
             'user.email=hidden-gems-bot@users.noreply.github.com',
             'commit', '--allow-empty', '-m', 'Persist daily delivery checkpoint'],
            ['git', 'push', 'origin', 'HEAD:main']]:
            subprocess.run(args, cwd=self.root, check=True, capture_output=True)
