window.addEventListener('message', function(event) {
    if (typeof event.data['datawrapper-height'] !== 'undefined') {
        var iframes = document.querySelectorAll('iframe');
        for (var chartId in event.data['datawrapper-height']) {
            for (var i = 0; i < iframes.length; i++) {
                if (iframes[i].contentWindow === event.source) {
                    var frame = iframes[i];
                    frame.style.height = event.data['datawrapper-height'][chartId] + 'px';
                }
            }
        }
    }
});
