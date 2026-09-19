from fastapi.testclient import TestClient
from app.main import create_app
from app.schemas.description import DEFAULT_DESCRIPTION
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
