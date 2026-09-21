from pathlib import Path

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import FileResponse, RedirectResponse, HTMLResponse

router = APIRouter()
BASE_DIR = Path(__file__).resolve().parents[2]
STATIC_DIR = BASE_DIR / "static"


def branded_page(html):
    return html.replace('参加型整列プラグイン', '待機列整理アプリ')


@router.get("/")
def root():
    return RedirectResponse(url="/control", status_code=307)


@router.get("/control")
def control_page(request: Request):
    if request.app.state.onecomme_mode:
        html = (STATIC_DIR / "control.html").read_text(encoding="utf-8")
        start = html.index('        <details id="youtube-panel"')
        end = html.index('        <div class="actions">', start)
        html = html[:start] + (STATIC_DIR / "onecomme-panel.html").read_text(encoding="utf-8") + html[end:]
        html = html.replace('/static/youtube.js', '/static/onecomme.js')
        html = html.replace('<h1>待機列管理</h1>', '<p><a href="/bot">Botのお知らせ設定（任意）</a> — 初期状態は無効です。</p><h1>待機列管理</h1>')
        html = html.replace('<h1>待機列管理</h1>', '<h1>待機列整理アプリ</h1>')
        return HTMLResponse(branded_page(html))
    return FileResponse(STATIC_DIR / "control.html")


@router.get("/overlay")
def overlay_page():
    return FileResponse(STATIC_DIR / "overlay.html")


@router.get("/settings")
def settings_page(request: Request):
    if request.app.state.onecomme_mode:
        html = (STATIC_DIR / "settings.html").read_text(encoding="utf-8")
        html = html.replace('<body>', '<body data-onecomme="true">')
        start = html.index('    <section class="panel fixed"')
        end = html.index('</section>', start) + len('</section>')
        html = html[:start] + html[end:]
        html = html.replace('<main>', '<main><p><a href="/bot">Botのお知らせ設定</a></p>')
        html = html.replace('OBSの「ソース」一覧で対象のブラウザソースを右クリック →「プロパティ」→「幅」「高さ」を、下に表示される現在の幅・高さに合わせてください。', 'わんコメの「待機列整理アプリ」テンプレートをOBSに追加します。OBSの枠は縦横共通で幅1200・高さ600以上を推奨します。')
        html = html.replace('標準文字サイズ28pxの目安：縦480×600px、横1200×240px。適用後は「保存してOBSに反映」を押し、OBS側も同じ幅・高さにしてください。文字数・行数・フォントに合わせて調整できます。', '縦横を選ぶと、表示領域を縦480×600px・横1200×240pxに切り替えます。「保存してOBSに反映」でテンプレートも更新されます。文字数・行数に合わせた調整も可能です。')
        html = html.replace('保存するとOBSに自動反映されます。幅・高さは縦横共通です。一度OBS側と合わせた後、配置レイアウトの切り替えだけならOBS側の変更は不要です。', '設定はここで一括管理します。通常の縦横切り替えではOBS側の操作は不要です。表示領域を1200×600pxより大きくする場合は、OBSの幅・高さも広げてください。')
        return HTMLResponse(branded_page(html))
    return FileResponse(STATIC_DIR / "settings.html")


@router.get("/obs-setup")
def obs_setup_page(request: Request):
    if request.app.state.onecomme_mode:
        return FileResponse(STATIC_DIR / "onecomme-obs-setup.html")
    return FileResponse(STATIC_DIR / "obs-setup.html")


@router.get("/onecomme-overlay")
def onecomme_overlay(request: Request):
    if not request.app.state.onecomme_mode:
        raise HTTPException(404)
    html = (STATIC_DIR / 'overlay.html').read_text(encoding='utf-8')
    html = html.replace('</body>', '<script src="/static/onecomme-overlay-ready.js"></script></body>')
    return HTMLResponse(html)


@router.get('/bot')
def bot_page(request: Request):
    if not request.app.state.onecomme_mode:
        raise HTTPException(404)
    return FileResponse(STATIC_DIR / 'bot.html')
