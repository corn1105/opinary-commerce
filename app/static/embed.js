(function () {
  var me = document.currentScript;
  if (!me) return;
  var pollId = me.getAttribute('data-poll-id');
  if (!pollId) return;

  var origin = new URL(me.src).origin;

  var iframe = document.createElement('iframe');
  iframe.src = origin + '/widget/' + encodeURIComponent(pollId);
  iframe.setAttribute('scrolling', 'no');
  iframe.setAttribute('frameborder', '0');
  iframe.setAttribute('allowtransparency', 'true');
  iframe.style.width = '100%';
  iframe.style.maxWidth = '460px';
  iframe.style.border = '0';
  iframe.style.display = 'block';
  iframe.style.margin = '0 auto';
  iframe.style.height = '300px';

  me.parentNode.insertBefore(iframe, me);

  window.addEventListener('message', function (e) {
    if (!e.data || e.data.type !== 'opinary-height') return;
    if (e.source !== iframe.contentWindow) return;
    var h = parseInt(e.data.height, 10);
    if (h > 0) iframe.style.height = h + 'px';
  });
})();
