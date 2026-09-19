import asyncio
import json
import httpx
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.services.application_services import ApplicationServices
from app.services.youtube_chat import YouTubeChat, video_id

KEY = "test_key_" + "x" * 30
VIDEO = "abcdefghijk"

@pytest.mark.parametrize("url", [VIDEO, "https://youtu.be/"+VIDEO+"?si=abc", "https://www.youtube.com/watch?v="+VIDEO, "https://youtube.com/live/"+VIDEO])
def test_video_urls(url):
    assert video_id(url) == VIDEO

@pytest.mark.parametrize("url", ["http://youtube.com/watch?v="+VIDEO, "https://youtube.com.evil.com/watch?v="+VIDEO, "https://youtube.com/@channel/live", "https://user@youtube.com/watch?v="+VIDEO, "https://localhost/"+VIDEO])
def test_reject_untrusted_urls(url):
    with pytest.raises(ValueError): video_id(url)

def message(mid, text, user="UCexample"):
    return {"id":mid, "snippet":{"type":"textMessageEvent", "publishedAt":"2026-09-20T00:00:00Z", "textMessageDetails":{"messageText":text}}, "authorDetails":{"displayName":"表示名", "channelId":user}}

def test_receive_history_join_duplicate_cancel_and_stop(tmp_path):
    async def scenario():
        services = ApplicationServices(db_path=str(tmp_path/'queue.db'), desktop=True)
        services.persistence_service.mutate_state(lambda s:s.update(cooldown_seconds=0))
        pages = [
            [message("old", "参加希望", "olduser")],
            [message("join", "参加希望 『Alice』"), message("join", "参加希望 『Alice』")],
            [message("cancel", "参加辞退")],
        ]
        requests = []
        phase = 0
        ready = asyncio.Event()
        resume = asyncio.Event()
        async def handler(request):
            requests.append(request)
            assert KEY not in str(request.url)
            assert request.headers['X-Goog-Api-Key'] == KEY
            if request.url.path.endswith('/videos'):
                return httpx.Response(200,json={"items":[{"liveStreamingDetails":{"activeLiveChatId":"live"}}]})
            if request.url.path.endswith('/channels'):
                return httpx.Response(200,json={"items":[{"snippet":{"customUrl":"@actual"}}]})
            return httpx.Response(200,json={"items":pages.pop(0),"nextPageToken":str(len(pages)),"pollingIntervalMillis":12000})
        async def sleep(delay):
            nonlocal phase
            assert delay >= 12
            phase += 1
            ready.set()
            await resume.wait()
            resume.clear(); ready.clear()
        chat=YouTubeChat(services,lambda:httpx.AsyncClient(transport=httpx.MockTransport(handler)),sleep)
        await chat.start(VIDEO,KEY)
        await ready.wait()
        assert services.build_view_state()['current'] == []
        resume.set()
        while phase < 2: await asyncio.sleep(.001)
        current=services.build_view_state()['current']
        assert len(current)==1
        assert current[0]['declared_player_name']=='Alice'
        assert current[0]['youtube_handle']=='@actual'
        assert chat.snapshot()['commands']==1
        resume.set()
        while phase < 3: await asyncio.sleep(.001)
        assert services.build_view_state()['current']==current
        assert chat.snapshot()['commands']==2
        await chat.stop()
        assert chat.task is None
        assert KEY not in json.dumps(chat.snapshot())
        assert len([r for r in requests if r.url.path.endswith('/channels')])==1
        assert [r.url.params.get('pageToken') for r in requests if r.url.path.endswith('/messages')]==[None,'2','1']
    asyncio.run(asyncio.wait_for(scenario(), 5))

@pytest.mark.parametrize('reason', ['quotaExceeded','liveChatEnded','liveChatDisabled','forbidden','keyInvalid'])
def test_errors_stop_without_leaking_key(tmp_path, reason):
    async def scenario():
        async def handler(request):
            return httpx.Response(403,json={'error':{'message':KEY,'errors':[{'reason':reason}]}})
        s=ApplicationServices(db_path=str(tmp_path/'db'),desktop=True)
        c=YouTubeChat(s,lambda:httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        await c.start(VIDEO,KEY)
        await c.task
        assert c.snapshot()['status']=='error'
        assert KEY not in json.dumps(c.snapshot())
        await c.stop()
    asyncio.run(scenario())

def test_transient_failure_uses_backoff_and_same_token(tmp_path):
    async def scenario():
        count=0
        delays=[]
        tokens=[]
        async def handler(request):
            nonlocal count
            if request.url.path.endswith('/videos'):
                return httpx.Response(200,json={'items':[{'liveStreamingDetails':{'activeLiveChatId':'live'}}]})
            count+=1
            tokens.append(request.url.params.get('pageToken'))
            if count==2: raise httpx.ConnectError('secret '+KEY)
            if count==3: return httpx.Response(403,json={'error':{'errors':[{'reason':'liveChatEnded'}]}})
            return httpx.Response(200,json={'items':[], 'nextPageToken':'resume','pollingIntervalMillis':15000})
        async def sleep(delay): delays.append(delay)
        c=YouTubeChat(ApplicationServices(db_path=str(tmp_path/'db'),desktop=True),lambda:httpx.AsyncClient(transport=httpx.MockTransport(handler)),sleep)
        await c.start(VIDEO,KEY)
        await c.task
        assert tokens==[None,'resume','resume']
        assert delays==[15,20]
        assert c.snapshot()['status']=='error'
        await c.stop()
    asyncio.run(scenario())

def test_api_requires_admin_and_rejects_bad_input(tmp_path):
    with TestClient(create_app(db_path=str(tmp_path/'db'),desktop=True),base_url='http://127.0.0.1') as c:
        assert c.get('/api/youtube/status').status_code==401
        c.headers['Authorization']='Bearer '+c.app.state.access_keys.ingest
        assert c.post('/api/youtube/connect',json={'url':VIDEO,'api_key':KEY}).status_code==401
        c.headers['Authorization']='Bearer '+c.app.state.access_keys.admin
        assert c.get('/api/youtube/status').json()['status']=='stopped'
        assert c.post('/api/youtube/connect',json={'url':'https://evil.com/'+VIDEO,'api_key':KEY}).status_code==422
        assert c.post('/api/youtube/disconnect',json={}).status_code==200
        assert KEY not in c.get('/api/control/backup').text


def test_stop_cancels_inflight_http_and_restart_has_no_old_worker(tmp_path):
    async def scenario():
        entered=asyncio.Event()
        cancelled=[]
        async def handler(request):
            entered.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.append(True)
                raise
        c=YouTubeChat(ApplicationServices(db_path=str(tmp_path/'db'),desktop=True),lambda:httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        await c.start(VIDEO,KEY)
        await entered.wait()
        await c.start(VIDEO,KEY)
        assert cancelled==[True]
        await asyncio.sleep(0)
        await c.stop()
        assert cancelled==[True,True]
        assert c.task is None
    asyncio.run(asyncio.wait_for(scenario(),2))


def test_closed_reception_and_malformed_messages_do_not_join(tmp_path):
    async def scenario():
        s=ApplicationServices(db_path=str(tmp_path/'db'),desktop=True)
        s.toggle_open()
        c=YouTubeChat(s)
        async def handler(request): return httpx.Response(200,json={'items':[]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await c._consume(client,KEY,{}, {})
            await c._consume(client,KEY,message('one','参加希望'),{})
        assert s.build_view_state()['current']==[]
        assert c.snapshot()['commands']==1
    asyncio.run(scenario())
