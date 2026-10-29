import json
import os
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler


class StopCollection(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # No uncounted requests or authorization forwarded to another host.


class GitHub:
    def __init__(self, store, config):
        self.store, self.config = store, config
        self.open = build_opener(NoRedirect()).open
        self.remaining = {}

    def get(self, path, raw=False, missing=None):
        if not path.startswith('/') or '..' in path.split('?')[0] or '://' in path:
            raise ValueError('invalid_github_path')
        bucket = 'search' if path.startswith('/search/') else 'core'
        if self.remaining.get(bucket, 99) <= 1:
            raise StopCollection('github_rate_limit_reserve')
        headers = {'User-Agent': 'GitHub-Hidden-Gems-Daily/1.0',
                   'Accept': 'application/vnd.github.raw+json' if raw else 'application/vnd.github+json',
                   'X-GitHub-Api-Version': '2022-11-28'}
        token = os.getenv('GITHUB_TOKEN') or os.getenv('GH_TOKEN')
        if token:
            headers['Authorization'] = 'Bearer ' + token
        for attempt in range(2):
            if self.store.log['github_api_requests'] >= self.config['api_requests_per_day']:
                self.store.log['over_budget'] = True
                raise StopCollection('daily_api_budget_reached')
            self.store.log['github_api_requests'] += 1
            event = {'path': path, 'status': 'reserved'}
            self.store.log['api_events'].append(event)
            self.store.save()  # Reservation survives process failure.
            try:
                with self.open(Request('https://api.github.com' + path, headers=headers), timeout=20) as r:
                    self.remaining[bucket] = int(r.headers.get('X-RateLimit-Remaining', '99'))
                    event['status'] = r.status
                    event['remaining'] = self.remaining[bucket]
                    cap = self.config['readme_bytes'] if raw else 900000
                    body = r.read(cap + 1)
                    event['truncated'] = len(body) > cap
                    self.store.save()
                    return body[:cap].decode('utf-8', errors='replace') if raw else json.loads(body)
            except HTTPError as e:
                event['status'] = e.code
                self.store.save()
                if e.code == 404:
                    return missing
                if e.code in (403, 429):
                    raise StopCollection('github_rate_limited_no_retry')
                if e.code < 500:
                    raise StopCollection('github_http_' + str(e.code))
            except (URLError, TimeoutError, OSError):
                event['status'] = 'network_error'
                self.store.save()
            if attempt or self.store.log['retry_used'] or self.config['max_retries_per_day'] == 0:
                raise StopCollection('github_request_failed_retry_exhausted')
            self.store.log['retry_used'] = True
            self.store.save()
            time.sleep(2)

    def search(self, query, count=12, sort='updated'):
        result = self.get('/search/repositories?' + urlencode({
            'q': query, 'per_page': count, 'sort': sort, 'order': 'desc'}))
        if result.get('incomplete_results'):
            self.store.stop('search_incomplete_results_partial_only')
        return result.get('items', [])
