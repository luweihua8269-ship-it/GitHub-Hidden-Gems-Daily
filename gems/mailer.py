import os
import smtplib
import ssl
from email.message import EmailMessage
from email.policy import SMTP as SMTP_POLICY


def deliver(store, config, checkpoint=None, smtp_factory=None):
    log = store.log
    if log['email_result'] in ('accepted', 'sending', 'unknown'):
        return 'blocked_duplicate_or_uncertain'
    if not log.get('prepared'):
        raise RuntimeError('prepare_report_first')
    required = ['SMTP_USER', 'SMTP_PASSWORD', 'MAIL_TO']
    if not all(os.getenv(k) for k in required):
        log['email_result'] = 'not_configured'
        store.save()
        return 'not_configured'
    # Provider policy must be confirmed by the operator. No claim of readable remaining quota.
    if os.getenv('SMTP_FREE_CONFIRMED') != 'true':
        store.stop('smtp_free_policy_not_confirmed')
        return 'blocked_provider_policy'
    if log['smtp_attempts'] >= 2 or (log['smtp_attempts'] and (log['retry_used'] or config['max_retries_per_day'] == 0)):
        return 'blocked_retry_limit'
    month_count = sum(x.get('smtp_data_attempts', 0) for d, x in store.data['days'].items() if d.startswith(store.day[:7]))
    if month_count >= config['smtp_monthly_cap'] or log.get('smtp_data_attempts', 0) >= config['smtp_messages_per_day']:
        store.stop('smtp_local_budget_reached')
        return 'blocked_smtp_budget'
    root = store.root / 'reports' / store.day
    msg = EmailMessage()
    msg['Subject'] = log['subject']
    msg['From'], msg['To'] = os.environ['SMTP_USER'], os.environ['MAIL_TO']
    msg['Message-ID'] = '<hidden-gems-' + store.day + '@daily.local>'
    msg.set_content((root / 'daily.md').read_text())
    msg.add_alternative((root / 'daily.html').read_text(), subtype='html')
    if log['smtp_attempts']:
        log['retry_used'] = True
    log['smtp_attempts'] += 1
    store.save()
    checkpoint = checkpoint or store.checkpoint
    host = os.getenv('SMTP_HOST', 'smtp.126.com')
    port = int(os.getenv('SMTP_PORT', '465'))
    if port not in (465, 587):
        raise ValueError('only_tls_smtp_465_or_587_supported')
    client = None
    data_started = False
    try:
        log['smtp_phase'] = 'connect'
        if smtp_factory:
            client = smtp_factory()
        elif port == 465:
            client = smtplib.SMTP_SSL(host, port, timeout=25, context=ssl.create_default_context())
        else:
            client = smtplib.SMTP(host, port, timeout=25)
            client.ehlo()
            client.starttls(context=ssl.create_default_context())
            client.ehlo()
        log['smtp_phase'] = 'authenticate'
        password = os.environ['SMTP_PASSWORD']
        if host == 'smtp.gmail.com':
            password = password.replace(' ', '')
        client.login(os.environ['SMTP_USER'], password)
        log['smtp_phase'] = 'sender'
        code, _ = client.mail(os.environ['SMTP_USER'])
        if code != 250:
            raise RuntimeError('smtp_sender_rejected')
        log['smtp_phase'] = 'recipient'
        code, _ = client.rcpt(os.environ['MAIL_TO'])
        if code not in (250, 251):
            raise RuntimeError('smtp_recipient_rejected')
        log['email_result'] = 'sending'
        log['smtp_data_attempts'] = log.get('smtp_data_attempts', 0) + 1
        log['smtp_phase'] = 'persist_intent'
        checkpoint()  # Commit+push intent, fail closed if remote state cannot be saved.
        data_started = True
        log['smtp_phase'] = 'data'
        code, _ = client.data(msg.as_bytes(policy=SMTP_POLICY))
        if code != 250:
            log['email_result'] = 'rejected_after_data'
        else:
            log['email_result'] = 'accepted'  # SMTP acceptance does not prove inbox arrival.
        log['smtp_phase'] = 'persist_result'
        checkpoint()
        log['smtp_phase'] = 'completed'
    except Exception as e:
        # No SMTP response body, addresses or credentials are written to logs.
        log['email_result'] = 'unknown' if data_started else 'failed_before_data'
        log['smtp_error_type'] = type(e).__name__
        if isinstance(e, smtplib.SMTPResponseException):
            log['smtp_error_code'] = e.smtp_code
        store.save()
        raise RuntimeError('smtp_' + log['email_result']) from None
    finally:
        if client:
            try:
                client.close()
            except Exception:
                pass
    return log['email_result']
