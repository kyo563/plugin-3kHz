(() => {
    const display = document.getElementById('display');
    let ready = false;
    window.addEventListener('message', event => {
        if (event.origin === 'http://127.0.0.1:18765' && event.source === display.contentWindow
            && event.data?.type === 'waiting-list-display-ready') ready = true;
    });
    // OBS may load before OneComme. Keep the display empty and retry until the
    // worker starts; after that the shared renderer handles reconnection.
    display.style.visibility = 'hidden';
    const timer = setInterval(() => {
        if (ready) { display.style.visibility = 'visible'; clearInterval(timer); }
        else display.src = 'http://127.0.0.1:18765/onecomme-overlay';
    }, 3000);
})();
