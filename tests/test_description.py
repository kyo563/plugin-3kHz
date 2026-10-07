from fastapi.testclient import TestClient
from app.main import create_app
from app.schemas.description import DEFAULT_DESCRIPTION
from app.schemas.description import (ONECOMME_DEFAULT_DESCRIPTION, LEGACY_DEFAULT_DESCRIPTION,
                                    LEGACY_ONECOMME_DEFAULT_DESCRIPTION)
from app.services.application_services import ApplicationServices


def test_description_save_restart_backup_and_reset(tmp_path):
    path = str(tmp_path / 'app.db')
    with TestClient(create_app(db_path=path, desktop=True), base_url='http://127.0.0.1') as c:
        c.headers['Authorization'] = 'Bearer ' + c.app.state.access_keys.admin
        assert c.get('/api/settings/description').json() == {'text': DEFAULT_DESCRIPTION}
        text = '編集した概要欄\n\n参加希望 『Alice』\n<script>文字として保持</script>'
        assert c.post('/api/settings/description', json={'text': text}).json() == {'text': text}
        assert c.get('/api/control/backup').json()['state']['description_text'] == text
        restarted = ApplicationServices(db_path=path, desktop=True)
        assert restarted.persistence_service.get_state()['description_text'] == text
        c.post('/api/control/reset')
        assert c.get('/api/settings/description').json()['text'] == text
        ingest = {'Authorization': 'Bearer ' + c.app.state.access_keys.ingest}
        assert c.post('/api/settings/description',json={'text':'wrong'},headers=ingest).status_code == 401
        assert c.post('/api/settings/description',json={'text':'x'*10001}).status_code == 422
        assert c.get('/api/settings/description').json()['text'] == text
        assert c.post('/api/settings/description',json={'text':''}).json() == {'text':''}
        assert 'description_text' not in c.get('/api/overlay-state').json()


def test_onecomme_default_contains_requested_participation_and_bot_guidance(tmp_path):
    text = ONECOMME_DEFAULT_DESCRIPTION
    assert text.startswith(DEFAULT_DESCRIPTION + '\n\n参加回数が少ない方を優先させる場合があります。')
    assert '【Botの使い方】' in text
    assert '待機順を確認する場合は、@JoinQueueBotへリプライしてください。' in text
    assert text.endswith('【Botの使い方】\n待機順を確認する場合は、@JoinQueueBotへリプライしてください。\n※Botが稼働している場合に利用できます。')
    for removed in ('特定の質問文言は不要です。', '対戦中の場合は「現在参加中です」とお知らせします。', '同じ方への回答は3分に1回です。'):
        assert removed not in text
    path = str(tmp_path / 'onecomme.db')
    for restarted in (False, True):
        with TestClient(create_app(db_path=path, desktop=True, onecomme=True), base_url='http://127.0.0.1') as c:
            c.headers['Authorization'] = 'Bearer ' + c.app.state.access_keys.admin
            assert c.get('/api/settings/description').json() == {'text': text}
            assert c.get('/api/control/backup').json()['state']['description_text'] == text


def test_onecomme_migrates_exact_old_defaults_but_preserves_custom_text(tmp_path):
    path = str(tmp_path / 'legacy-onecomme.db')
    services = ApplicationServices(db_path=path, desktop=True, onecomme=True)
    for text in (LEGACY_DEFAULT_DESCRIPTION, DEFAULT_DESCRIPTION, LEGACY_ONECOMME_DEFAULT_DESCRIPTION):
        services.persistence_service.mutate_state(lambda s: s.update(description_text=text))
        assert ApplicationServices(db_path=path, desktop=True, onecomme=True).persistence_service.get_state()['description_text'] == ONECOMME_DEFAULT_DESCRIPTION
    for custom in ('', DEFAULT_DESCRIPTION + '\n独自の案内', LEGACY_ONECOMME_DEFAULT_DESCRIPTION + '\n独自の案内'):
        services.persistence_service.mutate_state(lambda s: s.update(description_text=custom))
        assert ApplicationServices(db_path=path, desktop=True, onecomme=True).persistence_service.get_state()['description_text'] == custom


def test_shorter_onecomme_default_does_not_migrate_standalone_custom_description(tmp_path):
    path = str(tmp_path / 'standalone.db')
    services = ApplicationServices(db_path=path, desktop=True)
    services.persistence_service.mutate_state(lambda s: s.update(description_text=LEGACY_ONECOMME_DEFAULT_DESCRIPTION))
    assert ApplicationServices(db_path=path, desktop=True).persistence_service.get_state()['description_text'] == LEGACY_ONECOMME_DEFAULT_DESCRIPTION


def test_legacy_default_updates_but_custom_text_is_preserved(tmp_path):
    from app.schemas.description import LEGACY_DEFAULT_DESCRIPTION

    path = str(tmp_path / 'legacy.db')
    services = ApplicationServices(db_path=path, desktop=True)
    services.persistence_service.mutate_state(lambda s: s.update(description_text=LEGACY_DEFAULT_DESCRIPTION))
    restarted = ApplicationServices(db_path=path, desktop=True)
    assert restarted.persistence_service.get_state()['description_text'] == DEFAULT_DESCRIPTION
    custom = LEGACY_DEFAULT_DESCRIPTION + '\n独自の案内'
    restarted.persistence_service.mutate_state(lambda s: s.update(description_text=custom))
    assert ApplicationServices(db_path=path, desktop=True).persistence_service.get_state()['description_text'] == custom
