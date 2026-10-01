from copy import deepcopy
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.application_services import ApplicationServices
from app.services.onecomme import OneCommeBridge
from app.services.setup_preferences import SetupStore
from tests.test_onecomme_auto import frame


def make_bridge(path):
    return OneCommeBridge(ApplicationServices(db_path=str(path), desktop=True), SetupStore(str(path)))


def stream(video='abcdefghijk'):
    return {**frame(video), 'service_id': 'mahjong-row', 'service_name': '麻雀配信'}


def fill(p):
    def update(state):
        user = dict(user_id='viewer', display_name='Viewer', participation_count=4)
        state.update(current=[user], waiting=[{**user, 'user_id':'waiting'}],
                     name_overrides={'viewer':'申告名'}, comment_names={'viewer':'申告名'},
                     total_match_count=3, participation_counts={'viewer':4},
                     participation_history=[{'id':'first','label':'配信1','started_at':'now',
                                             'matches':3,'users':[{'user_id':'viewer','count':3}]}])
    p.mutate_state(update)


def test_remembers_row_and_archives_separate_video_state(tmp_path):
    b = make_bridge(tmp_path/'db')
    p = b.services.persistence_service
    b.heartbeat(services=[stream()])
    fill(p)
    original = p.get_state()
    b.bot = Mock()
    b.heartbeat(services=[stream('lmnopqrstuv')])
    assert not b.selected and b.pending['waiting_count'] == 1
    b.bot.pause.assert_called_once()
    b.confirm_transition('lmnopqrstuv', False, b.pending['revision'])
    state = p.get_state()
    assert state['current'] == state['waiting'] == state['participation_history'] == []
    assert state['total_match_count'] == 0
    for key in ('name_overrides','comment_names','command_settings','overlay_settings','participation_counts'):
        assert state[key] == original[key]
    assert not p.undo_available()
    b = make_bridge(tmp_path/'db')
    b.heartbeat(services=[stream('lmnopqrstuv'),frame('zyxwvutsrqp')])
    assert b.selected == 'lmnopqrstuv' and b.pending is None
    b.heartbeat(services=[stream()])  # Empty current session automatically restores old one.
    assert b.selected == 'abcdefghijk'
    restored = p.get_state()
    for key in ('current','waiting','participation_history','total_match_count'):
        if key in ('current','waiting'):
            assert [u['user_id'] for u in restored[key]] == [u['user_id'] for u in original[key]]
        else:
            assert restored[key] == original[key]


def test_pending_survives_restart_and_stale_confirmation_rejected(tmp_path):
    b = make_bridge(tmp_path/'db'); p = b.services.persistence_service
    b.heartbeat(services=[stream()]); fill(p)
    b.heartbeat(services=[stream('lmnopqrstuv')])
    b = make_bridge(tmp_path/'db'); p = b.services.persistence_service
    b.heartbeat(services=[stream('lmnopqrstuv')])
    revision = b.pending['revision']
    p.mutate_state(lambda s: s['logs'].append('別操作'))
    with pytest.raises(ValueError):
        b.confirm_transition('lmnopqrstuv', True, revision)
    b.heartbeat(services=[stream('lmnopqrstuv')])
    b.confirm_transition('lmnopqrstuv', True, b.pending['revision'])
    assert len(p.get_state()['current']) == len(p.get_state()['waiting']) == 1
    assert p.get_state()['participation_history'] == []
    assert p.get_state()['participation_counts']['viewer'] == 4
    b.heartbeat(services=[stream()])
    assert b.pending['saved']
    with pytest.raises(ValueError):
        b.confirm_transition('abcdefghijk', True, b.pending['revision'])
    b.confirm_transition('abcdefghijk', False, b.pending['revision'])
    assert p.get_state()['total_match_count'] == 3


def test_removed_row_never_selects_another_and_cancels_pending(tmp_path):
    b = make_bridge(tmp_path/'db')
    b.heartbeat(services=[stream()]); fill(b.services.persistence_service)
    b.heartbeat(services=[stream('lmnopqrstuv')]); revision=b.pending['revision']
    b.heartbeat(services=[frame('zyxwvutsrqp')])
    assert not b.selected and b.pending is None and b.selection_reason == 'missing'
    with pytest.raises(ValueError):
        b.confirm_transition('lmnopqrstuv', False, revision)
    b.remember('row-zyxwvutsrqp')
    assert b.pending['video_id'] == 'zyxwvutsrqp'
    b.select('')
    b.heartbeat(services=[frame('zyxwvutsrqp')])
    assert not b.selected and b.pending is None


def test_switch_is_atomic_if_sqlite_write_fails(tmp_path, monkeypatch):
    b=make_bridge(tmp_path/'db'); p=b.services.persistence_service
    b.heartbeat(services=[stream()]); fill(p)
    before=deepcopy(p.get_state()); revision=p.revision
    with p._connect() as conn:
        conn.execute("CREATE TRIGGER fail_switch BEFORE INSERT ON operation_logs BEGIN SELECT RAISE(ABORT, 'test'); END")
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        p.switch_video('lmnopqrstuv')
    assert p.get_state()==before and p.revision==revision
    assert p.active_video()=='abcdefghijk' and not p.has_saved_video('abcdefghijk')


def test_transition_endpoints_require_admin(tmp_path):
    with TestClient(create_app(db_path=str(tmp_path/'db'),desktop=True,onecomme=True),base_url='http://127.0.0.1') as c:
        for key in ('',c.app.state.access_keys.ingest):
            c.headers['Authorization']='Bearer '+key
            assert c.post('/api/onecomme/remember',json={'service_id':'mahjong-row'}).status_code==401
            assert c.post('/api/onecomme/transition',json={'video_id':'abcdefghijk','revision':0}).status_code==401
        c.headers['Authorization']='Bearer '+c.app.state.access_keys.admin
        assert c.post('/api/onecomme/transition',json={'video_id':'abcdefghijk','revision':0}).status_code==409
