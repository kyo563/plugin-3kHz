(() => {
  const names = ['general', 'bot'];
  const tabs = names.map(name => document.getElementById('settings-' + name + '-tab'));
  function select(name, updateUrl = false) {
    const selected = name === 'bot' ? 'bot' : 'general';
    names.forEach((value, index) => {
      const active = value === selected;
      tabs[index].setAttribute('aria-selected', String(active));
      tabs[index].tabIndex = active ? 0 : -1;
      document.getElementById('settings-' + value + '-panel').hidden = !active;
    });
    if (updateUrl) {
      const url = new URL(location.href);
      if (selected === 'bot') url.searchParams.set('tab', 'bot');
      else url.searchParams.delete('tab');
      history.pushState(null, '', url.pathname + url.search + url.hash);
    }
    if (selected === 'general') window.dispatchEvent(new Event('resize'));
  }
  tabs.forEach((tab, index) => {
    tab.addEventListener('click', () => select(names[index], true));
    tab.addEventListener('keydown', event => {
      let next;
      if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') next = 1 - index;
      else if (event.key === 'Home') next = 0;
      else if (event.key === 'End') next = 1;
      else return;
      event.preventDefault();
      select(names[next], true);
      tabs[next].focus();
    });
  });
  const restore = () => select(new URLSearchParams(location.search).get('tab'));
  window.addEventListener('popstate', restore);
  restore();
})();
