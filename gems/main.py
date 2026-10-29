import argparse
import hashlib
import json
import os
import time
from datetime import date, timedelta
from urllib.parse import urlencode

from .github import GitHub, StopCollection
from .mailer import deliver
from .render import render
from .scoring import age, assess, eligible, similar
from .storage import ROOT, Store, load, lock, today, write


def configuration(root):
    c = load(root / 'config.json', {})
    for key, low, high in [('api_requests_per_day', 1, 50), ('candidate_limit', 1, 60),
                           ('deep_limit', 1, 10), ('recommendation_limit', 1, 3),
                           ('readme_bytes', 1000, 30000), ('max_retries_per_day', 0, 1)]:
        if not isinstance(c.get(key), int) or not low <= c[key] <= high:
            raise ValueError('invalid_budget_' + key)
    if c['ai_editor_enabled'] or os.getenv('AI_EDITOR_ENABLED', 'false').lower() != 'false':
        raise ValueError('AI_editor_not_implemented_no_paid_calls_allowed')
    if c['max_retries_per_day'] == 0:
        c['disable_retry'] = True
    return c


def queries(day):
    cutoff = (date.fromisoformat(day) - timedelta(days=180)).isoformat()
    base = f' stars:20..5000 pushed:>{cutoff} archived:false fork:false'
    # Rotate topics each day, keep bounded discovery; no Trending or model calls.
    groups = [
        ['topic:clipboard', 'topic:menubar', 'topic:window-manager'],
        ['topic:photo-management', 'topic:image-processing', 'topic:screenshot'],
        ['topic:file-sharing', 'topic:screen-mirroring', 'topic:file-transfer'],
        ['topic:video-editor', 'topic:subtitle', 'topic:audio-player'],
        ['topic:e-ink', 'topic:file-organizer', 'topic:pomodoro']]
    offset = date.fromisoformat(day).toordinal() % 3
    return [g[(offset + i) % len(g)] + base for i, g in enumerate(groups)]


def seen(store, repo, config, selected=None):
    if repo.get('fork') or repo.get('parent') or repo.get('source'):
        return True
    for key, old in store.data['repositories'].items():
        recommended = old.get('recommended_date')
        if not recommended:
            continue
        if age(store.day, recommended) < config['dedup_days'] and (str(repo['id']) == key or repo['full_name'].lower() in [n.lower() for n in old.get('aliases', [])]):
            return True
        if age(store.day, recommended) < config['similarity_days']:
            from .scoring import classify
            category = classify((repo.get('description') or '') + ' ' + ' '.join(repo.get('topics', [])))[0]
            if old.get('category') == category or similar(repo.get('description') or '', old.get('description') or ''):
                return True
    for x in selected or []:
        if x['assessment']['category'] == repo.get('_category'):
            return True
        if similar(repo.get('description') or '', x['repository'].get('description') or ''):
            return True
    return False


def cloud_check(api):
    if os.getenv('GITHUB_ACTIONS') != 'true':
        return
    repo_name = os.environ['GITHUB_REPOSITORY']
    info = api.get('/repos/' + repo_name)
    if info.get('visibility') != 'public' or os.getenv('RUNNER_OS') != 'Linux':
        raise StopCollection('cloud_free_policy_requires_public_standard_linux')
    run_id = os.getenv('GITHUB_RUN_ID', 'unknown')
    if run_id not in api.store.log['cloud_runs']:
        api.store.log['cloud_runs'].append(run_id)
    api.store.log['actions_free_policy'] = 'public repository; workflow fixed ubuntu-latest; no artifacts/cache/larger runner'


def prepare(store, config):
    log = store.log
    if log.get('prepared'):
        return  # Same date resumes frozen outbox, never recollects.
    if log.get('collection_started'):
        store.stop('interrupted_collection_use_saved_verified_items_no_rescan')
        checked = log.get('verified_items', [])
    else:
        log['collection_started'] = True
        store.save()
        api = GitHub(store, config)
        checked = []
        candidates = {}
        try:
            cloud_check(api)
            limits = api.get('/rate_limit')
            for bucket in ('core', 'search'):
                api.remaining[bucket] = limits['resources'][bucket]['remaining']
            for i, query in enumerate(queries(store.day)):
                if len(candidates) >= config['candidate_limit']:
                    break
                for r in api.search(query, count=min(12, config['candidate_limit'] - len(candidates)), sort='updated' if i % 2 else 'stars'):
                    candidates.setdefault(str(r['id']), r)
            log['candidates'] = len(candidates)
            write(store.root / 'data' / 'candidates.json', {'date': store.day, 'repositories': list(candidates.values())})
            possible = [r for r in candidates.values() if eligible(r, store.day, config) and not seen(store, r, config)]
            possible.sort(key=lambda r: (r.get('stargazers_count', 0) < 2000, r.get('pushed_at') or ''), reverse=True)
            for r in possible[:config['deep_limit']]:
                log['deep_checked'] += 1
                store.save()
                name = r['full_name']
                detail = api.get('/repos/' + name)
                if not detail or seen(store, detail, config) or not eligible(detail, store.day, config):
                    continue
                release = api.get('/repos/' + detail['full_name'] + '/releases/latest', missing=None)
                ref = (release or {}).get('tag_name', detail['default_branch'])
                readme = api.get('/repos/' + detail['full_name'] + '/readme?' + urlencode({'ref': ref}), raw=True, missing='')
                a = assess(detail, readme, release, store.day)
                item = {'repository': {k: detail.get(k) for k in ['id', 'name', 'full_name', 'html_url', 'description', 'stargazers_count', 'pushed_at', 'created_at', 'default_branch', 'homepage', 'topics']},
                        'assessment': a, 'release': {k: release.get(k) for k in ['tag_name', 'html_url', 'published_at']} if release else None,
                        'readme_sha256': hashlib.sha256(readme.encode()).hexdigest(),
                        'readme_excerpt': readme[:6000], 'readme_ref': ref, 'checked_date': store.day}
                checked.append(item)
                log['verified_items'] = checked
                key = str(detail['id'])
                old = store.data['repositories'].get(key, {})
                store.data['repositories'][key] = {**old, 'repository_id': detail['id'], 'name': detail['full_name'],
                    'url': detail['html_url'], 'stars': detail['stargazers_count'], 'category': a['category'],
                    'description': detail.get('description'), 'discovered_date': old.get('discovered_date', store.day),
                    'updated_date': detail['pushed_at'], 'checked_date': store.day,
                    'aliases': list(set(old.get('aliases', []) + [detail['full_name']])),
                    'key_feature': a['feature_match'], 'score': a['score'], 'score_basis': a['dimensions'],
                    'verification': a['verification'], 'ever_recommended': old.get('ever_recommended', False)}
                store.save()
        except StopCollection as e:
            store.stop(str(e))
    selected = []
    for item in sorted(checked, key=lambda x: x['assessment']['score'], reverse=True):
        a, r = item['assessment'], item['repository']
        if not a['accepted'] or a['score'] < config['minimum_evidence_score']:
            continue
        r['_category'] = a['category']
        if seen(store, r, config, selected):
            continue
        selected.append(item)
        if len(selected) >= config['recommendation_limit']:
            break
    log['recommendations'] = len(selected)
    subject = render(store.root, store.day, selected, log)
    write(store.root / 'reports' / store.day / 'selection.json', selected)
    write(store.root / 'reports' / store.day / 'review-pool.json', checked)
    for x in selected:
        record = store.data['repositories'][str(x['repository']['id'])]
        record.update(recommended_date=store.day, ever_recommended=True)
    log.update(prepared=True, subject=subject)
    log.pop('verified_items', None)
    store.save()


def main():
    parser = argparse.ArgumentParser(description='Zero-model daily GitHub discovery')
    parser.add_argument('command', nargs='?', choices=['run', 'prepare', 'deliver', 'summary'], default='run')
    args = parser.parse_args()
    start = time.monotonic()
    with lock(ROOT):
        config = configuration(ROOT)
        store = Store()
        try:
            if args.command in ('run', 'prepare'):
                prepare(store, config)
            if args.command in ('run', 'deliver'):
                if os.getenv('GITHUB_ACTIONS') == 'true':
                    # Revalidate cost gate even when resuming an existing outbox.
                    cloud_check(GitHub(store, config))
                result = deliver(store, config)
                print('Email result:', result)
                if result.startswith('blocked') or result in ('rejected_after_data', 'not_configured'):
                    if os.getenv('GITHUB_ACTIONS') == 'true':
                        raise RuntimeError('delivery_needs_attention')
            print(json.dumps({k: v for k, v in store.log.items() if k not in ('api_events', 'verified_items')}, ensure_ascii=False, indent=2))
        except Exception as e:
            store.stop('run_error_' + type(e).__name__)
            print('Run stopped:', type(e).__name__, '(see reports/date/usage.json; sensitive server messages suppressed)')
            return 1
        finally:
            store.log['program_seconds'] += round(time.monotonic() - start, 3)
            store.save()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
