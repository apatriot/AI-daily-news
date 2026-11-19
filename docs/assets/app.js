/* AI Daily — analytics + light interactions (no framework, ~5KB) */
(function () {
  'use strict';

  var CFG = window.__AI_DAILY__ || {};
  var PAGE = CFG.page || 'index';
  var STORY_ID = CFG.storyId || '';
  var FEEDBACK_URL = CFG.feedbackUrl || '';
  var QUALIFIED_MS = 15000;

  // ---------- identity ----------
  function uid() {
    var k = 'aid_uid';
    var v = localStorage.getItem(k);
    if (!v) {
      v = 'u_' + Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
      localStorage.setItem(k, v);
    }
    return v;
  }
  var UID = uid();
  var SID = 's_' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);

  // ---------- transport ----------
  function send(type, extra) {
    if (!FEEDBACK_URL) return;
    var payload = Object.assign({
      v: 1, ts: Date.now(), uid: UID, sid: SID, page: PAGE, type: type
    }, extra || {});
    try {
      var body = JSON.stringify(payload);
      if (navigator.sendBeacon) {
        navigator.sendBeacon(FEEDBACK_URL, new Blob([body], { type: 'text/plain;charset=UTF-8' }));
      } else {
        fetch(FEEDBACK_URL, {
          method: 'POST', mode: 'no-cors',
          headers: { 'Content-Type': 'text/plain;charset=UTF-8' },
          body: body, keepalive: true
        });
      }
    } catch (e) { /* never break reading */ }
  }

  function storyData(el) {
    if (!el) return {};
    return {
      story_id: el.getAttribute('data-story-id') || '',
      section: el.getAttribute('data-section') || '',
      cluster: el.getAttribute('data-cluster') || '',
      source: el.getAttribute('data-source') || ''
    };
  }

  // ---------- read state ----------
  function markRead(id) {
    try {
      var raw = localStorage.getItem('aid_read') || '{}';
      var map = JSON.parse(raw);
      map[id] = Date.now();
      var keys = Object.keys(map);
      if (keys.length > 300) {
        keys.sort(function (a, b) { return map[a] - map[b]; });
        keys.slice(0, keys.length - 300).forEach(function (k) { delete map[k]; });
      }
      localStorage.setItem('aid_read', JSON.stringify(map));
    } catch (e) {}
  }

  function isRead(id) {
    try {
      var map = JSON.parse(localStorage.getItem('aid_read') || '{}');
      return !!map[id];
    } catch (e) { return false; }
  }

  // ---------- impressions (list page) ----------
  function initImpressions() {
    var nodes = document.querySelectorAll('[data-story-id]');
    if (!nodes.length) return;
    if (!('IntersectionObserver' in window)) return;

    var shown = {};
    var order = Array.prototype.indexOf;

    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        var el = entry.target;
        var id = el.getAttribute('data-story-id');
        if (!id || shown[id]) return;
        if (entry.isIntersecting && entry.intersectionRatio >= 0.5) {
          el._seenAt = el._seenAt || Date.now();
          setTimeout(function () {
            if (shown[id] || !el._seenAt) return;
            shown[id] = true;
            send('impression', Object.assign(storyData(el), {
              position: order.call(nodes, el) + 1
            }));
            if (isRead(id) && el.classList.contains('card')) el.classList.add('is-read');
          }, 1000);
        } else {
          el._seenAt = 0;
        }
      });
    }, { threshold: [0, 0.5, 1] });

    nodes.forEach(function (el) { io.observe(el); });
  }

  // ---------- detail page dwell ----------
  var dwellStart = 0;
  var dwellAcc = 0;
  var qualifiedSent = false;
  var qualifiedTimer = null;
  var maxScroll = 0;
  var outbound = false;

  function foreground() { return document.visibilityState === 'visible'; }

  function startDwell() {
    if (dwellStart) return;
    dwellStart = Date.now();
    if (!qualifiedTimer) {
      qualifiedTimer = setTimeout(function () {
        if (qualifiedSent) return;
        qualifiedSent = true;
        send('read_qualified', Object.assign(storyData(document.querySelector('.detail')), {
          dwell_ms: QUALIFIED_MS
        }));
      }, QUALIFIED_MS);
    }
  }

  function pauseDwell() {
    if (!dwellStart) return;
    dwellAcc += Date.now() - dwellStart;
    dwellStart = 0;
  }

  function dwellMs() {
    return dwellAcc + (dwellStart ? Date.now() - dwellStart : 0);
  }

  function finishDwell() {
    var total = dwellMs();
    if (outbound) return; // outbound click already counts as intent
    if (total >= QUALIFIED_MS) {
      send('read_end', Object.assign(storyData(document.querySelector('.detail')), {
        dwell_ms: total, scroll: maxScroll
      }));
      markRead(STORY_ID);
    } else {
      send('bounce', Object.assign(storyData(document.querySelector('.detail')), {
        dwell_ms: total
      }));
    }
  }

  function initDetail() {
    if (!STORY_ID) return;
    startDwell();

    document.addEventListener('visibilitychange', function () {
      if (foreground()) startDwell(); else pauseDwell();
    });

    window.addEventListener('scroll', function () {
      var doc = document.documentElement;
      var max = doc.scrollHeight - window.innerHeight;
      var ratio = max > 0 ? window.scrollY / max : 0;
      if (ratio > maxScroll) maxScroll = Math.min(1, ratio);
    }, { passive: true });

    window.addEventListener('pagehide', finishDwell);
    document.addEventListener('click', function (e) {
      var link = e.target.closest('[data-outbound]');
      if (!link) return;
      outbound = true;
      send('outbound', Object.assign(storyData(document.querySelector('.detail')), {
        dwell_ms: dwellMs()
      }));
      markRead(STORY_ID);
    });
  }

  // ---------- list clicks ----------
  function initClicks() {
    document.addEventListener('click', function (e) {
      var link = e.target.closest('.card-main');
      if (!link) return;
      var card = link.closest('[data-story-id]');
      var data = storyData(card);
      markRead(data.story_id);
      send('click', data);
    });
  }

  // ---------- feedback ----------
  function toast(text) {
    var el = document.querySelector('.toast');
    if (!el) {
      el = document.createElement('div');
      el.className = 'toast';
      document.body.appendChild(el);
    }
    el.textContent = text;
    el.classList.add('show');
    clearTimeout(el._t);
    el._t = setTimeout(function () { el.classList.remove('show'); }, 1600);
  }

  function openSheet(card) {
    var data = storyData(card);
    var mask = document.createElement('div');
    mask.className = 'sheet-mask';
    mask.innerHTML =
      '<div class="sheet" role="dialog" aria-modal="true">' +
      '<div class="sheet-title">调整推荐</div>' +
      '<button data-act="less">少推这类</button>' +
      '<button data-act="mute">屏蔽这个来源</button>' +
      '<button data-act="read">标记为已读</button>' +
      '<button data-act="save">收藏</button>' +
      '<button data-act="cancel">取消</button>' +
      '</div>';
    document.body.appendChild(mask);
    requestAnimationFrame(function () { mask.classList.add('show'); });

    mask.addEventListener('click', function (e) {
      var btn = e.target.closest('button');
      if (!btn) { if (e.target === mask) close(); return; }
      var act = btn.getAttribute('data-act');
      if (act === 'cancel') { close(); return; }
      send('feedback', Object.assign(data, { action: act }));
      if (act === 'read') {
        markRead(data.story_id);
        if (card.classList.contains('card')) card.classList.add('is-read');
      }
      toast(act === 'save' ? '已收藏' : '已记录');
      close();
    });

    function close() {
      mask.classList.remove('show');
      setTimeout(function () { mask.remove(); }, 200);
    }
  }

  function initFeedback() {
    document.addEventListener('click', function (e) {
      var btn = e.target.closest('.act');
      if (!btn) return;
      e.preventDefault();
      e.stopPropagation();
      var card = btn.closest('[data-story-id]');
      var data = storyData(card);
      var action = btn.getAttribute('data-action');
      if (action === 'up') {
        if (btn.classList.contains('is-on')) return;
        btn.classList.add('is-on');
        send('feedback', Object.assign(data, { action: 'up' }));
        toast('已记录，明天会更准');
      } else if (action === 'more') {
        openSheet(card);
      }
    });
  }

  // ---------- progress bar ----------
  function initProgress() {
    var bar = document.getElementById('progress');
    if (!bar) return;
    window.addEventListener('scroll', function () {
      var doc = document.documentElement;
      var max = doc.scrollHeight - window.innerHeight;
      bar.style.width = (max > 0 ? (window.scrollY / max) * 100 : 0) + '%';
    }, { passive: true });
  }

  // ---------- restore scroll ----------
  function initScrollRestore() {
    if (PAGE !== 'index' || !('scrollRestoration' in history)) return;
    history.scrollRestoration = 'manual';
    var y = sessionStorage.getItem('aid_scroll');
    if (y) {
      requestAnimationFrame(function () { window.scrollTo(0, parseInt(y, 10) || 0); });
    }
    window.addEventListener('pagehide', function () {
      sessionStorage.setItem('aid_scroll', String(window.scrollY));
    });
  }

  // ---------- boot ----------
  function boot() {
    initProgress();
    initImpressions();
    initClicks();
    initFeedback();
    initDetail();
    initScrollRestore();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
