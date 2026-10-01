(() => {
  const button=document.getElementById('review-load');
  const count=document.getElementById('review-count');
  count.value=sessionStorage.getItem('review-sample-count') || '37';
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
