const byId = id => document.getElementById(id);
byId('obs-url').value = `${location.origin}/overlay`;
async function copyText(value, resultId) {
  try { await navigator.clipboard.writeText(value); byId(resultId).textContent = 'コピーしました。'; }
  catch (_) {
    const text = document.createElement('textarea'); text.value = value; document.body.append(text); text.select();
    const ok = document.execCommand('copy'); text.remove();
    byId(resultId).textContent = ok ? 'コピーしました。' : 'コピーできません。URL欄を選択してコピーしてください。';
  }
}
byId('copy-url').onclick = () => copyText(byId('obs-url').value, 'copy-result');
byId('preview-mode').onchange = () => {
  const mode = byId('preview-mode').value;
  byId('preview-panel').dataset.mode = mode;
  byId('preview-kind').textContent = mode === 'sample' ? 'サンプル表示：架空の参加者・固定データ' : mode === 'live' ? '現在の待機列：実際の参加者・自動更新' : 'プレビュー停止中';
  byId('preview-explanation').textContent = mode === 'sample' ? '表示テスト用です。実際の参加者や待機列とは連動しません。' : mode === 'live' ? '管理画面での追加・削除・次の対戦の操作が、この表示にも反映されます。参加者がいない場合は募集枠になります。' : '表示処理を停止しています。';
  byId('preview').src = mode === 'off' ? 'about:blank' : `/overlay?preview=1${mode === 'sample' ? '&sample=1' : ''}`;
  byId('preview').parentElement.hidden = mode === 'off';
};
async function checkStatus() {
  if (!document.hidden) {
    try {
      const response = await fetch('/api/obs-status'); if (!response.ok) throw new Error();
      const status = await response.json();
      byId('recommended-width').textContent = status.recommended_width;
      byId('recommended-height').textContent = status.recommended_height;
      byId('preview').style.width = `${status.recommended_width}px`;
      byId('preview').style.height = `${status.recommended_height}px`;
      const scale = Math.min(1, byId('preview').parentElement.clientWidth / status.recommended_width, 600 / status.recommended_height);
      byId('preview').style.transform = `scale(${scale})`;
      byId('preview').parentElement.style.height = `${status.recommended_height * scale}px`;
      const seconds = status.last_access_seconds;
      byId('access-status').textContent = seconds === null ? 'アプリ起動済み。表示URLへのアクセスはまだありません。' :
        seconds < 10 ? 'アプリ起動済み。表示URLへのアクセスを検出しています。' : `アプリ起動済み。最後のアクセスは約${Math.round(seconds)}秒前です。OBSのソースが非表示の場合も更新は止まります。`;
    } catch (_) { byId('access-status').textContent = 'アプリに接続できません。起動状態を確認してください。'; }
  }
  setTimeout(checkStatus, 3000);
}
async function loadPort() {
  const response = await fetch('/api/desktop-settings'); if (!response.ok) return;
  const settings = await response.json(); byId('port').value = settings.port || location.port;
  byId('save-port').disabled = !settings.available;
  byId('start-managing').hidden = !settings.available;
}
byId('port-form').onsubmit = async event => {
  event.preventDefault();
  try {
    const response = await fetch('/api/desktop-settings', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({port:Number(byId('port').value)})});
    if (!response.ok) throw new Error();
    byId('port-result').textContent = '保存しました。アプリ再起動後に有効になります。';
  } catch (_) { byId('port-result').textContent = '保存できませんでした。入力値と接続を確認してください。'; }
};
async function copyConnection(kind) {
  try {
    const response = await fetch('/api/connection'); if (!response.ok) throw new Error();
    const data = await response.json(); byId('receive-url').value = data.receive_url;
    await copyText(data[kind], 'connection-result');
  } catch (_) { byId('connection-result').textContent = '接続情報を取得できませんでした。'; }
}
byId('copy-control').onclick = () => copyConnection('control_url');
byId('copy-ingest').onclick = () => copyConnection('ingest_key');
byId('receive-url').value = `${location.origin}/api/comments/receive`;
loadPort().catch(() => {}); checkStatus();

byId('start-managing').onclick = async () => {
  byId('start-managing').disabled = true;
  try {
    const response = await fetch('/api/desktop/onboarding-complete', {method:'POST', signal:AbortSignal.timeout(5000)});
    if (!response.ok) throw new Error();
    location.href = '/control';
  } catch (_) {
    byId('start-result').textContent = '案内の完了を保存できません。もう一度押してください。';
    byId('start-managing').disabled = false;
  }
};
