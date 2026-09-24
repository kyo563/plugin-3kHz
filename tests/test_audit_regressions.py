from datetime import datetime, timezone

from app.schemas.comment import ReceivedComment
from app.schemas.backup import Backup
from app.services.application_services import ApplicationServices
from app.services.onecomme import OneCommeBridge
from app.services.operator_service import export_backup


def test_onecomme_quoted_name_lock_opaque_id_and_memo_roundtrip(tmp_path):
    path = str(tmp_path/'queue.db')
    services = ApplicationServices(db_path=path, desktop=True)
    bridge = OneCommeBridge(services)
    bridge.frames['abcdefghijk'] = 'Test'; bridge.select('abcdefghijk')
    services.persistence_service.mutate_state(lambda s: s.update(cooldown_seconds=0))
    serial = 0
    def receive(uid, text, memo=None, handle='@same'):
        nonlocal serial
        serial += 1
        return bridge.receive('abcdefghijk', 'Test', ReceivedComment(
            source='youtube', userKey=uid, displayName='YouTube Name', youtubeHandle=handle,
            message=text, oneCommeMemo=memo, externalMessageId=str(serial),
            receivedAt=datetime.now(timezone.utc).isoformat()))
    for i in range(3): receive('now'+str(i), '参加希望')
    receive('opaque-onecomme-id', '参加希望 名前拒否', '<b>PRIVATE MEMO</b>')
    user = services.build_view_state()['waiting'][0]
    identity = user['user_id']
    assert user['declared_player_name'] == 'YouTube Name'
    assert user['onecomme_memo'] == '<b>PRIVATE MEMO</b>'
    receive('opaque-onecomme-id', '参加希望『初登録』', handle='@changed')
    user = services.build_view_state()['waiting'][0]
    assert user['user_id'] == identity and user['declared_player_name'] == '初登録'
    assert user['onecomme_memo'] == '<b>PRIVATE MEMO</b>'
    receive('opaque-onecomme-id', '参加希望『上書き不可』')
    assert services.build_view_state()['waiting'][0]['declared_player_name'] == '初登録'
    receive('other-onecomme-id', '参加希望', handle='@same')
    assert len(services.build_view_state()['waiting']) == 2  # Same handle never merges identities.
    receive('opaque-onecomme-id', '普通のコメント', 'UPDATED PRIVATE')
    assert services.build_view_state()['waiting'][0]['onecomme_memo'] == 'UPDATED PRIVATE'
    assert 'PRIVATE' not in str(services.build_overlay_state())
    backup = export_backup(services)
    restored = Backup.model_validate_json(backup.model_dump_json())
    assert restored.state.waiting[0].onecomme_memo == 'UPDATED PRIVATE'
    restarted = ApplicationServices(db_path=path, desktop=True)
    assert restarted.build_view_state()['waiting'][0]['onecomme_memo'] == 'UPDATED PRIVATE'
    assert restarted.build_view_state()['waiting'][0]['declared_player_name'] == '初登録'
    receive('opaque-onecomme-id', '別のコメント', '')
    assert services.build_view_state()['waiting'][0]['onecomme_memo'] == ''


def test_legacy_backup_without_memo_remains_valid(tmp_path):
    services = ApplicationServices(db_path=str(tmp_path/'q.db'), desktop=True)
    data = export_backup(services).model_dump()
    for user in data['state']['current'] + data['state']['waiting']:
        user.pop('onecomme_memo', None)
    Backup.model_validate(data)
