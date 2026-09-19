import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.services.application_services import ApplicationServices


def test_custom_commands_persist_receive_names_and_keep_now_protection(tmp_path):
    path = str(tmp_path / 'commands.db')
    with TestClient(create_app(db_path=path, desktop=True),base_url='http://127.0.0.1') as c:
        c.headers['Authorization']='Bearer '+c.app.state.access_keys.admin
        words={'join':['!JOIN','参加します'],'cancel':['!leave','抜けます']}
        assert c.post('/api/settings/commands',json=words).status_code==200
        c.post('/api/settings/comments',json={'cooldown_seconds':0})
        for i in range(3): c.post('/api/control/add-user',json={'user_id':str(i),'display_name':str(i)})
        def send(text):
            return c.post('/api/comments/receive',json={'source':'youtube','receivedAt':'2026-09-20T00:00:00Z','displayName':'Account','userKey':'alice','message':text})
        assert send('参加希望').json()['command']=='ignore'
        assert send('!JOIN 『Alice』').json()['command']=='join'
        state=c.get('/api/state').json()
        assert state['waiting'][0]['declared_player_name']=='Alice'
        assert send('抜けます').json()['command']=='cancel'
        assert c.get('/api/state').json()['waiting']==[]
        send('参加します 『Bob』')
        state=c.get('/api/state').json()
        assert state['waiting'][0]['declared_player_name']=='Alice'
        c.post('/api/control/remove-user',json={'user_id':'0'})
        send('!leave')
        assert any(u['display_name']=='Account' for u in c.get('/api/state').json()['current'])
        expected={'join':['!join','参加します'],'cancel':['!leave','抜けます']}
        assert c.get('/api/control/backup').json()['state']['command_settings']==expected
        assert ApplicationServices(db_path=path,desktop=True).persistence_service.get_state()['command_settings']==expected
        assert c.get('/api/settings/commands',headers={'Authorization':'Bearer '+c.app.state.access_keys.ingest}).status_code==401


@pytest.mark.parametrize('words', [
    {'join':[],'cancel':['辞退']}, {'join':[' '],'cancel':['辞退']},
    {'join':['x'*65],'cancel':['辞退']}, {'join':['join'],'cancel':['!JOIN']},
    {'join':['join']*21,'cancel':['辞退']}, {'join':['『name』'],'cancel':['辞退']},
])
def test_invalid_commands_leave_saved_settings_unchanged(tmp_path, words):
    with TestClient(create_app(db_path=str(tmp_path/'db'),desktop=True),base_url='http://127.0.0.1') as c:
        c.headers['Authorization']='Bearer '+c.app.state.access_keys.admin
        before=c.get('/api/settings/commands').json()
        assert c.post('/api/settings/commands',json=words).status_code==422
        assert c.get('/api/settings/commands').json()==before


def test_official_youtube_receiver_accepts_custom_join(tmp_path):
    import asyncio
    import httpx
    from app.services.youtube_chat import YouTubeChat
    services=ApplicationServices(db_path=str(tmp_path/'youtube.db'),desktop=True)
    services.persistence_service.mutate_state(lambda s:s.update(command_settings={'join':['!join'],'cancel':['!leave']}))
    item={'id':'custom', 'snippet':{'type':'textMessageEvent','publishedAt':'2026-09-20T00:00:00Z','textMessageDetails':{'messageText':'!join 『Alice』'}}, 'authorDetails':{'displayName':'Account','channelId':'UCexample'}}
    async def consume():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'items':[]}))) as client:
            await YouTubeChat(services)._consume(client,'key',item,{})
    asyncio.run(consume())
    assert services.build_view_state()['current'][0]['declared_player_name']=='Alice'


def test_custom_words_are_not_blocked_by_legacy_join_exclusions():
    from app.services.command_detector import CommandDetector
    detector=CommandDetector()
    assert detector.detect('参加希望者')=='ignore'
    assert detector.detect('参加希望者',{'join':['参加希望者'],'cancel':['辞退']})=='join'
