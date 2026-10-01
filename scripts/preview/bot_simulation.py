"""Explicitly opt-in, memory-only UI simulation. No HTTP client, tokens or sender."""
from app.services.bot import BotSettings, BOT_ID


class PreviewBot:
    def __init__(self, bridge):
        self.bridge = bridge
        self.settings = BotSettings()
        self.requested = self.approved = self.authenticated = self.moderator = False
        self.running = False
        self.video = self.checked = ''
        self.error = ''

    def pause(self):
        self.running = False
        self.checked = ''
        self.settings = self.settings.model_copy(update={'enabled': False})

    stop = pause

    def status(self):
        if self.running and (not self.bridge.snapshot()['connected'] or self.bridge.snapshot()['selected'] != self.video):
            self.pause()
        return dict(settings=self.settings.model_dump(), account={'id': BOT_ID, 'name': 'JoinQueueBot（シミュレーション）'},
                    test_available=False, authenticated=self.authenticated, ready=self.running,
                    channel_id='UC' + '9'*22 if self.authenticated else None,
                    error=self.error, last_result='', pending=0,
                    authorization_url=None, confirmation='1234abcd' if self.requested and not self.authenticated else None,
                    has_connection_key=self.requested, login_pending=self.requested and not self.authenticated,
                    next_announcement_seconds=self.settings.initial_delay_minutes*60 if self.running and self.settings.periodic else None)

    def command(self, action):
        self.error = ''
        if action == 'stop':
            self.pause()
        elif action == 'connect':
            self.requested = True
        elif action == 'status':
            self.authenticated = self.approved
        elif action in ('check', 'start'):
            if not self.authenticated:
                raise ValueError('配信チャンネルの認証を完了してください。')
            if not self.moderator:
                raise ValueError('@JoinQueueBotの標準モデレーター登録を確認してください。')
            stream = self.bridge.snapshot()
            selected = next((s for s in stream['services'] if s['id'] == stream['selected']), {})
            if not stream['connected'] or not stream['selected'] or selected.get('state') != 'live':
                raise ValueError('配信開始前です。わんコメで配信中の対象に接続してから再確認してください。')
            self.checked = stream['selected']
            if action == 'start':
                self.running, self.video = True, self.checked
                self.settings = self.settings.model_copy(update={'enabled': True})
        else:
            raise ValueError('シミュレーションでは実チャットへの投稿を実行しません。')
        return self.status()

    def configure(self, settings):
        if not self.authenticated:
            raise ValueError('配信チャンネルの認証を完了してください。')
        if settings.enabled and not self.running:
            raise ValueError('接続確認後に起動してください。')
        self.settings = settings
        if not settings.enabled:
            self.pause()
        return self.status()

    def disconnect(self):
        self.pause()
        self.requested = self.approved = self.authenticated = False
        return self.status()

    def receive(self, comment):
        return False

    def is_self(self, comment):
        return False

    def announce(self):
        pass
