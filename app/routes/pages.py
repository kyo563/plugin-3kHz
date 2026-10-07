from pathlib import Path
from html import escape
import json

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import FileResponse, RedirectResponse, HTMLResponse
from app.schemas.command_settings import CommandSettings
from app.schemas.overlay_settings import OneCommeOverlaySettings

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
        html = html[:start] + '<p id="onecomme-status" role="status">接続確認中…</p><p><a href="/settings">配信・接続設定</a></p>' + html[end:]
        html = html.replace('/static/youtube.js', '/static/onecomme.js')
        html = html.replace('<h1>待機列管理</h1>', '<p><a href="/settings?tab=bot">Bot設定</a></p><h1>待機列管理</h1>')
        html = html.replace('<h1>待機列管理</h1>', '<h1>待機列整理アプリ</h1>')
        html = html.replace('<body>', '<body data-onecomme="true">')
        html = html.replace('</head>', '<link rel="stylesheet" href="/static/control-display.css"></head>')
        controls = (STATIC_DIR / 'control-display.html').read_text(encoding='utf-8')
        html = html.replace('<div class="grid">', controls + '<div class="grid">', 1)
        html = html.replace('<script src="/static/control.js">', '<script src="/static/control-display.js"></script><script src="/static/control.js">')
        html = html.replace('</body>', '<script src="/static/setup-launch.js"></script></body>')
        html = html.replace('<ul id="waiting" aria-label="待機中の全参加者"></ul>', '<ul id="waiting" aria-label="待機中の参加者（最大128人表示）"></ul><button id="waiting-expand" type="button" aria-expanded="false" aria-controls="waiting" hidden>残りを表示</button><p id="waiting-overflow" role="status"></p>')
        return HTMLResponse(branded_page(html))
    return FileResponse(STATIC_DIR / "control.html")


@router.get("/overlay")
def overlay_page():
    return FileResponse(STATIC_DIR / "overlay.html")


@router.get("/settings")
def settings_page(request: Request):
    if request.app.state.onecomme_mode:
        html = (STATIC_DIR / "settings.html").read_text(encoding="utf-8")
        html = html.replace('<!-- ONECOMME_FONT_PICKER -->', (STATIC_DIR / 'font-picker.html').read_text(encoding='utf-8'))
        html = html.replace('<!-- ONECOMME_FONT_DETAILS_END -->', '</details>')
        html = html.replace('<!-- ONECOMME_TEXT_EFFECTS -->',
            '<p><label><input name="text_bold" type="checkbox" checked> 太字で強調する</label></p>'
            '<p><label><input name="text_shadow" type="checkbox" checked> 文字に影を付ける</label></p>')
        html = html.replace('<body>', '<body data-onecomme="true">')
        html = html.replace('<!-- ONECOMME_PARTICIPATION_NUMBER -->',
                            '<label><input type="checkbox" name="show_participation_number"> 名前の後ろに今回の配信での参加回数を表示する（例：プレイヤー名 *2回目）</label>')
        start = html.index('    <section class="panel fixed"')
        end = html.index('</section>', start) + len('</section>')
        html = html[:start] + html[end:]
        tabs = (STATIC_DIR / 'settings-tabs.html').read_text(encoding='utf-8')
        # Move existing forms intact: their IDs, save APIs and validation stay shared.
        start = html.index('    <section class="panel" aria-labelledby="layout-title">')
        end = html.index('    <section class="panel" aria-labelledby="comment-settings-title">', start)
        overlay = html[start:end]
        html = html[:start] + html[end:]
        start = html.index('    <section class="panel" aria-labelledby="reset-settings-title">')
        end = html.index('</dialog>', start) + len('</dialog>')
        overlay += html[start:end]
        html = html[:start] + html[end:]
        # Keep the standalone edition's guidance unchanged; simplify OneComme copy.
        start = overlay.index('      <p>保存するとOBSに自動反映されます。')
        end = overlay.index('      <div id="layout-preview-shell">', start)
        overlay = overlay[:start] + '      <p>OBSに表示される文言は以下のとおりです。</p>\n' + overlay[end:]
        overlay = overlay.replace('      <p>チェック模様は透過確認用です。OBSには表示されません。大きなサイズは縮小してプレビューします。</p>', '')
        overlay = overlay.replace('を初期値に戻して保存します。待機列・参加回数・総対戦回数・参加者名・追加済みフォント・コメントの制限時間・参加辞退の判定文言は残ります。', 'を初期値に戻します。')
        # Share the actual OBS controls with the basic/setup page, not copies.
        labels = []
        label_defaults = {}
        overlay_defaults = OneCommeOverlaySettings()
        for old, new in (('NOWの見出し', '現在対局中の見出し'),
                         ('NEXTの見出し', '次回グループの見出し'),
                         ('QUEUEの見出し', '待機グループ数の見出し')):
            overlay = overlay.replace(f'<label>{old} ', f'<label>{new} ')
        for key in ('open_label', 'now_label', 'next_label', 'queue_label'):
            start = overlay.index('<label>', overlay.rfind('\n', 0, overlay.index(f'name="{key}"')))
            end = overlay.index('</label>', start) + len('</label>')
            field_id = f'setup-label-{key}'
            labels.append(overlay[start:end].replace('<input ', f'<input id="{field_id}" form="overlay-layout-form" '))
            label_defaults[field_id] = getattr(overlay_defaults, key)
            overlay = overlay[:start] + overlay[end:]
        def reset_button(button_id, defaults):
            values = escape(json.dumps(defaults, ensure_ascii=False), quote=True)
            return f'<button type="button" class="setup-wording-reset" id="{button_id}" data-defaults="{values}">リセットしてやりなおす</button>'

        command_defaults = CommandSettings()
        html = html.replace('<p id="commands-result"', reset_button('setup-reset-commands', {
            'join-commands': '\n'.join(command_defaults.join),
            'cancel-commands': '\n'.join(command_defaults.cancel),
        }) + '<p id="commands-result"', 1)
        label_panel = ('<section class="panel setup-commands" aria-labelledby="display-labels-title">'
                       '<h2 id="display-labels-title">OBSの表示文言</h2><p>表示文言が変更できます</p>'
                       '<div class="layout-fields">' + ''.join(labels) + '</div>'
                       '<button type="submit" form="overlay-layout-form" id="save-display-labels" disabled>表示文言を保存して反映</button>'
                       + reset_button('setup-reset-labels', label_defaults) +
                       '<p id="display-labels-result" role="status"></p>'
                       '<p class="setting-note">※OBS表示用のフォントや透過度の変更は設定画面から可能です</p></section>')
        end = html.index('</section>', html.index('<form id="command-settings-form">')) + len('</section>')
        html = html[:end] + label_panel + html[end:]
        general = (STATIC_DIR / 'setup-general.html').read_text(encoding='utf-8').replace('<!-- CONNECTION -->', (STATIC_DIR / 'onecomme-panel.html').read_text(encoding='utf-8'))
        wizard = (STATIC_DIR / 'setup-wizard.html').read_text(encoding='utf-8')
        html = html.replace('</header>', '</header>' + wizard, 1)
        html = html.replace('</header>', '</header>' + tabs + '<div id="settings-general-panel" role="tabpanel" aria-labelledby="settings-general-tab">', 1)
        html = html.replace(wizard, general + wizard, 1)
        bot = (STATIC_DIR / 'bot.html').read_text(encoding='utf-8')
        # Wizard stays outside tab panels so it remains visible at every step.
        html = html.replace(wizard, '', 1).replace('<div class="settings-tabs"', wizard + '<div class="settings-tabs"', 1)
        obs = (STATIC_DIR / 'obs-settings.html').read_text(encoding='utf-8')
        overlay = '<details id="setup-obs-details" open><summary>表示を細かく調整する</summary>' + overlay + '</details>'
        html = html.replace('</main>', '</div><div id="settings-obs-panel" role="tabpanel" aria-labelledby="settings-obs-tab" hidden>' + obs + overlay + '</div><div id="settings-bot-panel" role="tabpanel" aria-labelledby="settings-bot-tab" hidden>' + bot + '</div></main>')
        html = html.replace('</head>', '<link rel="stylesheet" href="/static/bot.css"><link rel="stylesheet" href="/static/settings-tabs.css"></head>')
        html = html.replace('</body>', '<script src="/static/settings-tabs.js"></script><script src="/static/bot.js"></script><script src="/static/onecomme.js"></script><script src="/static/onecomme-obs-setup.js"></script><script src="/static/setup-wizard.js"></script></body>')
        html = html.replace('</head>', '<link rel="stylesheet" href="/static/onecomme-obs-setup.css"><link rel="stylesheet" href="/static/setup.css"></head>')
        html = html.replace('href="/obs-setup"', 'href="/settings?tab=obs"')
        html = html.replace('OBSの「ソース」一覧で対象のブラウザソースを右クリック →「プロパティ」→「幅」「高さ」を、下に表示される現在の幅・高さに合わせてください。', 'わんコメの「待機列整理アプリ」テンプレートをOBSに追加します。OBSの枠は縦横共通で幅1200・高さ600以上を推奨します。')
        html = html.replace('標準文字サイズ28pxの目安：縦480×600px、横1200×240px。適用後は「保存してOBSに反映」を押し、OBS側も同じ幅・高さにしてください。文字数・行数・フォントに合わせて調整できます。', '縦横を選ぶと、表示領域を縦480×600px・横1200×240pxに切り替えます。「保存してOBSに反映」でテンプレートも更新されます。文字数・行数に合わせた調整も可能です。')
        return HTMLResponse(branded_page(html))
    return FileResponse(STATIC_DIR / "settings.html")


@router.get("/obs-setup")
def obs_setup_page(request: Request):
    if request.app.state.onecomme_mode:
        return RedirectResponse('/settings?tab=obs', status_code=307)
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
    return RedirectResponse('/settings?tab=bot', status_code=307)
