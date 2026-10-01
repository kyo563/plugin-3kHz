(() => {
  for (const action of ['begin','moderator','approve','cancel']) {
    document.getElementById('review-bot-'+action).onclick = async () => {
      const result=document.getElementById('review-bot-result');
      try {
        const r=await fetch('/api/preview/bot',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action})});
        const data=await r.json();
        if(!r.ok) throw new Error(data.detail);
        result.textContent={begin:'シミュレーション中。Googleへの接続・実投稿はありません。',moderator:'標準モデレーター登録済みを再現しました。',approve:'認証許可を再現しました。下の「認証結果を確認」を押してください。',cancel:'認証キャンセルを再現しました。'}[action];
      } catch(e) {result.textContent=e.message;}
    };
  }
  // The real OAuth link is intentionally never produced in this offline simulation.
  document.getElementById('bot-connect')?.addEventListener('click', () => {
    document.getElementById('review-bot-result').textContent='シミュレーション中は認証リンクの代わりに「Google認証で許可した結果を再現」を押し、認証結果を確認してください。';
  });
  const button=document.getElementById('review-load');
  const count=document.getElementById('review-count');
  count.value=sessionStorage.getItem('review-sample-count') || '37';
  const stream=document.getElementById('review-stream');
  stream.disabled=true;
  fetch('/preview-status').then(r=>r.json()).then(s=>{stream.value=s.stream;}).catch(()=>{}).finally(()=>{stream.disabled=false;});
  stream.onchange=async()=>{
    stream.disabled=true;
    try {
      const r=await fetch('/api/preview/stream',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({state:stream.value})});
      if (!r.ok) throw new Error();
    } catch (_) { document.getElementById('review-result').textContent='サンプル配信の切り替えに失敗しました。'; }
    finally {stream.disabled=false;}
  };
  button.onclick=async()=>{
    button.disabled=true;
    try {
      const r=await fetch('/api/preview/scenario',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({count:Number(document.getElementById('review-count').value)})});
      if(!r.ok) throw new Error();
      sessionStorage.setItem('review-sample-count',count.value);
      location.assign('/control');
    } catch (_) { document.getElementById('review-result').textContent='読み込みに失敗しました。再試行してください。'; }
    finally {button.disabled=false;}
  };
})();
