"""Allowlisted queue diagnostics: YouTube handles only, never raw operation logs."""
from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
import hmac
import json
import secrets
import time
import re
import unicodedata

from app.services.participation_history import current_session_counts

_event = ContextVar('queue_audit_event', default=None)
ACTIONS = {'state_update', 'application_start', 'manual_change', 'manual_add', 'manual_remove',
           'manual_reorder', 'manual_move', 'manual_tail', 'name_edit', 'count_correct',
           'match_complete', 'reception_toggle', 'priority_toggle', 'history_reset',
           'undo', 'backup_restore', 'all_reset', 'stream_new', 'stream_resume',
           'comment_join', 'comment_cancel', 'comment_duplicate', 'comment_rejected'}
REASONS = {'none', 'priority_insert', 'fifo_join', 'fill_now', 'rejoin_tail', 'cancelled',
           'ignored_now', 'closed', 'cooldown', 'name_limit', 'not_found', 'duplicate',
           'unselected', 'history', 'invalid_timestamp', 'final_group_fill'}


@contextmanager
def audit_event(action, actor=None, handle=None):
    meta = {'action': action if action in ACTIONS else 'state_update', 'actor': actor, 'handle': handle, 'reason': 'none'}
    token = _event.set(meta)
    try:
        yield meta
    finally:
        _event.reset(token)


def audit_reason(reason):
    meta = _event.get()
    if meta is not None:
        meta['reason'] = reason if reason in REASONS else 'none'


class QueueAudit:
    MAX_EVENTS = 3000
    MAX_BYTES = 6 * 1024 * 1024
    MAX_USERS = 1000

    @staticmethod
    def handle(value):
        if (isinstance(value, str) and 2 <= len(value) <= 200 and value.startswith('@')
                and not any(c.isspace() or c in '@:/?#&=\\<>"\'' or unicodedata.category(c) in {'Cc','Cf','Cs'} for c in value[1:])):
            return value
        return None

    @staticmethod
    def initialize(conn):
        conn.execute('CREATE TABLE IF NOT EXISTS queue_audit_streams (video TEXT PRIMARY KEY, salt TEXT NOT NULL, aliases TEXT NOT NULL, sequence INTEGER NOT NULL, omitted INTEGER NOT NULL, touched INTEGER NOT NULL, started INTEGER NOT NULL DEFAULT 0)')
        if 'started' not in {r[1] for r in conn.execute('PRAGMA table_info(queue_audit_streams)')}:
            conn.execute('ALTER TABLE queue_audit_streams ADD COLUMN started INTEGER NOT NULL DEFAULT 0')
        conn.execute('CREATE TABLE IF NOT EXISTS queue_audit_events (id INTEGER PRIMARY KEY AUTOINCREMENT, video TEXT NOT NULL, body TEXT NOT NULL, bytes INTEGER NOT NULL)')

    @staticmethod
    def adopt(conn, video):
        if not conn.execute('SELECT 1 FROM queue_audit_streams WHERE video=?', (video,)).fetchone():
            conn.execute('UPDATE queue_audit_streams SET video=? WHERE video=?', (video, ''))
            conn.execute('UPDATE queue_audit_events SET video=? WHERE video=?', (video, ''))

    def record(self, conn, before, after, revision, *, force=False):
        row = conn.execute('SELECT video_id FROM onecomme_active WHERE id=1').fetchone()
        video = row[0] if row else ''
        stream = conn.execute('SELECT * FROM queue_audit_streams WHERE video=?', (video,)).fetchone()
        salt = stream['salt'] if stream else secrets.token_hex(32)
        aliases = json.loads(stream['aliases']) if stream else {}

        def alias(uid):
            digest = hmac.new(bytes.fromhex(salt), str(uid).encode('utf-8'), hashlib.sha256).hexdigest()
            if digest not in aliases and len(aliases) < 20000:
                aliases[digest] = 'P' + str(len(aliases) + 1).zfill(3)
            return aliases.get(digest, 'P-' + digest[:16])

        def number(value):
            return value if type(value) is int and 0 <= value <= 2147483647 else 0

        def projection(state):
            counts = current_session_counts(state)
            users = state.get('current', []) + state.get('waiting', [])
            visible = users[:self.MAX_USERS]
            current = [alias(u['user_id']) for u in state.get('current', [])[:3]]
            waiting = [alias(u['user_id']) for u in state.get('waiting', [])[:self.MAX_USERS - len(current)]]
            appearance = state.get('overlay_settings', {})
            empty = 'EMPTY_OPEN' if state.get('is_open') else 'EMPTY_CLOSED'
            shown = bool(appearance.get('show_participation_number'))
            def obs(items):
                return [p + (f' *{number(counts.get(u["user_id"], 0)) + 1}' if shown else '')
                        for p, u in items]
            pairs = [(alias(u['user_id']), u) for u in visible]
            return {'NOW': current, 'WAITING': waiting, 'NEXT': waiting[:3], 'QUEUE': waiting[3:],
                    'handles': {alias(u['user_id']): self.handle(u.get('youtube_handle')) for u in visible},
                    'this_stream_completed': {alias(u['user_id']): number(counts.get(u['user_id'], 0)) for u in visible},
                    'lifetime_completed': {alias(u['user_id']): max(number(state.get('participation_counts', {}).get(u['user_id'], 0)), number(u.get('participation_count', 0))) for u in visible},
                    'waiting_count': len(state.get('waiting', [])), 'omitted_participants': max(0, len(users) - self.MAX_USERS),
                    'reception_open': bool(state.get('is_open')), 'priority_enabled': bool(state.get('priority_mode')),
                    'completed_groups': number(state.get('total_match_count', 0)),
                    'OBS_NOW': obs(pairs[:len(current)]) + [empty] * (3 - len(current)),
                    'OBS_NEXT': obs(pairs[len(current):len(current) + 3]) + [empty] * max(0, 3 - len(waiting)),
                    'OBS_count_enabled': shown, 'OBS_layout': appearance.get('layout') if appearance.get('layout') in {'vertical', 'horizontal', 'custom'} else 'vertical',
                    'OBS_font_size': number(appearance.get('font_size', 28)),
                    'OBS_size': [number(appearance.get('width', 480)), number(appearance.get('height', 600))],
                    'OBS_template_tokens': {key: re.findall(r'\[(?:受付|NOW見出し|NOW[123]|NEXT見出し|NEXT[123]|QUEUE見出し|待機人数|待機人数のみ|待機グループ)\]', str(appearance.get(key, '')))[:100]
                                            for key in ('vertical_text', 'horizontal_now_text', 'horizontal_next_text', 'horizontal_queue_text', 'custom_text')},
                    'OBS_name_mode': appearance.get('name_mode') if appearance.get('name_mode') in {'youtube','declared','youtube_declared','declared_youtube'} else 'youtube'}

        meta = _event.get()
        old, new = projection(before), projection(after)
        totals_before, totals_after = before.get('participation_counts', {}), after.get('participation_counts', {})
        changed = sum(totals_before.get(k, 0) != totals_after.get(k, 0) for k in totals_before.keys() | totals_after.keys())
        if not force and old == new and not meta and not changed:
            return
        sequence = (stream['sequence'] if stream else 0) + 1
        now = time.time_ns()
        started = stream['started'] if stream and stream['started'] else now
        body = {'sequence': sequence, 'revision': revision, 'elapsed_seconds': round(max(0, now - started) / 1e9, 3),
                'action': meta['action'] if meta else 'state_update',
                'reason': meta['reason'] if meta else 'none',
                'actor': alias(meta['actor']) if meta and meta.get('actor') else None,
                'actor_handle': self.handle(meta.get('handle')) if meta else None,
                'cumulative_records_changed': changed,
                'before': old, 'after': new}
        display = conn.execute('SELECT value FROM control_display WHERE id=1').fetchone()
        fields = json.loads(display[0]) if display else {}
        body['CONTROL_FIELDS'] = {k: fields.get(k, True) is True for k in ('avatar','username','alias','memo','count','order')}
        encoded = json.dumps(body, ensure_ascii=False, separators=(',', ':'))
        size = len(encoded.encode('utf-8'))
        conn.execute('INSERT OR REPLACE INTO queue_audit_streams VALUES(?,?,?,?,?,?,?)',
                     (video, salt, json.dumps(aliases), sequence, stream['omitted'] if stream else 0, now, started))
        conn.execute('INSERT INTO queue_audit_events(video,body,bytes) VALUES(?,?,?)', (video, encoded, size))
        # Bound local storage, and tell the exported report when earlier events expired.
        rows = conn.execute('SELECT id,bytes FROM queue_audit_events WHERE video=? ORDER BY id DESC', (video,)).fetchall()
        retained, total = [], 0
        for item in rows:
            if retained and (len(retained) >= self.MAX_EVENTS or total + item['bytes'] > self.MAX_BYTES):
                break
            retained.append(item['id'])
            total += item['bytes']
        if retained and len(retained) < len(rows):
            conn.execute('DELETE FROM queue_audit_events WHERE video=? AND id<?', (video, retained[-1]))
            conn.execute('UPDATE queue_audit_streams SET omitted=omitted+? WHERE video=?', (len(rows) - len(retained), video))
        for stale in conn.execute('SELECT video FROM queue_audit_streams ORDER BY touched DESC LIMIT -1 OFFSET 2').fetchall():
            conn.execute('DELETE FROM queue_audit_events WHERE video=?', (stale['video'],))
            conn.execute('DELETE FROM queue_audit_streams WHERE video=?', (stale['video'],))

    @staticmethod
    def export(conn):
        lines = ['JoinQueue 操作ログ（YouTubeハンドルのみ） / format=1 / app=0.1.7',
                 '識別情報は@ハンドルのみ。表示名・申告名・ユーザーID・チャンネル/配信ID・URL・メモ・コメント本文・認証情報・実日時は出力しません。',
                 'P番号は配信ごとに別の仮番号です。handlesで@ハンドルと対応します。ハンドル未取得の場合は仮番号のみ。アーカイブとの照合用であり完全匿名ではありません。',
                 'priority: 今回の対戦済み回数のみ比較、同回数は先着順、NOW/NEXTを優先挿入で追い越さない。',
                 'rejoin_tail: 同じ人の参加希望を再受信すると最後尾へ。match_completeだけが対戦完了による回数加算。',
                 'this_stream_completedは今回の対戦済み回数、lifetime_completedは累計（優先判定には使用しない）。OBSの*n回目は今回の対戦済み+1。表示はハンドル対応の出力データで、実描画の証明ではありません。',
                 '更新前の操作は復元できません。各行は操作前後の完全な列（上限1000人）です。omitted=削除された古いイベント数。',
                 'elapsed_seconds=この配信のログ記録開始からの経過秒（配信開始時刻とは一致しない場合があります）。CONTROL_FIELDSは管理画面の表示項目。',
                 'action: manual_*=管理者操作、comment_*=参加/辞退、history_reset=今回のみ0、stream_new=新配信、stream_resume=保存済み配信へ復帰、undo=取消。']
        row = conn.execute('SELECT video_id FROM onecomme_active WHERE id=1').fetchone()
        active = row[0] if row else ''
        streams = conn.execute('SELECT video,omitted FROM queue_audit_streams ORDER BY (video=?) DESC,touched DESC LIMIT 2', (active,)).fetchall()
        for i, stream in enumerate(streams):
            lines.append(f'\n--- {"現在" if i == 0 else "前回"}の配信 / omitted={stream["omitted"]} ---')
            lines.extend(r['body'] for r in conn.execute('SELECT body FROM queue_audit_events WHERE video=? ORDER BY id', (stream['video'],)))
        return '\n'.join(lines) + '\n'
