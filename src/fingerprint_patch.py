"""
src/fingerprint_patch.py
Full browser fingerprint hardening — 8 vectors.
Import STEALTH_INIT_SCRIPT and pass to context.add_init_script().
"""

STEALTH_INIT_SCRIPT = r"""
// ── 1. Core automation signals ───────────────────────────────────────────────
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

Object.defineProperty(navigator, 'plugins', {
    get: () => {
        const makePlugin = (name, desc, filename, mimeTypes) => {
            const plugin = Object.create(Plugin.prototype);
            Object.defineProperty(plugin, 'name',        { get: () => name });
            Object.defineProperty(plugin, 'description', { get: () => desc });
            Object.defineProperty(plugin, 'filename',    { get: () => filename });
            Object.defineProperty(plugin, 'length',      { get: () => mimeTypes.length });
            mimeTypes.forEach((mt, i) => { plugin[i] = mt; });
            return plugin;
        };
        const plugins = [
            makePlugin('Chrome PDF Plugin',         'Portable Document Format', 'internal-pdf-viewer', []),
            makePlugin('Chrome PDF Viewer',         '',                         'mhjfbmdgcfjbbpaeojofohoefgiehjai', []),
            makePlugin('Native Client',             '',                         'internal-nacl-plugin', []),
            makePlugin('Widevine Content Decryption Module', 'Enables Widevine licenses', 'widevinecdmadapter.dll', []),
            makePlugin('Microsoft Edge PDF Plugin', 'Portable Document Format', 'pdf.dll', []),
        ];
        const list = Object.create(PluginArray.prototype);
        plugins.forEach((p, i) => { list[i] = p; list[p.name] = p; });
        Object.defineProperty(list, 'length', { get: () => plugins.length });
        list[Symbol.iterator] = Array.prototype[Symbol.iterator].bind(plugins);
        return list;
    }
});

Object.defineProperty(navigator, 'languages',           { get: () => ['uz-UZ', 'ru', 'en-US', 'en'] });
Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
Object.defineProperty(navigator, 'deviceMemory',        { get: () => 8 });
Object.defineProperty(navigator, 'maxTouchPoints',      { get: () => 0 });
Object.defineProperty(navigator, 'platform',            { get: () => 'Win32' });
Object.defineProperty(navigator, 'vendor',              { get: () => 'Google Inc.' });
Object.defineProperty(navigator, 'appVersion', {
    get: () => '5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
});

window.chrome = {
    runtime: {},
    loadTimes: function() {},
    csi: function() {},
    app: {}
};

// ── 2. Client Hints (navigator.userAgentData) ─────────────────────────────
const brandList = [
    { brand: 'Not_A Brand',   version: '8'   },
    { brand: 'Chromium',      version: '120' },
    { brand: 'Google Chrome', version: '120' }
];
const uaData = {
    brands:   brandList,
    mobile:   false,
    platform: 'Windows',
    getHighEntropyValues: (hints) => Promise.resolve({
        architecture:    'x86',
        bitness:         '64',
        brands:          brandList,
        fullVersionList: brandList.map(b => ({ brand: b.brand, version: b.version + '.0.0.0' })),
        mobile:          false,
        model:           '',
        platform:        'Windows',
        platformVersion: '15.0.0',
        uaFullVersion:   '120.0.0.0',
    }),
    toJSON: () => ({ brands: brandList, mobile: false, platform: 'Windows' })
};
Object.defineProperty(navigator, 'userAgentData', { get: () => uaData });

// ── 3. Canvas fingerprint noise ──────────────────────────────────────────────
// toDataURL / toBlob / getImageData ga ±1 pixel noise (seeded, ko'zga ko'rinmaydi).
(function() {
    const _noise = (() => {
        let s = (performance.now() * 1000) | 0;
        return () => { s ^= s << 13; s ^= s >> 17; s ^= s << 5; return (s >>> 0) / 4294967296; };
    })();

    const origToDataURL   = HTMLCanvasElement.prototype.toDataURL;
    const origToBlob      = HTMLCanvasElement.prototype.toBlob;
    const origGetContext  = HTMLCanvasElement.prototype.getContext;
    const origGetImageData = CanvasRenderingContext2D.prototype.getImageData;

    function addNoise(imageData) {
        const d = imageData.data;
        for (let i = 0; i < d.length; i += 4) {
            d[i]   = Math.min(255, Math.max(0, d[i]   + ((_noise() * 2 - 1) | 0)));
            d[i+1] = Math.min(255, Math.max(0, d[i+1] + ((_noise() * 2 - 1) | 0)));
            d[i+2] = Math.min(255, Math.max(0, d[i+2] + ((_noise() * 2 - 1) | 0)));
        }
        return imageData;
    }

    CanvasRenderingContext2D.prototype.getImageData = function(...args) {
        return addNoise(origGetImageData.apply(this, args));
    };

    HTMLCanvasElement.prototype.toDataURL = function(...args) {
        const ctx = origGetContext.call(this, '2d');
        if (ctx) {
            try {
                const id = origGetImageData.call(ctx, 0, 0, this.width || 1, this.height || 1);
                addNoise(id);
                ctx.putImageData(id, 0, 0);
            } catch(e) {}
        }
        return origToDataURL.apply(this, args);
    };

    HTMLCanvasElement.prototype.toBlob = function(cb, ...args) {
        const ctx = origGetContext.call(this, '2d');
        if (ctx) {
            try {
                const id = origGetImageData.call(ctx, 0, 0, this.width || 1, this.height || 1);
                addNoise(id);
                ctx.putImageData(id, 0, 0);
            } catch(e) {}
        }
        return origToBlob.call(this, cb, ...args);
    };
})();

// ── 4. WebGL fingerprint (WebGL1 + WebGL2) ───────────────────────────────────
(function() {
    const patch = (ctx) => {
        if (!window[ctx]) return;
        const orig = window[ctx].prototype.getParameter;
        window[ctx].prototype.getParameter = function(p) {
            if (p === 37445) return 'Intel Inc.';
            if (p === 37446) return 'Intel Iris OpenGL Engine';
            return orig.call(this, p);
        };
    };
    patch('WebGLRenderingContext');
    patch('WebGL2RenderingContext');
})();

// ── 5. AudioContext fingerprint block ─────────────────────────────────────────
// AnalyserNode output ga micro-noise qo'shadi — audio signature unikal bo'lmaydi.
(function() {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    const origCreateAnalyser = AC.prototype.createAnalyser;
    AC.prototype.createAnalyser = function(...args) {
        const analyser = origCreateAnalyser.apply(this, args);
        const _getFloat = analyser.getFloatFrequencyData.bind(analyser);
        const _getByte  = analyser.getByteFrequencyData.bind(analyser);
        analyser.getFloatFrequencyData = function(arr) {
            _getFloat(arr);
            for (let i = 0; i < arr.length; i++) arr[i] += (Math.random() - 0.5) * 0.0001;
        };
        analyser.getByteFrequencyData = function(arr) {
            _getByte(arr);
            for (let i = 0; i < arr.length; i++) arr[i] = Math.min(255, arr[i] + (Math.random() > 0.5 ? 1 : 0));
        };
        return analyser;
    };
})();

// ── 6. Font fingerprint masking ──────────────────────────────────────────────
// document.fonts.check() — faqat common system fonts uchun true.
// measureText.width — ±0.2px noise (font detection threshold dan past).
(function() {
    const SYSTEM_FONTS = [
        'arial','helvetica','times new roman','courier new','verdana',
        'georgia','trebuchet ms','impact','comic sans ms','tahoma',
        'palatino','garamond','bookman','sans-serif','serif','monospace',
        'cursive','fantasy'
    ];

    if (document.fonts && document.fonts.check) {
        const _check = document.fonts.check.bind(document.fonts);
        document.fonts.check = function(font, text) {
            const name = (font || '').replace(/\d+px\s*/i, '').trim().replace(/['"]/g, '').toLowerCase();
            return SYSTEM_FONTS.some(f => name.includes(f));
        };
    }

    const _measureText = CanvasRenderingContext2D.prototype.measureText;
    CanvasRenderingContext2D.prototype.measureText = function(text) {
        const result = _measureText.call(this, text);
        const noise  = (Math.random() - 0.5) * 0.4;
        const origW  = result.width;
        Object.defineProperty(result, 'width', { get: () => origW + noise, configurable: true });
        return result;
    };
})();

// ── 7. WebRTC IP leakage block ────────────────────────────────────────────────
// RTCPeerConnection wrap — iceServers bo'shatiladi, host candidate bloklanadi.
(function() {
    if (!window.RTCPeerConnection) return;
    const _RTC = window.RTCPeerConnection;

    function PatchedRTC(config, ...args) {
        if (config && config.iceServers) {
            config = Object.assign({}, config, { iceServers: [] });
        }
        const pc = new _RTC(config, ...args);

        const _addEL = pc.addEventListener.bind(pc);
        pc.addEventListener = function(type, listener, ...rest) {
            if (type === 'icecandidate') {
                const wrapped = function(event) {
                    if (event && event.candidate && event.candidate.candidate &&
                        event.candidate.candidate.includes('typ host')) return;
                    listener.apply(this, arguments);
                };
                return _addEL(type, wrapped, ...rest);
            }
            return _addEL(type, listener, ...rest);
        };

        Object.defineProperty(pc, 'onicecandidate', {
            set(fn) {
                if (!fn) return _addEL('icecandidate', () => {});
                _addEL('icecandidate', function(e) {
                    if (e && e.candidate && e.candidate.candidate &&
                        e.candidate.candidate.includes('typ host')) return;
                    fn.call(pc, e);
                });
            }
        });

        return pc;
    }

    PatchedRTC.prototype = _RTC.prototype;
    Object.defineProperties(PatchedRTC, Object.getOwnPropertyDescriptors(_RTC));
    window.RTCPeerConnection = PatchedRTC;
})();

// ── 8. Codec profiling spoof ──────────────────────────────────────────────────
// Uch xil API orqali codec fingerprint olinadi:
//   a) HTMLVideoElement / HTMLAudioElement.canPlayType()
//   b) RTCRtpSender.getCapabilities() / RTCRtpReceiver.getCapabilities()
//   c) MediaRecorder.isTypeSupported()
// Hammasi real Windows Chrome 120 profili bilan mos keladi.
(function() {

    // a) canPlayType — aniq javoblarni normalize qilamiz
    const VIDEO_TYPES = {
        'video/mp4':                                          'probably',
        'video/mp4; codecs="avc1.42E01E"':                   'probably',
        'video/mp4; codecs="avc1.42E01E, mp4a.40.2"':        'probably',
        'video/mp4; codecs="avc1.4D401E"':                   'probably',
        'video/mp4; codecs="avc1.64001E"':                   'probably',
        'video/mp4; codecs="avc1.640028"':                   'probably',
        'video/mp4; codecs="hev1.1.6.L93.B0"':              'probably',
        'video/webm':                                         'probably',
        'video/webm; codecs="vp8"':                          'probably',
        'video/webm; codecs="vp8, vorbis"':                  'probably',
        'video/webm; codecs="vp9"':                          'probably',
        'video/webm; codecs="vp9, opus"':                    'probably',
        'video/webm; codecs="av1"':                          'probably',
        'video/ogg':                                          'maybe',
        'video/ogg; codecs="theora"':                        'maybe',
        'application/x-mpegURL':                              'maybe',
    };
    const AUDIO_TYPES = {
        'audio/mpeg':                                         'probably',
        'audio/mp4':                                          'probably',
        'audio/mp4; codecs="mp4a.40.2"':                     'probably',
        'audio/ogg':                                          'probably',
        'audio/ogg; codecs="opus"':                          'probably',
        'audio/ogg; codecs="vorbis"':                        'probably',
        'audio/webm':                                         'probably',
        'audio/webm; codecs="opus"':                         'probably',
        'audio/wav':                                          'probably',
        'audio/wav; codecs="1"':                             'probably',
        'audio/flac':                                         'probably',
        'audio/aac':                                          'probably',
        'audio/x-aac':                                        'maybe',
    };

    const _videoCanPlay = HTMLVideoElement.prototype.canPlayType;
    const _audioCanPlay = HTMLAudioElement.prototype.canPlayType;

    HTMLVideoElement.prototype.canPlayType = function(type) {
        const t = (type || '').trim().toLowerCase();
        if (VIDEO_TYPES.hasOwnProperty(t)) return VIDEO_TYPES[t];
        return _videoCanPlay.call(this, type);
    };

    HTMLAudioElement.prototype.canPlayType = function(type) {
        const t = (type || '').trim().toLowerCase();
        if (AUDIO_TYPES.hasOwnProperty(t)) return AUDIO_TYPES[t];
        return _audioCanPlay.call(this, type);
    };

    // b) RTCRtpSender / RTCRtpReceiver.getCapabilities()
    // Real Chrome 120 Windows da mavjud bo'lgan codec ro'yxati
    const RTC_VIDEO_CODECS = [
        { mimeType: 'video/VP8',   clockRate: 90000, sdpFmtpLine: '' },
        { mimeType: 'video/VP9',   clockRate: 90000, sdpFmtpLine: 'profile-id=0' },
        { mimeType: 'video/VP9',   clockRate: 90000, sdpFmtpLine: 'profile-id=2' },
        { mimeType: 'video/H264',  clockRate: 90000, sdpFmtpLine: 'level-asymmetry-allowed=1;packetization-mode=1;profile-level-id=42001f' },
        { mimeType: 'video/H264',  clockRate: 90000, sdpFmtpLine: 'level-asymmetry-allowed=1;packetization-mode=0;profile-level-id=42001f' },
        { mimeType: 'video/H264',  clockRate: 90000, sdpFmtpLine: 'level-asymmetry-allowed=1;packetization-mode=1;profile-level-id=42e01f' },
        { mimeType: 'video/H264',  clockRate: 90000, sdpFmtpLine: 'level-asymmetry-allowed=1;packetization-mode=0;profile-level-id=42e01f' },
        { mimeType: 'video/AV1',   clockRate: 90000, sdpFmtpLine: '' },
        { mimeType: 'video/H265',  clockRate: 90000, sdpFmtpLine: '' },
        { mimeType: 'video/red',   clockRate: 90000, sdpFmtpLine: '' },
        { mimeType: 'video/ulpfec',clockRate: 90000, sdpFmtpLine: '' },
        { mimeType: 'video/rtx',   clockRate: 90000, sdpFmtpLine: '' },
    ];
    const RTC_AUDIO_CODECS = [
        { mimeType: 'audio/opus',       clockRate: 48000, channels: 2, sdpFmtpLine: 'minptime=10;useinbandfec=1' },
        { mimeType: 'audio/ISAC',       clockRate: 16000, channels: 1, sdpFmtpLine: '' },
        { mimeType: 'audio/ISAC',       clockRate: 32000, channels: 1, sdpFmtpLine: '' },
        { mimeType: 'audio/G722',       clockRate: 8000,  channels: 1, sdpFmtpLine: '' },
        { mimeType: 'audio/PCMU',       clockRate: 8000,  channels: 1, sdpFmtpLine: '' },
        { mimeType: 'audio/PCMA',       clockRate: 8000,  channels: 1, sdpFmtpLine: '' },
        { mimeType: 'audio/CN',         clockRate: 32000, channels: 1, sdpFmtpLine: '' },
        { mimeType: 'audio/CN',         clockRate: 16000, channels: 1, sdpFmtpLine: '' },
        { mimeType: 'audio/CN',         clockRate: 8000,  channels: 1, sdpFmtpLine: '' },
        { mimeType: 'audio/telephone-event', clockRate: 48000, channels: 1, sdpFmtpLine: '0-15' },
        { mimeType: 'audio/telephone-event', clockRate: 32000, channels: 1, sdpFmtpLine: '0-15' },
        { mimeType: 'audio/telephone-event', clockRate: 16000, channels: 1, sdpFmtpLine: '0-15' },
        { mimeType: 'audio/telephone-event', clockRate: 8000,  channels: 1, sdpFmtpLine: '0-15' },
    ];

    const RTC_CAPS = {
        video: { codecs: RTC_VIDEO_CODECS, headerExtensions: [
            { uri: 'urn:ietf:params:rtp-hdrext:toffset' },
            { uri: 'http://www.webrtc.org/experiments/rtp-hdrext/abs-send-time' },
            { uri: 'urn:3gpp:video-orientation' },
            { uri: 'http://www.ietf.org/id/draft-holmer-rmcat-transport-wide-cc-extensions-01' },
            { uri: 'http://www.webrtc.org/experiments/rtp-hdrext/playout-delay' },
            { uri: 'http://www.webrtc.org/experiments/rtp-hdrext/video-content-type' },
            { uri: 'http://www.webrtc.org/experiments/rtp-hdrext/video-timing' },
            { uri: 'http://www.webrtc.org/experiments/rtp-hdrext/color-space' },
            { uri: 'urn:ietf:params:rtp-hdrext:sdes:mid' },
            { uri: 'urn:ietf:params:rtp-hdrext:sdes:rtp-stream-id' },
            { uri: 'urn:ietf:params:rtp-hdrext:sdes:repaired-rtp-stream-id' },
        ]},
        audio: { codecs: RTC_AUDIO_CODECS, headerExtensions: [
            { uri: 'urn:ietf:params:rtp-hdrext:ssrc-audio-level' },
            { uri: 'http://www.ietf.org/id/draft-holmer-rmcat-transport-wide-cc-extensions-01' },
            { uri: 'urn:ietf:params:rtp-hdrext:sdes:mid' },
            { uri: 'urn:ietf:params:rtp-hdrext:sdes:rtp-stream-id' },
            { uri: 'urn:ietf:params:rtp-hdrext:sdes:repaired-rtp-stream-id' },
        ]},
    };

    if (window.RTCRtpSender && RTCRtpSender.getCapabilities) {
        const _senderCaps = RTCRtpSender.getCapabilities.bind(RTCRtpSender);
        RTCRtpSender.getCapabilities = function(kind) {
            if (kind === 'video') return JSON.parse(JSON.stringify(RTC_CAPS.video));
            if (kind === 'audio') return JSON.parse(JSON.stringify(RTC_CAPS.audio));
            return _senderCaps(kind);
        };
    }

    if (window.RTCRtpReceiver && RTCRtpReceiver.getCapabilities) {
        const _receiverCaps = RTCRtpReceiver.getCapabilities.bind(RTCRtpReceiver);
        RTCRtpReceiver.getCapabilities = function(kind) {
            if (kind === 'video') return JSON.parse(JSON.stringify(RTC_CAPS.video));
            if (kind === 'audio') return JSON.parse(JSON.stringify(RTC_CAPS.audio));
            return _receiverCaps(kind);
        };
    }

    // c) MediaRecorder.isTypeSupported()
    const MR_SUPPORTED = [
        'video/webm',
        'video/webm; codecs="vp8"',
        'video/webm; codecs="vp8, opus"',
        'video/webm; codecs="vp9"',
        'video/webm; codecs="vp9, opus"',
        'video/webm; codecs="av1"',
        'video/webm; codecs="av1, opus"',
        'video/webm; codecs="h264"',
        'video/webm; codecs="h264, opus"',
        'video/mp4',
        'video/mp4; codecs="avc1"',
        'video/mp4; codecs="avc1, mp4a.40.2"',
        'audio/webm',
        'audio/webm; codecs="opus"',
        'audio/ogg; codecs="opus"',
    ];
    const MR_SUPPORTED_SET = new Set(MR_SUPPORTED.map(t => t.trim().toLowerCase()));

    if (window.MediaRecorder) {
        const _isSupported = MediaRecorder.isTypeSupported.bind(MediaRecorder);
        MediaRecorder.isTypeSupported = function(type) {
            const t = (type || '').trim().toLowerCase();
            if (MR_SUPPORTED_SET.has(t)) return true;
            // Aniq yo'q deb bilganlarimiz
            if (t.includes('h265') || t.includes('hevc') || t.includes('mpeg')) return false;
            return _isSupported(type);
        };
    }

})();
"""