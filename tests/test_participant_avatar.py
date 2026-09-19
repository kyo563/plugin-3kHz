import asyncio
import httpx
import pytest
from app.schemas.avatar import normalize_avatar_url
from app.services.application_services import ApplicationServices
from app.services.youtube_chat import YouTubeChat
from app.services.operator_service import export_backup


@pytest.mark.parametrize('url', ['http://yt3.ggpht.com/a', 'https://localhost/a', 'file:///a', 'https://ggpht.com.evil.test/a', 'https://x@yt3.ggpht.com/a', 'https://yt3.ggpht.com:99/a', None])
def test_invalid_avatar_is_ignored(url):
    assert normalize_avatar_url(url) is None


def test_youtube_avatar_survives_restart_and_backup_without_obs_exposure(tmp_path):
    path = str(tmp_path / 'avatar.db')
    services = ApplicationServices(db_path=path, desktop=True)
    url = 'https://yt3.ggpht.com/example=s32'
    item = {'id':'one', 'snippet':{'type':'textMessageEvent', 'publishedAt':'2026-09-20T00:00:00Z', 'textMessageDetails':{'messageText':'参加希望'}}, 'authorDetails':{'channelId':'UCexample', 'displayName':'Alice', 'profileImageUrl':url}}
    async def consume():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200,json={'items':[]}))) as client:
            await YouTubeChat(services)._consume(client,'key',item,{})
    asyncio.run(consume())
    restarted = ApplicationServices(db_path=path, desktop=True)
    state = restarted.build_view_state()
    assert state['current'][0]['avatar_url'] == url
    assert export_backup(restarted).state.current[0].avatar_url == url
    from app.services.overlay_state_service import OverlayStateService
    assert 'avatar_url' not in str(OverlayStateService().build_overlay_state(state))
