import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from gems.github import GitHub, StopCollection
from gems.main import configuration, prepare, seen
from gems.mailer import deliver
from gems.render import render
from gems.scoring import assess
from gems.storage import ROOT, Store

DAY = '2026-10-29'
REPO = {'id': 1, 'full_name': 'test/photo', 'name': 'photo', 'html_url': 'https://github.com/test/photo',
        'description': 'A photo manager for your desktop', 'topics': ['photo-management'],
        'license': {'spdx_id': 'MIT'}, 'stargazers_count': 160, 'pushed_at': DAY + 'T00:00:00Z',
        'fork': False, 'archived': False}
README = '# Photo manager\n## Installation\nWindows macOS Linux\n![Screenshot](demo.png)\nDownload from Releases.'
RELEASE = {'tag_name': 'v1.0', 'html_url': 'https://github.com/test/photo/releases/v1.0', 'published_at': DAY,
           'assets': [{'name': 'photo.dmg', 'browser_download_url': 'https://github.com/test/photo/releases/download/v1.0/photo.dmg'}]}


class SMTP:
    def __init__(self, disconnect=False):
        self.data_calls = 0
        self.disconnect = disconnect
    def login(self, *a): pass
    def mail(self, *a): return 250, b'ok'
    def rcpt(self, *a): return 250, b'ok'
    def data(self, *a):
        self.data_calls += 1
        self.wire_bytes = a[0]
        if self.disconnect: raise OSError('connection lost after DATA')
        return 250, b'accepted'
    def close(self): pass


class Safety(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / 'config.json').write_text((ROOT / 'config.json').read_text())
        (self.root / 'templates').mkdir()
        (self.root / 'templates/email.html').write_text((ROOT / 'templates/email.html').read_text())
        self.store = Store(self.root, DAY)
        self.c = configuration(self.root)

    def tearDown(self): self.tmp.cleanup()

    def outbox(self):
        item = {'repository': copy.deepcopy(REPO), 'assessment': assess(REPO, README, RELEASE, DAY), 'release': RELEASE}
        self.store.log.update(prepared=True, subject=render(self.root, DAY, [item], self.store.log))
        self.store.save()

    def test_api_hard_cap_survives_new_process(self):
        self.store.log['github_api_requests'] = 50
        self.store.save()
        api = GitHub(Store(self.root, DAY), self.c)
        with self.assertRaises(StopCollection), patch.object(api, 'open') as network:
            api.get('/rate_limit')
        network.assert_not_called()

    def test_one_global_retry_including_network_failures(self):
        api = GitHub(self.store, self.c)
        with patch.object(api, 'open', side_effect=URLError('offline')) as network, patch('time.sleep'):
            with self.assertRaises(StopCollection): api.get('/rate_limit')
            self.assertEqual(network.call_count, 2)
            with self.assertRaises(StopCollection): api.get('/rate_limit')
            self.assertEqual(network.call_count, 3)
        self.assertTrue(self.store.log['retry_used'])
        self.assertEqual(self.store.log['github_api_requests'], 3)

    def test_rate_limit_does_not_retry(self):
        api = GitHub(self.store, self.c)
        with patch.object(api, 'open', side_effect=HTTPError('url', 429, '', {}, None)) as network:
            with self.assertRaises(StopCollection): api.get('/rate_limit')
            self.assertEqual(network.call_count, 1)

    def test_query_allows_star_range(self):
        api = GitHub(self.store, self.c)
        with patch.object(api, 'open', side_effect=HTTPError('url', 404, '', {}, None)):
            self.assertIsNone(api.get('/search/repositories?q=stars%3A20..5000'))
        with self.assertRaises(ValueError): api.get('/repos/../../secret')

    def test_llm_setting_fails_closed(self):
        with patch.dict(os.environ, {'AI_EDITOR_ENABLED': 'true'}):
            with self.assertRaises(ValueError): configuration(self.root)
        self.assertEqual(self.store.log['llm_calls'], 0)

    def test_fork_rename_and_ninety_day_dedup(self):
        self.store.data['repositories']['1'] = {'recommended_date': '2026-10-01', 'aliases': ['old/name'], 'category': '照片管理'}
        renamed = dict(REPO, full_name='new/name')
        self.assertTrue(seen(self.store, renamed, self.c))
        self.assertTrue(seen(self.store, dict(REPO, id=2, fork=True), self.c))
        self.store.data['repositories']['1']['recommended_date'] = '2026-07-01'
        self.assertFalse(seen(self.store, renamed, self.c))

    def test_similar_category_suppressed_for_week(self):
        self.store.data['repositories']['2'] = {'recommended_date': DAY, 'aliases': [], 'category': '照片管理'}
        self.assertTrue(seen(self.store, REPO, self.c))

    def test_unverified_cost_risk_and_license_go_to_review(self):
        self.assertTrue(assess(REPO, README, RELEASE, DAY)['accepted'])
        self.assertFalse(assess(REPO, README + '\nRequires API key and billing.', RELEASE, DAY)['accepted'])
        self.assertFalse(assess(dict(REPO, license=None), README, RELEASE, DAY)['accepted'])
        self.assertFalse(assess(REPO, README + '\ncurl https://x/install | bash', RELEASE, DAY)['accepted'])
        self.assertFalse(assess(REPO, README, None, DAY)['accepted'])
        self.assertEqual(assess(REPO, README, RELEASE, DAY)['pending_points'], 36)

    def test_html_escapes_upstream_text(self):
        item = {'repository': dict(REPO, description='<script>alert(1)</script>'), 'assessment': assess(REPO, README, RELEASE, DAY), 'release': RELEASE}
        render(self.root, DAY, [item], self.store.log)
        text = (self.root / 'reports' / DAY / 'daily.html').read_text()
        self.assertNotIn('<script>', text)
        self.assertIn('&lt;script&gt;', text)

    @patch.dict(os.environ, {'SMTP_USER': 'private@example.com', 'SMTP_PASSWORD': 'never-log-this', 'MAIL_TO': 'reader@example.com', 'SMTP_FREE_CONFIRMED': 'true'})
    def test_accepted_email_never_repeats(self):
        self.outbox()
        client = SMTP()
        self.assertEqual(deliver(self.store, self.c, checkpoint=self.store.save, smtp_factory=lambda: client), 'accepted')
        fresh = Store(self.root, DAY)
        self.assertEqual(deliver(fresh, self.c, smtp_factory=lambda: client), 'blocked_duplicate_or_uncertain')
        self.assertEqual(client.data_calls, 1)
        self.assertIn(b'\r\n', client.wire_bytes)
        self.assertNotIn(b'\n', client.wire_bytes.replace(b'\r\n', b''))
        saved = self.store.path.read_text()
        self.assertNotIn('private@example.com', saved)
        self.assertNotIn('never-log-this', saved)

    @patch.dict(os.environ, {'SMTP_USER': 'a@example.com', 'SMTP_PASSWORD': 'secret', 'MAIL_TO': 'b@example.com', 'SMTP_FREE_CONFIRMED': 'true'})
    def test_ambiguous_data_never_retries(self):
        self.outbox()
        client = SMTP(disconnect=True)
        with self.assertRaises(RuntimeError): deliver(self.store, self.c, checkpoint=self.store.save, smtp_factory=lambda: client)
        self.assertEqual(self.store.log['email_result'], 'unknown')
        self.assertEqual(deliver(Store(self.root, DAY), self.c, smtp_factory=lambda: client), 'blocked_duplicate_or_uncertain')
        self.assertEqual(client.data_calls, 1)

    @patch.dict(os.environ, {'SMTP_USER': 'a@example.com', 'SMTP_PASSWORD': 'secret', 'MAIL_TO': 'b@example.com', 'SMTP_FREE_CONFIRMED': 'true'})
    def test_failed_remote_checkpoint_prevents_data(self):
        self.outbox()
        client = SMTP()
        with self.assertRaises(RuntimeError):
            deliver(self.store, self.c, checkpoint=lambda: (_ for _ in ()).throw(OSError('push failed')), smtp_factory=lambda: client)
        self.assertEqual(client.data_calls, 0)

    def test_same_day_prepare_reuses_frozen_outbox(self):
        self.outbox()
        with patch.object(GitHub, 'get', side_effect=AssertionError('no network')):
            prepare(self.store, self.c)

    def test_cloud_private_repo_blocked(self):
        from gems.main import cloud_check
        api = GitHub(self.store, self.c)
        with patch.dict(os.environ, {'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': 'a/b', 'RUNNER_OS': 'Linux'}):
            with patch.object(api, 'get', return_value={'visibility': 'private'}):
                with self.assertRaises(StopCollection): cloud_check(api)

    @patch.dict(os.environ, {'SMTP_USER': 'a@example.com', 'SMTP_PASSWORD': 'secret', 'MAIL_TO': 'b@example.com', 'SMTP_FREE_CONFIRMED': 'true'})
    def test_connection_failure_reports_stage_without_secret(self):
        import smtplib
        self.outbox()
        with self.assertRaises(RuntimeError):
            deliver(self.store, self.c, checkpoint=self.store.save, smtp_factory=lambda: (_ for _ in ()).throw(smtplib.SMTPServerDisconnected('private server text')))
        self.assertEqual(self.store.log['smtp_phase'], 'connect')
        self.assertEqual(self.store.log['smtp_error_type'], 'SMTPServerDisconnected')
        self.assertNotIn('private server text', self.store.path.read_text())


if __name__ == '__main__': unittest.main()
