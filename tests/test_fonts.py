import hashlib
import struct
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.schemas.overlay_settings import OverlaySettings
from app.services.application_services import ApplicationServices

# Small sfnt envelope; endpoint verifies structure, browser validates actual glyph data.
FONT = b"\x00\x01\x00\x00" + struct.pack('>HHHH',1,16,0,0) + struct.pack('>4sIII',b'name',0,28,4) + b'test'

@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(db_path=str(tmp_path/'state.db'),desktop=True),base_url='http://127.0.0.1') as c:
        c.headers['Authorization']='Bearer '+c.app.state.access_keys.admin
        yield c

def upload(client, data=FONT, **kwargs):
    return client.post('/api/fonts',content=data,headers={'Content-Type':'application/octet-stream','X-Font-Name':'sample.ttf',**kwargs})

def test_import_deduplicates_and_survives_restart(client,tmp_path):
    etag=client.get('/api/overlay-state').headers['etag']
    identifier=upload(client).json()['id']
    assert client.get('/api/overlay-state',headers={'If-None-Match':etag}).status_code==200
    assert identifier==hashlib.sha256(FONT).hexdigest()
    assert upload(client).status_code==200
    assert len(client.get('/api/fonts').json())==1
    fresh=ApplicationServices(db_path=str(tmp_path/'state.db'),desktop=True)
    assert bytes(fresh.persistence_service.get_font(identifier)['data'])==FONT
    public=client.get('/api/font-assets/'+identifier,headers={'Authorization':''})
    assert public.status_code==200 and public.content==FONT
    assert public.headers['content-type']=='font/ttf'
    assert client.get('/api/fonts',headers={'Authorization':''}).status_code==401
    assert upload(client,Authorization='').status_code==401
    assert upload(client,Authorization='Bearer '+client.app.state.access_keys.ingest).status_code==401
    assert upload(client,Origin='https://example.com').status_code==403

@pytest.mark.parametrize('data',[b'',b'<script>alert(1)</script>',FONT[:-1],b'ttcf'+bytes(50),b'wOF2'+bytes(50)])
def test_bad_font_rejected_without_saving(client,data):
    assert upload(client,data).status_code==422
    assert client.get('/api/fonts').json()==[]

def test_limits_and_no_filesystem_path_access(client):
    assert client.post('/api/fonts',content=b'x',headers={'Content-Type':'application/octet-stream','Content-Length':str(32*1024*1024+1)}).status_code==413
    assert client.get('/api/font-assets/not-a-font-id').status_code==404
    service=client.app.state.services.persistence_service
    for i in range(20):
        data=FONT+bytes([i]); service.store_font(hashlib.sha256(data).hexdigest(),'font','font/ttf',data)
    assert upload(client).status_code==422
    assert len(client.get('/api/fonts').json())==20

def test_settings_backup_and_missing_font_fallback_reference(client):
    identifier=upload(client).json()['id']
    settings=OverlaySettings().model_dump()
    settings['fonts'].update(all=identifier,now_names='mincho',ui_heading='gothic')
    assert client.post('/api/settings/overlay',json=settings).status_code==200
    assert client.get('/api/overlay-state').json()['appearance']['fonts']==settings['fonts']
    backup=client.get('/api/control/backup').json()
    assert backup['state']['overlay_settings']['fonts']==settings['fonts']
    assert 'font_assets' not in backup['state']
    old=OverlaySettings().model_dump(); old.pop('fonts')
    assert client.post('/api/settings/overlay',json=old).status_code==200
    assert client.get('/api/settings/overlay').json()['fonts']['all']=='default'
    for value in ('url(https://example.com/font.ttf)','../../file.ttf','arial; color:red'):
        settings['fonts']['all']=value
        assert client.post('/api/settings/overlay',json=settings).status_code==422

def test_cleanup_removes_font_copy_and_preserves_original(tmp_path):
    import sys
    if sys.platform!='win32': pytest.skip('Windows ownership')
    from desktop.ownership import OwnershipCatalog
    original=tmp_path/'original.ttf'; original.write_bytes(FONT)
    folder=tmp_path/'app'; db=folder/'state.db'
    catalog=OwnershipCatalog(tmp_path/'catalog'); catalog.register(folder,db)
    services=ApplicationServices(db_path=str(db),desktop=True)
    services.persistence_service.store_font(hashlib.sha256(FONT).hexdigest(),'font','font/ttf',original.read_bytes())
    assert catalog.remove()['errors']==[]
    assert not db.exists() and original.read_bytes()==FONT
