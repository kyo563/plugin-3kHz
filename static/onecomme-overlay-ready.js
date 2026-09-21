// No queue contents or credentials are sent to the embedding template.
if (window.parent !== window) window.parent.postMessage({type: 'waiting-list-display-ready'}, '*');
