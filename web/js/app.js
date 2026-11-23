// crunchyroller - web dashboard logic

let pollTimer = null;
let ddVideo = null;
let ddAudioQual = null;
let ddAudio = null;
let ddSubs = null;
let ddBitrate = null;
let ddAudioFormat = null;
let watcherState = {
  enabled: true,
  is_checking: false,
  interval_minutes: 60,
  monitored_count: 0,
  series: [],
};
let monitoredSeriesMap = new Map();

const VIDEO_OPTIONS = [
  { val: 'none', label: 'none (audio & subs only)' },
  { val: '1080p', label: '1080p' },
  { val: '720p', label: '720p' },
  { val: '480p', label: '480p' },
  { val: '360p', label: '360p' },
  { val: '240p', label: '240p' }
];

const AUDIO_FORMAT_OPTIONS = [
  { val: 'mka', label: '.mka (audio + subs)' },
  { val: 'mkv', label: '.mkv (audio + subs)' },
  { val: 'standalone', label: 'standalone files (.m4a + .ass)' }
];

const AUDIO_QUAL_OPTIONS = [
  { val: '192k', label: '192k' },
  { val: '96k', label: '96k' }
];

const BITRATE_OPTIONS = [
  { val: 'highest', label: 'highest (default)' },
  { val: 'lowest', label: 'data saver (lowest)' }
];

const AUDIO_OPTIONS = [
  { val: 'all', label: 'All available' },
  { val: 'ja-JP', label: 'Japanese' },
  { val: 'en-US', label: 'English' },
  { val: 'de-DE', label: 'German' },
  { val: 'fr-FR', label: 'French' },
  { val: 'es-419', label: 'Spanish (Latin America)' },
  { val: 'es-ES', label: 'Spanish (Spain)' },
  { val: 'pt-BR', label: 'Portuguese (Brazil)' },
  { val: 'pt-PT', label: 'Portuguese (Portugal)' },
  { val: 'it-IT', label: 'Italian' },
  { val: 'ru-RU', label: 'Russian' },
  { val: 'ar-SA', label: 'Arabic' },
  { val: 'hi-IN', label: 'Hindi' },
  { val: 'ko-KR', label: 'Korean' },
  { val: 'zh-CN', label: 'Chinese' },
  { val: 'id-ID', label: 'Indonesian' }
];

const SUBS_OPTIONS = [
  { val: 'all', label: 'All available' },
  { val: 'en-US', label: 'English' },
  { val: 'en-US-cc', label: 'English (CC)' },
  { val: 'ja-JP', label: 'Japanese' },
  { val: 'es-419', label: 'Spanish (Latin America)' },
  { val: 'es-ES', label: 'Spanish (Spain)' },
  { val: 'pt-BR', label: 'Portuguese (Brazil)' },
  { val: 'pt-PT', label: 'Portuguese (Portugal)' },
  { val: 'fr-FR', label: 'French' },
  { val: 'de-DE', label: 'German' },
  { val: 'it-IT', label: 'Italian' },
  { val: 'ru-RU', label: 'Russian' },
  { val: 'ar-SA', label: 'Arabic' },
  { val: 'hi-IN', label: 'Hindi' },
  { val: 'id-ID', label: 'Indonesian' },
  { val: 'vi-VN', label: 'Vietnamese' },
  { val: 'th-TH', label: 'Thai' },
  { val: 'tr-TR', label: 'Turkish' },
  { val: 'pl-PL', label: 'Polish' }
];

class CheckboxDropdown {
  constructor(containerId, hiddenInputId, options, defaultVal, onChange, multi = true) {
    this.container = document.getElementById(containerId);
    this.hiddenInput = document.getElementById(hiddenInputId);
    this.options = options;
    this.onChange = onChange;
    this.multi = multi;
    this.value = defaultVal || (multi ? 'all' : (options[0] ? options[0].val : ''));
    this.init();
  }

  init() {
    if (!this.container) return;
    this.container.innerHTML = `
      <div class="select-btn" tabindex="0" role="button" aria-haspopup="listbox">
        <span class="select-btn-text"></span>
        <svg class="select-arrow" width="10" height="6" viewBox="0 0 10 6" fill="none">
          <path d="M1 1L5 5L9 1" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </div>
      <div class="select-menu" role="listbox"></div>
    `;

    this.btn = this.container.querySelector('.select-btn');
    this.btnText = this.container.querySelector('.select-btn-text');
    this.menu = this.container.querySelector('.select-menu');

    this.btn.addEventListener('click', (e) => {
      e.stopPropagation();
      this.toggle();
    });

    this.btn.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        this.toggle();
      }
    });

    document.addEventListener('click', (e) => {
      if (!document.contains(e.target)) return;
      if (!this.container.contains(e.target)) {
        this.close();
      }
    });

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && this.container.classList.contains('open')) {
        this.close();
      }
    });

    this.render();
  }

  toggle() {
    const wasOpen = this.container.classList.contains('open');
    document.querySelectorAll('.select-dropdown.open').forEach(el => el.classList.remove('open'));
    if (!wasOpen) {
      this.container.classList.add('open');
    }
  }

  close() {
    this.container.classList.remove('open');
  }

  getSelectedList() {
    if (!this.multi) return [this.value];
    if (!this.value || !this.value.trim()) return ['all'];
    if (this.value.trim().toLowerCase() === 'all') return ['all'];
    return this.value.split(',').map(s => s.trim()).filter(Boolean);
  }

  setValue(val, triggerChange = true) {
    const nextVal = (!this.multi)
      ? (val || (this.options[0] ? this.options[0].val : ''))
      : (val || 'all');

    const changed = (this.value !== nextVal);
    this.value = nextVal;
    if (this.hiddenInput) this.hiddenInput.value = this.value;

    this.updateDisplay();

    if (triggerChange && this.onChange && changed) {
      this.onChange(this.value);
    }
  }

  selectSingle(val) {
    this.setValue(val, true);
    this.close();
  }

  toggleItem(val) {
    if (!this.multi) {
      this.selectSingle(val);
      return;
    }

    if (val === 'all') {
      this.setValue('all');
      return;
    }

    let list = this.getSelectedList();
    const allSpecific = this.options.filter(o => o.val !== 'all').map(o => o.val.toLowerCase());

    if (list.includes('all')) {
      list = [val];
    } else {
      const idx = list.findIndex(c => c.toLowerCase() === val.toLowerCase());
      if (idx !== -1) {
        list.splice(idx, 1);
      } else {
        list.push(val);
      }
    }

    if (list.length === 0) {
      this.setValue('all');
      return;
    }

    if (list.length >= allSpecific.length && allSpecific.every(code => list.some(c => c.toLowerCase() === code))) {
      this.setValue('all');
      return;
    }

    this.setValue(list.join(','));
  }

  updateDisplay() {
    if (!this.multi) {
      const found = this.options.find(o => o.val.toLowerCase() === (this.value || '').toLowerCase());
      if (this.btnText) this.btnText.textContent = found ? found.label : (this.value || 'Select');
    } else {
      const selected = this.getSelectedList();
      const isAll = selected.includes('all');
      if (isAll) {
        if (this.btnText) this.btnText.textContent = 'All available';
      } else {
        const labels = selected.map(code => {
          const found = this.options.find(o => o.val.toLowerCase() === code.toLowerCase());
          return found ? found.label : code;
        });
        if (this.btnText) {
          if (labels.length === 1) {
            this.btnText.textContent = labels[0];
          } else if (labels.length === 2) {
            this.btnText.textContent = `${labels[0]}, ${labels[1]}`;
          } else {
            this.btnText.textContent = `${labels[0]}, ${labels[1]} +${labels.length - 2}`;
          }
        }
      }
    }

    if (!this.menu) return;
    const selected = this.getSelectedList();
    const isAll = selected.includes('all');
    this.menu.querySelectorAll('.select-opt').forEach(row => {
      const optVal = (row.dataset.val || '').toLowerCase();
      const isChecked = (!this.multi)
        ? (optVal === (this.value || '').toLowerCase())
        : (isAll ? (optVal === 'all') : selected.some(c => c.toLowerCase() === optVal));

      row.classList.toggle('selected', isChecked);
      row.setAttribute('aria-selected', isChecked ? 'true' : 'false');
      const cb = row.querySelector('.cb-custom');
      if (cb) cb.checked = isChecked;
    });
  }

  render() {
    if (!this.menu) return;
    const scrollPos = this.menu.scrollTop;
    this.menu.innerHTML = '';

    const selected = this.getSelectedList();
    const isAll = selected.includes('all');

    this.options.forEach(opt => {
      const isChecked = (!this.multi)
        ? (opt.val.toLowerCase() === (this.value || '').toLowerCase())
        : (isAll ? (opt.val === 'all') : selected.some(c => c.toLowerCase() === opt.val.toLowerCase()));

      const row = document.createElement('div');
      row.className = 'select-opt' + (isChecked ? ' selected' : '') + (opt.val === 'all' ? ' opt-all' : '');
      row.dataset.val = opt.val;
      row.setAttribute('role', 'option');
      row.setAttribute('aria-selected', isChecked ? 'true' : 'false');

      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.className = 'cb-custom';
      cb.checked = isChecked;
      cb.tabIndex = -1;

      const label = document.createElement('span');
      label.className = 'select-opt-text';
      label.textContent = opt.label;

      row.append(cb, label);

      row.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (!this.multi) {
          this.selectSingle(opt.val);
        } else {
          this.toggleItem(opt.val);
        }
      });

      this.menu.appendChild(row);
    });

    this.updateDisplay();
    this.menu.scrollTop = scrollPos;
  }
}

// quick toast popup
function toast(msg, type = 'ok') {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = 'show ' + type;
  clearTimeout(el._timer);
  el._timer = setTimeout(() => el.className = '', 2800);
}

// fetch wrapper for backend API calls
async function api(endpoint, payload = null) {
  const options = payload != null
    ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }
    : { method: 'GET' };
  try {
    const res = await fetch(endpoint, options);
    const text = await res.text();
    try {
      return JSON.parse(text);
    } catch (parseErr) {
      console.warn(`[api] Non-JSON response from ${endpoint} (HTTP ${res.status}):`, text.slice(0, 150));
      return {
        success: false,
        error: `HTTP ${res.status}: Server returned HTML instead of JSON. If you just updated files, please restart web_gui.py!`,
      };
    }
  } catch (netErr) {
    console.error(`[api] Network error calling ${endpoint}:`, netErr);
    return { success: false, error: netErr.message || 'Network error' };
  }
}

// init app state on page load
window.addEventListener('DOMContentLoaded', async () => {
  ddVideo = new CheckboxDropdown('dd-video', 'vq', VIDEO_OPTIONS, '1080p', () => saveCfg(), false);
  ddAudioQual = new CheckboxDropdown('dd-audio-qual', 'aq', AUDIO_QUAL_OPTIONS, '192k', () => saveCfg(), false);
  ddAudio = new CheckboxDropdown('dd-audio', 'al', AUDIO_OPTIONS, 'ja-JP', () => saveCfg(), true);
  ddSubs = new CheckboxDropdown('dd-subs', 'sl', SUBS_OPTIONS, 'en-US', () => saveCfg(), true);
  ddBitrate = new CheckboxDropdown('dd-bitrate', 'bitrate-mode', BITRATE_OPTIONS, 'highest', () => saveCfg(), false);
  ddAudioFormat = new CheckboxDropdown('dd-audio-format', 'audio-only-format', AUDIO_FORMAT_OPTIONS, 'mka', () => saveCfg(), false);


  const state = await api('/api/state');
  applyState(state);

  ['login-email', 'login-pass'].forEach(id => {
    const el = document.getElementById(id);
    if (el) {
      el.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          loginCredentials();
        }
      });
    }
  });

  const searchInput = document.getElementById('search-input');
  if (searchInput) {
    searchInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        searchSeries();
      }
    });
    searchInput.addEventListener('input', () => {
      const clearBtn = document.getElementById('search-clear-btn');
      if (clearBtn) {
        clearBtn.style.display = searchInput.value.trim() ? 'block' : 'none';
      }
    });
  }

  const urlInput = document.getElementById('url');
  if (urlInput) {
    urlInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        fetchUrl();
      }
    });
    urlInput.addEventListener('input', () => {
      autoResizeUrlTextarea(urlInput);
    });
  }

  initCustomContextMenu();
  checkForUpdates(false);
  loadGitHubStars();
});

function autoResizeUrlTextarea(el) {
  if (!el) return;
  el.style.height = 'auto';
  el.style.height = Math.min(140, Math.max(38, el.scrollHeight)) + 'px';
}

// Fetch and display live GitHub star count in header
async function loadGitHubStars() {
  const countEl = document.getElementById('github-star-count');
  if (!countEl) return;

  // 1. Try local backend endpoint first (cached for 10 minutes to avoid rate limits)
  try {
    const res = await api('/api/stars');
    if (res && res.success && res.stars > 0) {
      countEl.textContent = String(res.stars);
      countEl.style.display = 'inline';
      return;
    }
  } catch (e) {}

  // 2. Direct client-side fetch fallback
  try {
    const resp = await fetch('https://api.github.com/repos/Vure-sh/crunchyroller', {
      headers: { 'Accept': 'application/vnd.github.v3+json' }
    });
    if (resp.ok) {
      const data = await resp.json();
      if (data && data.stargazers_count > 0) {
        countEl.textContent = String(data.stargazers_count);
        countEl.style.display = 'inline';
      }
    }
  } catch (e) {}
}

// sync UI with backend state
function applyState(state) {
  const badge = document.getElementById('badge');
  const badgeTxt = document.getElementById('badge-txt');

  if (state.authenticated) {
    badge.classList.add('on');
    badgeTxt.textContent = 'connected';
    if (state.auth_type === 'android_tv') {
      badge.title = 'Connected via Android TV login';
    } else if (state.auth_type === 'token') {
      badge.title = 'Connected via session token';
    } else {
      badge.title = 'Connected';
    }
  } else {
    badge.classList.remove('on');
    badgeTxt.textContent = 'offline';
    badge.title = 'Offline';
  }

  // update settings
  if (state.config) {
    if (ddVideo && state.config.video_quality) {
      ddVideo.setValue(state.config.video_quality, false);
    } else if (state.config.video_quality) {
      document.getElementById('vq').value = state.config.video_quality;
    }

    if (ddAudioQual && state.config.audio_quality) {
      ddAudioQual.setValue(state.config.audio_quality, false);
    } else if (state.config.audio_quality) {
      document.getElementById('aq').value = state.config.audio_quality;
    }

    if (ddAudio && state.config.audio_lang) {
      ddAudio.setValue(state.config.audio_lang, false);
    } else if (state.config.audio_lang) {
      document.getElementById('al').value = state.config.audio_lang;
    }

    if (ddSubs && state.config.subs_lang) {
      ddSubs.setValue(state.config.subs_lang, false);
    } else if (state.config.subs_lang) {
      document.getElementById('sl').value = state.config.subs_lang;
    }

    if (ddBitrate && state.config.bitrate_mode) {
      ddBitrate.setValue(state.config.bitrate_mode, false);
    } else if (state.config.bitrate_mode) {
      const bmEl = document.getElementById('bitrate-mode');
      if (bmEl) bmEl.value = state.config.bitrate_mode;
    }

    if (ddAudioFormat && state.config.audio_only_format) {
      ddAudioFormat.setValue(state.config.audio_only_format, false);
    } else if (state.config.audio_only_format) {
      const aofEl = document.getElementById('audio-only-format');
      if (aofEl) aofEl.value = state.config.audio_only_format;
    }
    const forceDownload = document.getElementById('force-download');
    if (forceDownload) forceDownload.checked = Boolean(state.config.force_download);

    const enableResume = document.getElementById('enable-resume');
    if (enableResume && state.config.enable_resume !== undefined) {
      enableResume.checked = Boolean(state.config.enable_resume);
    }

    const enableLogging = document.getElementById('enable-logging');
    if (enableLogging && state.config.enable_logging !== undefined) {
      enableLogging.checked = Boolean(state.config.enable_logging);
    }

    const audioFallback = document.getElementById('audio-fallback');
    if (audioFallback && state.config.audio_fallback !== undefined) {
      audioFallback.checked = Boolean(state.config.audio_fallback);
    }

    if (state.config.workers !== undefined) {
      const slider = document.getElementById('workers-slider');
      if (slider) {
        slider.value = state.config.workers;
        onWorkersSlider(state.config.workers);
      }
    }

    const dlDirInput = document.getElementById('download-dir');
    if (dlDirInput && state.config.download_dir !== undefined) {
      dlDirInput.value = (state.config.download_dir === 'anime') ? '' : (state.config.download_dir || '');
    }

    if (state.config.enable_antiratelimit !== undefined) {
      const en = Boolean(state.config.enable_antiratelimit);
      const m = document.getElementById('enable-antiratelimit');
      if (m) m.checked = en;
      const s = document.getElementById('antiratelimit-enable-sub');
      if (s) s.checked = en;
    }

    if (state.config.antiratelimit_delay !== undefined) {
      const dSlider = document.getElementById('antiratelimit-delay-slider');
      if (dSlider) {
        dSlider.value = state.config.antiratelimit_delay;
        const dBadge = document.getElementById('antiratelimit-delay-badge');
        if (dBadge) dBadge.textContent = `${state.config.antiratelimit_delay}s`;
      }
    }

    if (state.config.antiratelimit_jitter !== undefined) {
      const jSlider = document.getElementById('antiratelimit-jitter-slider');
      if (jSlider) {
        jSlider.value = state.config.antiratelimit_jitter;
        const jBadge = document.getElementById('antiratelimit-jitter-badge');
        if (jBadge) jBadge.textContent = `± ${state.config.antiratelimit_jitter}s`;
      }
    }

    if (state.config.antiratelimit_reduce_threads !== undefined) {
      const rtCheck = document.getElementById('antiratelimit-reduce-threads');
      if (rtCheck) rtCheck.checked = Boolean(state.config.antiratelimit_reduce_threads);
    }

    updateAntiRateLimitPreview();

    updateQuickFormatBar();
  }

  if (state.log_path) {
    const logPathDisplay = document.getElementById('log-path-display');
    if (logPathDisplay) {
      logPathDisplay.textContent = state.log_path;
    }
  }

  if (state.version) {
    const verDisplay = document.getElementById('version-display');
    if (verDisplay) {
      verDisplay.textContent = 'v' + state.version;
    }
  }

  // Update nav queue badge
  const navBadge = document.getElementById('nav-queue-badge');
  const queuedCount = (state.download && state.download.queued_count !== undefined)
    ? state.download.queued_count
    : (state.queue ? state.queue.length : 0);
  if (navBadge) {
    if (queuedCount > 0) {
      navBadge.style.display = 'inline-flex';
      navBadge.textContent = String(queuedCount);
    } else {
      navBadge.style.display = 'none';
    }
  }

  // if a download is running, start polling progress
  if (state.download && state.download.status === 'running') startPolling();
  updateProgressPanel(state.download);

  if (state.watcher) {
    updateWatcherState(state.watcher);
  }
}

// manual token save
async function saveToken() {
  const val = document.getElementById('tok').value.trim();
  if (!val) {
    toast('paste your token first', 'err');
    return;
  }
  const res = await api('/api/login', { etp_rt: val });
  if (res.success) {
    toast('token saved!', 'ok');
    document.getElementById('badge').classList.add('on');
    document.getElementById('badge-txt').textContent = 'connected';
    document.getElementById('badge').title = 'Connected via session token';
    document.getElementById('tok').value = '';
  } else {
    toast(res.error || 'invalid token', 'err');
  }
}

// toggle collapsible Android TV login form
function toggleAndroidLoginForm() {
  const panel = document.getElementById('android-login-panel');
  const btn = document.getElementById('toggle-android-login-btn');
  if (!panel) return;
  const isHidden = panel.style.display === 'none' || !panel.style.display;
  panel.style.display = isHidden ? 'flex' : 'none';
  if (btn) btn.classList.toggle('active', isHidden);
  if (isHidden) {
    const emailInput = document.getElementById('login-email');
    if (emailInput) emailInput.focus();
  }
}

// Android TV username & password login
async function loginCredentials() {
  const username = (document.getElementById('login-email').value || '').trim();
  const password = (document.getElementById('login-pass').value || '').trim();
  if (!username || !password) {
    toast('enter email and password', 'err');
    return;
  }
  const btn = document.getElementById('btn-login-cred');
  const origText = btn ? btn.textContent : 'sign in';
  if (btn) {
    btn.disabled = true;
    btn.textContent = 'signing in...';
  }
  toast('signing in...', 'ok');
  try {
    const res = await api('/api/login-credentials', { username, password });
    if (res.success) {
      toast('signed in successfully!', 'ok');
      document.getElementById('badge').classList.add('on');
      document.getElementById('badge-txt').textContent = 'connected';
      document.getElementById('badge').title = 'Connected via Android TV login';
      document.getElementById('login-pass').value = '';
      setTimeout(() => {
        const panel = document.getElementById('android-login-panel');
        const toggleBtn = document.getElementById('toggle-android-login-btn');
        if (panel) panel.style.display = 'none';
        if (toggleBtn) toggleBtn.classList.remove('active');
      }, 1200);
    } else {
      toast(res.error || 'login failed', 'err');
    }
  } catch (e) {
    toast('login failed: ' + e.message, 'err');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = origText;
    }
  }
}

// save quality / language dropdowns, workers, resume, logging & download directory
async function saveCfg() {
  const vqVal = ddVideo ? ddVideo.value : (document.getElementById('vq')?.value || '1080p');
  const aqVal = ddAudioQual ? ddAudioQual.value : (document.getElementById('aq')?.value || '192k');
  const audioVal = ddAudio ? ddAudio.value : (document.getElementById('al')?.value || 'ja-JP');
  const subsVal = ddSubs ? ddSubs.value : (document.getElementById('sl')?.value || 'en-US');
  const dlDirVal = (document.getElementById('download-dir') || {}).value || '';
  const workersVal = parseInt(document.getElementById('workers-slider')?.value || '16', 10);
  const resumeVal = Boolean(document.getElementById('enable-resume')?.checked);
  const loggingVal = Boolean(document.getElementById('enable-logging')?.checked);
  const audioFallbackVal = Boolean(document.getElementById('audio-fallback')?.checked ?? true);
  const bitrateVal = ddBitrate ? ddBitrate.value : (document.getElementById('bitrate-mode')?.value || 'highest');
  const audioFormatVal = ddAudioFormat ? ddAudioFormat.value : (document.getElementById('audio-only-format')?.value || 'mka');

  const enableAntiRateLimit = Boolean(
    document.getElementById('enable-antiratelimit')?.checked ||
    document.getElementById('antiratelimit-enable-sub')?.checked
  );
  const arDelayVal = parseInt(document.getElementById('antiratelimit-delay-slider')?.value || '60', 10);
  const arJitterVal = parseInt(document.getElementById('antiratelimit-jitter-slider')?.value || '5', 10);
  const arReduceThreads = Boolean(document.getElementById('antiratelimit-reduce-threads')?.checked);

  await api('/api/config', {
    video_quality: vqVal,
    audio_quality: aqVal,
    audio_lang: audioVal,
    subs_lang: subsVal,
    force_download: (document.getElementById('force-download') || {}).checked || false,
    download_dir: dlDirVal.trim() || 'anime',
    workers: workersVal,
    enable_resume: resumeVal,
    enable_logging: loggingVal,
    audio_fallback: audioFallbackVal,
    bitrate_mode: bitrateVal,
    audio_only_format: audioFormatVal,
    enable_antiratelimit: enableAntiRateLimit,
    antiratelimit_delay: arDelayVal,
    antiratelimit_jitter: arJitterVal,
    antiratelimit_reduce_threads: arReduceThreads,
  });

  updateAntiRateLimitPreview();
  updateQuickFormatBar();
}

// Tab switcher
function switchTab(tabName) {
  const m = document.getElementById('enable-antiratelimit');
  const s = document.getElementById('antiratelimit-enable-sub');
  if (m && s) {
    if (tabName === 'settings') {
      m.checked = s.checked;
    } else if (tabName === 'antiratelimit') {
      s.checked = m.checked;
    }
    if (tabName === 'browse' && !browseLoaded) {
      browseLoaded = true;
      loadBrowseAnimes();
    }
    if (tabName === 'watchlist' && !watchlistLoaded) {
      watchlistLoaded = true;
      loadUserWatchlist();
    }
  }

  document.querySelectorAll('.nav-tab').forEach(tab => {
    if (tabName === 'antiratelimit') {
      tab.classList.toggle('active', tab.dataset.tab === 'settings');
    } else {
      tab.classList.toggle('active', tab.dataset.tab === tabName);
    }
  });

  document.querySelectorAll('.tab-pane').forEach(pane => {
    const isActive = pane.id === `tab-${tabName}`;
    pane.classList.toggle('active', isActive);
    pane.style.display = isActive ? 'block' : 'none';
  });

  if (tabName === 'settings' || tabName === 'antiratelimit') {
    updateAntiRateLimitPreview();
    updatePartialsCacheStatus();
    loadHistory();
  }
  if (tabName === 'autodl') {
    renderAutoDlTab();
  }
}

// Slider live badge update
function onWorkersSlider(val) {
  const badge = document.getElementById('workers-badge');
  if (badge) badge.textContent = `${val} workers`;
}

// Anti-Ratelimit Controls & Preview
function openAntiRatelimitView() {
  const m = document.getElementById('enable-antiratelimit');
  const s = document.getElementById('antiratelimit-enable-sub');
  if (m && s) {
    s.checked = m.checked;
  }
  updateAntiRateLimitPreview();
  switchTab('antiratelimit');
}

function onAntiRateLimitDelay(val) {
  const badge = document.getElementById('antiratelimit-delay-badge');
  if (badge) badge.textContent = `${val}s`;
  updateAntiRateLimitPreview();
}

function onAntiRateLimitJitter(val) {
  const badge = document.getElementById('antiratelimit-jitter-badge');
  if (badge) badge.textContent = `± ${val}s`;
  updateAntiRateLimitPreview();
}

function onAntiRateLimitMasterToggle(checked) {
  toggleAntiRateLimit(checked);
}

function toggleAntiRateLimit(checked) {
  const m = document.getElementById('enable-antiratelimit');
  const s = document.getElementById('antiratelimit-enable-sub');
  if (m) m.checked = checked;
  if (s) s.checked = checked;
  if (checked) {
    const rt = document.getElementById('antiratelimit-reduce-threads');
    if (rt) rt.checked = true;
  }
  updateAntiRateLimitPreview();
  saveCfg();
}

function updateAntiRateLimitPreview() {
  const m = document.getElementById('enable-antiratelimit');
  const s = document.getElementById('antiratelimit-enable-sub');
  const isEnabled = Boolean((m && m.checked) || (s && s.checked));
  if (m && m.checked !== isEnabled) m.checked = isEnabled;
  if (s && s.checked !== isEnabled) s.checked = isEnabled;

  const delay = parseInt(document.getElementById('antiratelimit-delay-slider')?.value || '60', 10);
  const jitter = parseInt(document.getElementById('antiratelimit-jitter-slider')?.value || '5', 10);
  const reduceThreads = Boolean(document.getElementById('antiratelimit-reduce-threads')?.checked);

  const minWait = Math.max(1, delay - jitter);
  const maxWait = delay + jitter;

  const previewVal = document.getElementById('pacing-preview-value');
  if (previewVal) {
    previewVal.textContent = `${minWait}s – ${maxWait}s`;
  }

  const box = document.getElementById('antiratelimit-feature-box');
  if (box) {
    box.classList.toggle('active', isEnabled);
  }
}

// Quick format bar label sync
function updateQuickFormatBar() {
  const vqVal = ddVideo ? ddVideo.value : (document.getElementById('vq')?.value || '1080p');
  const aqVal = ddAudioQual ? ddAudioQual.value : (document.getElementById('aq')?.value || '192k');
  const alVal = ddAudio ? ddAudio.value : (document.getElementById('al')?.value || 'ja-JP');
  const slVal = ddSubs ? ddSubs.value : (document.getElementById('sl')?.value || 'en-US');

  const vqEl = document.getElementById('qf-vq');
  if (vqEl) vqEl.textContent = vqVal === 'none' ? 'audio only' : vqVal;

  const aqEl = document.getElementById('qf-aq');
  if (aqEl) aqEl.textContent = aqVal;

  const langsEl = document.getElementById('qf-langs');
  if (langsEl) {
    const alLabel = alVal === 'all' ? 'All Audios' : (alVal.includes(',') ? alVal.split(',')[0] + ' +' : alVal);
    const slLabel = slVal === 'all' ? 'All Subs' : (slVal.includes(',') ? slVal.split(',')[0] + ' +' : slVal);
    langsEl.textContent = `${alLabel} [${slLabel}]`;
  }
}

// Partials cache status
async function updatePartialsCacheStatus() {
  const el = document.getElementById('cache-stats-text');
  if (!el) return;
  try {
    const res = await api('/api/partials/status');
    if (res && res.success) {
      if (res.episodes_count > 0) {
        el.textContent = `${res.size_mb} MB across ${res.episodes_count} episode(s)`;
      } else {
        el.textContent = 'empty (0 MB)';
      }
    } else {
      el.textContent = 'cache status unavailable';
    }
  } catch (e) {
    el.textContent = 'could not load cache stats';
  }
}

// Clean partials cache
async function cleanPartialsCache() {
  const btn = document.getElementById('btn-clean-cache');
  const origText = btn ? btn.textContent : 'clear cache';
  if (btn) {
    btn.disabled = true;
    btn.textContent = 'clearing...';
  }
  try {
    const res = await api('/api/partials/clean', {});
    if (res && res.success) {
      const msg = `Freed ${res.freed_mb} MB (${res.cleaned_count} episode(s))`;
      toast(msg, 'ok');
      updatePartialsCacheStatus();
    } else {
      toast(res?.error || 'failed to clear cache', 'err');
    }
  } catch (e) {
    toast('error clearing cache: ' + e.message, 'err');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = origText;
    }
  }
}

// Purge orphan stream tokens on Crunchyroll
async function purgeZombieSessions() {
  const btn = document.getElementById('btn-purge-sessions');
  const origText = btn ? btn.textContent : 'clear streams';
  if (btn) {
    btn.disabled = true;
    btn.textContent = 'clearing...';
  }
  try {
    const res = await api('/api/sessions/purge', {});
    if (res && res.success) {
      toast(`Cleared ${res.purged} active stream(s)`, 'ok');
    } else {
      toast(res?.error || 'failed to clear streams', 'err');
    }
  } catch (e) {
    toast('purge error: ' + e.message, 'err');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = origText;
    }
  }
}

// Open native file explorer to the logs folder
async function openLogFolder() {
  const btn = document.getElementById('btn-open-log-dir');
  const origText = btn ? btn.textContent : 'open folder';
  if (btn) {
    btn.disabled = true;
    btn.textContent = 'opening...';
  }
  try {
    const res = await api('/api/logs/open-folder', {});
    if (res && res.success) {
      toast('Opened logs directory', 'ok');
    } else {
      const state = await api('/api/state');
      const p = state?.log_path || res?.path;
      if (p && navigator.clipboard) {
        await navigator.clipboard.writeText(p);
        toast('Could not open file manager. Path copied to clipboard.', 'err');
      } else {
        toast('Failed to open logs directory', 'err');
      }
    }
  } catch (e) {
    toast('Error opening logs: ' + e.message, 'err');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = origText;
    }
  }
}

// Copy recent log file content to clipboard
async function copyLogContent() {
  const btn = document.getElementById('btn-copy-log');
  const origText = btn ? btn.textContent : 'copy log';
  if (btn) {
    btn.disabled = true;
    btn.textContent = 'copying...';
  }
  try {
    const res = await api('/api/logs/content');
    if (res && res.success && res.content) {
      let copied = false;
      if (navigator.clipboard && navigator.clipboard.writeText) {
        try {
          await navigator.clipboard.writeText(res.content);
          copied = true;
        } catch (_) {}
      }
      if (!copied) {
        await api('/api/clipboard/copy', { text: res.content });
        copied = true;
      }
      toast('Copied recent logs to clipboard', 'ok');
    } else {
      toast('No log content found or log is empty', 'err');
    }
  } catch (e) {
    toast('Error copying logs: ' + e.message, 'err');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = origText;
    }
  }
}

// Copy full log file path to clipboard
async function copyLogPath() {
  const el = document.getElementById('log-path-display');
  const p = el?.textContent?.trim();
  if (p && p !== 'checking log path...') {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      try {
        await navigator.clipboard.writeText(p);
      } catch (_) {
        await api('/api/clipboard/copy', { text: p });
      }
    } else {
      await api('/api/clipboard/copy', { text: p });
    }
    toast('Copied log path to clipboard', 'ok');
  }
}

// Check for newer GitHub releases
async function checkForUpdates(manual = false) {
  const btn = document.getElementById('btn-check-updates');
  const origBtnText = btn ? btn.textContent : 'check for updates';
  if (manual && btn) {
    btn.disabled = true;
    btn.textContent = 'checking...';
  }

  try {
    const endpoint = manual ? '/api/version/check?force=1' : '/api/version/check';
    const res = await api(endpoint);

    if (res && res.success) {
      const badge = document.getElementById('update-badge');
      const updateTxt = document.getElementById('update-text');
      const verDisplay = document.getElementById('version-display');

      if (verDisplay && res.current_version) {
        verDisplay.textContent = 'v' + res.current_version;
      }

      if (res.has_update) {
        if (badge) {
          badge.href = res.release_url || 'https://github.com/Vure-sh/crunchyroller/releases/latest';
          if (updateTxt) {
            updateTxt.textContent = `v${res.latest_version} available`;
          }
          badge.style.display = 'inline-flex';
        }
        if (manual) {
          toast(`Update v${res.latest_version} available!`, 'ok');
        }
      } else {
        if (badge) {
          badge.style.display = 'none';
        }
        if (manual) {
          toast(`You are on the latest version (v${res.current_version})`, 'ok');
        }
      }
    } else if (manual) {
      toast(res?.error || 'Could not check for updates', 'err');
    }
  } catch (err) {
    if (manual) {
      toast('Update check failed: ' + err.message, 'err');
    }
  } finally {
    if (manual && btn) {
      btn.disabled = false;
      btn.textContent = origBtnText;
    }
  }
}

// Resume interrupted downloads
async function resumeInterrupted() {
  const btn = document.getElementById('btn-resume-interrupted');
  if (btn) {
    btn.disabled = true;
    btn.textContent = 'resuming...';
  }
  try {
    const res = await api('/api/queue/resume-interrupted', {});
    if (res && res.success) {
      toast(`Resumed ${res.resumed || 0} interrupted episode(s)`, 'ok');
      startPolling();
      const state = await api('/api/state');
      if (state && state.download) updateProgressPanel(state.download);
    } else {
      toast(res?.error || 'failed to resume interrupted', 'err');
    }
  } catch (e) {
    toast('resume error: ' + e.message, 'err');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = 'resume interrupted';
    }
  }
}

// Retry failed downloads
async function retryFailed() {
  const btn = document.getElementById('btn-retry-failed');
  if (btn) {
    btn.disabled = true;
    btn.textContent = 'retrying...';
  }
  try {
    const res = await api('/api/queue/retry-failed', {});
    if (res && res.success) {
      toast(`Re-queued ${res.retried || 0} failed episode(s)`, 'ok');
      startPolling();
      const state = await api('/api/state');
      if (state && state.download) updateProgressPanel(state.download);
    } else {
      toast(res?.error || 'failed to retry episodes', 'err');
    }
  } catch (e) {
    toast('retry error: ' + e.message, 'err');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = 'retry failed';
    }
  }
}

// Clear download history
async function clearHistory() {
  const list = document.getElementById('history-list');
  try {
    const res = await api('/api/queue/history/clear', { method: 'POST' });
    if (res && res.success) {
      if (list) list.innerHTML = '<div class="history-empty">no downloads yet</div>';
      loadHistory();
    }
  } catch (e) {
    console.error('clearHistory error:', e);
  }
}

function getHistorySeriesTitle(item) {
  if (item.series_title && item.series_title.trim() && item.series_title.toLowerCase() !== 'unknown') {
    return item.series_title.trim();
  }
  if (item.output_file) {
    const norm = item.output_file.replace(/\\/g, '/');
    const parts = norm.split('/').filter(Boolean);
    const animeIdx = parts.lastIndexOf('anime');
    if (animeIdx !== -1 && animeIdx + 1 < parts.length) {
      return parts[animeIdx + 1];
    }
    if (parts.length >= 3) {
      return parts[parts.length - 3];
    }
    const fileName = parts[parts.length - 1] || '';
    const dashMatch = fileName.match(/^(.*?)\s*-\s*S\d+/i);
    if (dashMatch) return dashMatch[1].trim();
  }
  if (item.season_title && item.season_title.trim()) {
    return item.season_title.trim();
  }
  if (item.label) {
    const m = item.label.match(/^(.*?)\s*[-—]\s*S\d+/i);
    if (m && m[1].trim()) return m[1].trim();
  }
  return 'Anime';
}

function getHistoryEpTag(item) {
  if (item.season_number && item.episode_number) {
    return `S${String(item.season_number).padStart(2, '0')}E${String(item.episode_number).padStart(2, '0')}`;
  }
  if (item.label) {
    const m = item.label.match(/S\d+E\d+/i);
    if (m) return m[0].toUpperCase();
  }
  if (item.episode_number) {
    return `EP ${item.episode_number}`;
  }
  return '';
}

function getHistoryEpTitle(item) {
  if (item.title && item.title.trim() && item.title !== item.ep_id) {
    return item.title.trim();
  }
  if (item.label) {
    const cleaned = item.label.replace(/^S\d+E\d+\s*[-—]\s*/i, '').trim();
    if (cleaned) return cleaned;
    return item.label;
  }
  return item.ep_id || '';
}

function formatRelativeTime(timestamp) {
  if (!timestamp) return '';
  const ts = timestamp * (timestamp < 1e11 ? 1000 : 1);
  const diffSec = Math.floor((Date.now() - ts) / 1000);
  if (diffSec < 0) return 'just now';
  if (diffSec < 60) return `${diffSec}s ago`;
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHour = Math.floor(diffMin / 60);
  if (diffHour < 24) return `${diffHour}h ago`;
  const diffDay = Math.floor(diffHour / 24);
  if (diffDay < 7) return `${diffDay}d ago`;
  const d = new Date(ts);
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

// Load completed and canceled history
async function loadHistory() {
  const list = document.getElementById('history-list');
  if (!list) return;
  try {
    const res = await api('/api/queue/history');
    if (res && res.success && res.history) {
      if (res.history.length === 0) {
        list.innerHTML = '<div class="history-empty">no downloads yet</div>';
        return;
      }
      list.innerHTML = '';
      res.history.slice(0, 40).forEach(item => {
        const row = document.createElement('div');
        row.className = 'history-row';

        const left = document.createElement('div');
        left.className = 'history-left';

        // Line 1: [Icon] Series Title [Badge]
        const topLine = document.createElement('div');
        topLine.className = 'history-top-line';

        const statusIco = document.createElement('span');
        statusIco.className = `ep-ico ep-ico-${item.status === 'completed' ? 'done' : 'err'}`;
        statusIco.textContent = item.status === 'completed' ? '✓' : (item.status === 'canceled' ? '✕' : (item.status === 'skipped' ? '↷' : '!'));

        const seriesTitle = getHistorySeriesTitle(item);
        const seriesEl = document.createElement('span');
        seriesEl.className = 'history-series';
        seriesEl.textContent = seriesTitle;
        seriesEl.title = seriesTitle;

        topLine.append(statusIco, seriesEl);

        const epTag = getHistoryEpTag(item);
        if (epTag) {
          const epTagEl = document.createElement('span');
          epTagEl.className = 'history-ep-tag';
          epTagEl.textContent = epTag;
          topLine.appendChild(epTagEl);
        }

        // Line 2: Episode Title • Quality • Time
        const subLine = document.createElement('div');
        subLine.className = 'history-sub-line';

        const epTitle = getHistoryEpTitle(item);
        const epTitleEl = document.createElement('span');
        epTitleEl.className = 'history-ep-title';
        epTitleEl.textContent = epTitle;
        epTitleEl.title = epTitle;
        subLine.appendChild(epTitleEl);

        if (item.video_quality) {
          const sep = document.createElement('span');
          sep.className = 'history-sep';
          sep.textContent = '•';
          const qualEl = document.createElement('span');
          qualEl.className = 'history-quality';
          qualEl.textContent = item.video_quality === 'none' ? 'audio only' : item.video_quality;
          subLine.append(sep, qualEl);
        }

        const relTime = formatRelativeTime(item.finished_at);
        if (relTime) {
          const sep = document.createElement('span');
          sep.className = 'history-sep';
          sep.textContent = '•';
          const timeEl = document.createElement('span');
          timeEl.className = 'history-time';
          timeEl.textContent = relTime;
          subLine.append(sep, timeEl);
        }

        left.append(topLine, subLine);

        // Right side: [Size] [Status Pill] [Folder Button]
        const right = document.createElement('div');
        right.className = 'history-right';

        if (item.file_size_mb) {
          const sz = document.createElement('span');
          sz.className = 'history-size';
          sz.textContent = `${item.file_size_mb} MB`;
          right.appendChild(sz);
        }

        const pill = document.createElement('span');
        pill.className = `task-ep-status-pill status-${item.status}`;
        pill.textContent = item.status;
        right.appendChild(pill);

        if (item.status === 'completed') {
          const openBtn = document.createElement('button');
          openBtn.className = 'btn-history-open';
          openBtn.title = 'Open file / show in folder';
          openBtn.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>';
          openBtn.onclick = (e) => {
            e.stopPropagation();
            openDownloadFolder(item.output_file || '');
          };
          right.appendChild(openBtn);
        }

        row.append(left, right);
        list.appendChild(row);
      });
    }
  } catch (e) {
    console.error('loadHistory error:', e);
  }
}

// open native directory chooser
async function browseDirectory() {
  const btn = document.getElementById('browse-dir-btn');
  const origText = btn ? btn.textContent : 'browse';
  if (btn) {
    btn.disabled = true;
    btn.textContent = '...';
  }
  try {
    const res = await api('/api/choose-directory', {});
    if (res.success && res.download_dir) {
      const input = document.getElementById('download-dir');
      if (input) input.value = res.download_dir;
      toast('download folder set: ' + res.download_dir, 'ok');
    } else if (res.cancelled) {
      // User closed or cancelled folder picker
    } else {
      toast(res.error || 'could not open folder picker', 'err');
    }
  } catch (err) {
    toast('failed to open folder picker', 'err');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = origText;
    }
  }
}

// open native download folder or revealed file in host file manager
async function openDownloadFolder(customPath = '') {
  try {
    const payload = customPath ? { path: customPath } : {};
    const res = await api('/api/downloads/open-folder', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    if (!res || !res.success) {
      toast(res?.error || 'could not open folder', 'err');
    }
  } catch (err) {
    toast('failed to open folder: ' + err.message, 'err');
  }
}

let currentInputMode = 'search';
let lastSelectedSeries = null;

function setInputMode(mode) {
  currentInputMode = mode;
  const searchTab = document.getElementById('tab-mode-search');
  const urlTab = document.getElementById('tab-mode-url');
  const searchSec = document.getElementById('search-section');
  const urlSec = document.getElementById('url-section');

  if (mode === 'search') {
    if (searchTab) searchTab.classList.add('active');
    if (urlTab) urlTab.classList.remove('active');
    if (searchSec) searchSec.style.display = 'block';
    if (urlSec) urlSec.style.display = 'none';
    const sIn = document.getElementById('search-input');
    if (sIn) sIn.focus();
  } else {
    if (urlTab) urlTab.classList.add('active');
    if (searchTab) searchTab.classList.remove('active');
    if (urlSec) urlSec.style.display = 'block';
    if (searchSec) searchSec.style.display = 'none';
    const uIn = document.getElementById('url');
    if (uIn) uIn.focus();
  }
}

function clearSearch() {
  const input = document.getElementById('search-input');
  if (input) {
    input.value = '';
    input.focus();
  }
  const clearBtn = document.getElementById('search-clear-btn');
  if (clearBtn) clearBtn.style.display = 'none';
  const panel = document.getElementById('search-results-panel');
  if (panel) panel.style.display = 'none';
}

function closeSearchResults() {
  const panel = document.getElementById('search-results-panel');
  if (panel) panel.style.display = 'none';
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

async function searchSeries() {
  const input = document.getElementById('search-input');
  if (!input) return;
  const query = input.value.trim();
  if (!query) {
    toast('enter a series title to search', 'err');
    return;
  }

  // If user pasted a Crunchyroll URL into the search box, redirect to URL fetch
  if (/^https?:\/\//i.test(query) || query.includes('crunchyroll.com/')) {
    setInputMode('url');
    const urlInput = document.getElementById('url');
    if (urlInput) urlInput.value = query;
    fetchUrl();
    return;
  }

  const btn = document.getElementById('search-btn');
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<span class="spin"></span>';
  }

  try {
    const res = await api('/api/search', { q: query, n: 15 });
    if (!res || !res.success) {
      toast(res?.error || 'search failed', 'err');
      return;
    }
    renderSearchResults(res.results || [], query);
  } catch (err) {
    toast('search error: ' + err.message, 'err');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = 'search';
    }
  }
}

let selectedSearchIds = new Set();

function updateSearchSelectedCount() {
  const count = selectedSearchIds.size;
  const fetchBtn = document.getElementById('search-fetch-selected-btn');
  const autodlBtn = document.getElementById('search-autodl-selected-btn');
  const noneBtn = document.getElementById('search-select-none-btn');
  if (fetchBtn) {
    fetchBtn.textContent = `fetch selected (${count})`;
    fetchBtn.style.display = count > 0 ? 'inline-flex' : 'none';
  }
  if (autodlBtn) {
    autodlBtn.textContent = `auto-dl selected (${count})`;
    autodlBtn.style.display = count > 0 ? 'inline-flex' : 'none';
  }
  if (noneBtn) {
    noneBtn.style.display = count > 0 ? 'inline-flex' : 'none';
  }
}

function toggleSelectAllSearchResults(select) {
  const cbs = document.querySelectorAll('.search-select-cb');
  cbs.forEach(cb => {
    cb.checked = select;
    const card = cb.closest('.search-result-card');
    if (card) card.classList.toggle('selected', select);
    const id = cb.dataset.id;
    if (select) {
      selectedSearchIds.add(id);
    } else {
      selectedSearchIds.delete(id);
    }
  });
  updateSearchSelectedCount();
}

async function fetchSelectedSearchAnime() {
  if (!selectedSearchIds.size) return;
  const urls = Array.from(selectedSearchIds).map(id => `https://www.crunchyroll.com/series/${id}`);
  closeSearchResults();
  await fetchUrl(urls, true);
}

async function monitorSelectedSearchAnime() {
  const ids = Array.from(selectedSearchIds);
  if (!ids.length) return;
  toast(`Enabling auto-download for ${ids.length} show(s)...`, 'info');

  let successCount = 0;
  for (const sid of ids) {
    try {
      const res = await api('/api/watcher/monitor', {
        series_id: sid,
        mode: 'latest_only',
      });
      if (res && res.success) {
        monitoredSeriesMap.set(sid, res.series);
        successCount++;
      }
    } catch (_) {}
  }
  selectedSearchIds.clear();
  toggleSelectAllSearchResults(false);
  updateSearchSelectedCount();
  toast(`Auto-download enabled for ${successCount} show(s)!`, 'ok');
  syncAllMonitoredCards();
  const sRes = await api('/api/watcher/status');
  if (sRes && sRes.success) updateWatcherState(sRes);
}

function renderSearchResults(results, query) {
  const panel = document.getElementById('search-results-panel');
  const statusEl = document.getElementById('search-results-status');
  const listEl = document.getElementById('search-results-list');
  if (!panel || !statusEl || !listEl) return;

  panel.style.display = 'block';
  listEl.innerHTML = '';
  selectedSearchIds.clear();
  updateSearchSelectedCount();

  if (!results.length) {
    statusEl.textContent = `no anime found for "${query}"`;
    return;
  }

  statusEl.textContent = `found ${results.length} result(s) for "${query}"`;

  results.forEach(item => {
    const card = document.createElement('div');
    card.className = 'search-result-card';
    card.setAttribute('tabindex', '0');
    card.setAttribute('role', 'button');

    let posterHtml = '';
    if (item.poster) {
      posterHtml = `<img class="res-poster" src="${escapeHtml(item.poster)}" alt="${escapeHtml(item.title)}" loading="lazy" onerror="this.style.opacity='0.2'">`;
    } else {
      posterHtml = `<div class="res-poster res-poster-empty"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg></div>`;
    }

    const badges = [];
    if (item.type === 'movie_listing') {
      badges.push('<span class="res-badge res-badge-movie">movie</span>');
    } else {
      badges.push('<span class="res-badge">series</span>');
    }

    if (item.season_count > 0) {
      badges.push(`<span class="res-badge">${item.season_count} ${item.season_count === 1 ? 'season' : 'seasons'}</span>`);
    }
    if (item.episode_count > 0) {
      badges.push(`<span class="res-badge">${item.episode_count} ep</span>`);
    }
    if (item.year) {
      badges.push(`<span class="res-badge">${item.year}</span>`);
    }
    if (item.is_subbed) {
      badges.push('<span class="res-badge res-badge-sub">SUB</span>');
    }
    if (item.is_dubbed) {
      badges.push('<span class="res-badge res-badge-dub">DUB</span>');
    }

    const desc = item.description || '';

    const isMonitored = monitoredSeriesMap.has(item.id);

    card.innerHTML = `
      <div class="search-card-cb-wrap">
        <input type="checkbox" class="cb-custom search-select-cb" data-id="${escapeHtml(item.id)}" title="Select anime">
      </div>
      ${posterHtml}
      <div class="res-content">
        <div class="res-title-row">
          <div class="res-title" title="${escapeHtml(item.title)}">${escapeHtml(item.title)}</div>
        </div>
        <div class="res-badges">${badges.join('')}</div>
        ${desc ? `<div class="res-desc" title="${escapeHtml(desc)}">${escapeHtml(desc)}</div>` : ''}
        <div class="res-actions">
          <button type="button" class="btn-s ${isMonitored ? 'btn-monitor-active' : 'btn-monitor'} search-autodl-btn" data-id="${escapeHtml(item.id)}" data-title="${escapeHtml(item.title)}" data-poster="${escapeHtml(item.poster || '')}" title="${isMonitored ? 'Auto-download active. Click to stop.' : 'Auto-download new episodes when they air'}">${isMonitored ? 'auto-dl ✓' : 'auto-dl'}</button>
          <button type="button" class="btn-s res-btn">fetch series</button>
        </div>
      </div>
    `;

    const cb = card.querySelector('.search-select-cb');
    if (cb) {
      cb.addEventListener('click', (e) => {
        e.stopPropagation();
        if (cb.checked) {
          selectedSearchIds.add(item.id);
          card.classList.add('selected');
        } else {
          selectedSearchIds.delete(item.id);
          card.classList.remove('selected');
        }
        updateSearchSelectedCount();
      });
    }

    const autodlBtn = card.querySelector('.search-autodl-btn');
    if (autodlBtn) {
      autodlBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        toggleMonitorSeries(e, item.id, item.title, null, item.poster);
      });
    }

    const fetchBtn = card.querySelector('.res-btn');
    if (fetchBtn) {
      fetchBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        selectSeries(item, true);
      });
    }

    const handleCardClick = (e) => {
      if (e.target.closest('button') || e.target.closest('.search-card-cb-wrap')) return;
      if (cb) {
        cb.checked = !cb.checked;
        if (cb.checked) {
          selectedSearchIds.add(item.id);
          card.classList.add('selected');
        } else {
          selectedSearchIds.delete(item.id);
          card.classList.remove('selected');
        }
        updateSearchSelectedCount();
      } else {
        selectSeries(item, false);
      }
    };

    card.addEventListener('click', handleCardClick);
    card.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        handleCardClick(e);
      }
    });

    listEl.appendChild(card);
  });
}

function selectSeries(item, append = false) {
  lastSelectedSeries = item;
  const targetUrl = `https://www.crunchyroll.com/series/${item.id}`;
  const urlInput = document.getElementById('url');
  if (urlInput && !append) {
    urlInput.value = targetUrl;
    autoResizeUrlTextarea(urlInput);
  }
  document.querySelectorAll('.search-result-card').forEach(c => c.classList.remove('selected'));
  fetchUrl(targetUrl, append);
}

// Global list of currently loaded anime objects
let loadedAnimeList = [];

// fetch URL metadata & show episode tree (supports single or multiple URLs)
async function fetchUrl(overrideUrls = null, appendMode = false) {
  let urlsToFetch = [];
  if (overrideUrls) {
    urlsToFetch = Array.isArray(overrideUrls) ? overrideUrls : [overrideUrls];
  } else {
    const urlInput = document.getElementById('url');
    const raw = (urlInput ? urlInput.value : '').trim();
    if (!raw) {
      toast('paste crunchyroll url(s) or search for a series', 'err');
      return;
    }
    urlsToFetch = raw.split(/[\r\n,;]+/).map(u => u.trim()).filter(Boolean);
  }

  if (!urlsToFetch.length) {
    toast('no valid URLs provided', 'err');
    return;
  }

  const btn = document.getElementById('fetch-btn');
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<span class="spin"></span> ${urlsToFetch.length > 1 ? `fetching ${urlsToFetch.length}...` : 'fetching...'}`;
  }

  try {
    const res = await api('/api/fetch', { urls: urlsToFetch });
    if (!res || !res.success) {
      toast(res?.error || 'fetch failed', 'err');
      return;
    }

    const fetched = res.animes || (res.seasons ? [res] : []);
    if (!fetched.length) {
      toast('no anime found for provided URLs', 'err');
      return;
    }

    renderEpisodeTree(fetched, appendMode);

    if (fetched.length === 1) {
      toast(fetched[0].title || 'Fetched anime', 'ok');
    } else {
      toast(`Fetched ${fetched.length} animes successfully`, 'ok');
    }

    if (res.errors && res.errors.length) {
      toast(`${res.errors.length} URL(s) failed to fetch`, 'err');
    }

    const treeEl = document.getElementById('tree');
    if (treeEl) {
      treeEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  } catch (err) {
    toast('fetch error: ' + err.message, 'err');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = 'fetch';
    }
  }
}

function clearTree() {
  loadedAnimeList = [];
  const list = document.getElementById('sn-list');
  if (list) list.innerHTML = '';
  const treeEl = document.getElementById('tree');
  if (treeEl) treeEl.style.display = 'none';
  const summaryEl = document.getElementById('tree-summary-bar');
  if (summaryEl) summaryEl.style.display = 'none';
  const headerEl = document.getElementById('tree-series-header');
  if (headerEl) headerEl.style.display = 'none';
  updateTotalCount();
}

function removeAnimeFromTree(animeId) {
  loadedAnimeList = loadedAnimeList.filter(a => String(a.id || a.title) !== String(animeId));
  const block = document.querySelector(`.anime-tree-block[data-anime-id="${animeId}"]`);
  if (block) block.remove();

  if (loadedAnimeList.length === 0) {
    clearTree();
  } else {
    updateMultiAnimeTreeHeaders();
    updateTotalCount();
  }
}

function updateExpandAllBtnText() {
  const blocks = document.querySelectorAll('.sn-block, .anime-tree-block');
  const btn = document.getElementById('toggle-seasons-btn');
  if (!blocks.length || !btn) return;
  const anyCollapsed = [...blocks].some(b => b.classList.contains('collapsed'));
  btn.textContent = anyCollapsed ? 'expand all' : 'collapse all';
}

// toggle expand/collapse all seasons across all anime
function toggleAllSeasons() {
  const blocks = document.querySelectorAll('.sn-block, .anime-tree-block');
  const btn = document.getElementById('toggle-seasons-btn');
  if (!blocks.length) return;
  const anyCollapsed = [...blocks].some(b => b.classList.contains('collapsed'));
  blocks.forEach(b => {
    b.classList.toggle('collapsed', !anyCollapsed);
    const chev = b.querySelector('.anime-chevron');
    if (chev) {
      chev.style.transform = (!anyCollapsed) ? 'rotate(-90deg)' : '';
    }
  });
  if (btn) btn.textContent = anyCollapsed ? 'collapse all' : 'expand all';
}

function updateMultiAnimeTreeHeaders() {
  const headerEl = document.getElementById('tree-series-header');
  const summaryEl = document.getElementById('tree-summary-bar');
  const summaryInfo = document.getElementById('tree-summary-info');
  const titleEl = document.getElementById('ser-title');

  if (loadedAnimeList.length === 1) {
    const data = loadedAnimeList[0];
    if (titleEl) titleEl.textContent = data.title;
    if (summaryEl) summaryEl.style.display = 'none';

    if (headerEl) {
      const posterImg = document.getElementById('tree-poster');
      const badgesEl = document.getElementById('tree-series-badges');
      const descEl = document.getElementById('tree-series-desc');
      const posterSrc = data.poster || (lastSelectedSeries && lastSelectedSeries.poster) || '';

      if (posterSrc && posterImg) {
        posterImg.src = posterSrc;
        posterImg.style.display = 'block';
      } else if (posterImg) {
        posterImg.style.display = 'none';
      }

      if (badgesEl) {
        const totalSn = data.seasons ? data.seasons.length : 0;
        let totalEp = 0;
        if (data.seasons) {
          data.seasons.forEach(s => totalEp += (s.episodes ? s.episodes.length : 0));
        }
        const bList = [];
        if (totalSn > 0) bList.push(`<span class="res-badge">${totalSn} ${totalSn === 1 ? 'season' : 'seasons'}</span>`);
        if (totalEp > 0) bList.push(`<span class="res-badge">${totalEp} episodes</span>`);
        if (data.year || (lastSelectedSeries && lastSelectedSeries.year)) {
          bList.push(`<span class="res-badge">${data.year || lastSelectedSeries.year}</span>`);
        }
        badgesEl.innerHTML = bList.join('');
      }

      if (descEl) {
        const descText = data.description || (lastSelectedSeries && lastSelectedSeries.description) || '';
        descEl.textContent = descText;
        descEl.style.display = descText ? 'block' : 'none';
      }
      headerEl.style.display = 'flex';
    }
  } else if (loadedAnimeList.length > 1) {
    if (headerEl) headerEl.style.display = 'none';
    if (summaryEl) {
      let totalSn = 0;
      let totalEp = 0;
      loadedAnimeList.forEach(a => {
        totalSn += (a.seasons ? a.seasons.length : 0);
        (a.seasons || []).forEach(s => totalEp += (s.episodes ? s.episodes.length : 0));
      });
      if (summaryInfo) {
        summaryInfo.textContent = `${loadedAnimeList.length} anime • ${totalSn} seasons • ${totalEp} episodes`;
      }
      summaryEl.style.display = 'flex';
    }
    if (titleEl) titleEl.textContent = `${loadedAnimeList.length} Anime Loaded`;
  }
}

function renderSeasonBlock(season, animeTitle, sIdx, animeId) {
  const block = document.createElement('div');
  block.className = 'sn-block collapsed';
  block.dataset.seasonId = season.id || String(sIdx);
  if (animeId) block.dataset.animeId = animeId;

  // season header
  const head = document.createElement('div');
  head.className = 'sn-head';

  const cbWrap = document.createElement('div');
  cbWrap.className = 'sn-cb-wrap';

  const seasonCb = document.createElement('input');
  seasonCb.type = 'checkbox';
  seasonCb.className = 'cb-custom sn-cb';
  seasonCb.checked = true;
  seasonCb.id = 's_' + (animeId ? animeId + '_' : '') + sIdx;

  cbWrap.appendChild(seasonCb);

  const titleWrap = document.createElement('div');
  titleWrap.className = 'sn-title-wrap';

  const label = document.createElement('span');
  label.className = 'sn-title';

  let snName = (season.title || '').trim();
  if (animeTitle && snName.toLowerCase().startsWith(animeTitle.toLowerCase())) {
    snName = snName.slice(animeTitle.length).replace(/^[\s:–—-]+/, '').trim();
  }
  if (!snName) {
    snName = season.season_number > 0 ? `Season ${season.season_number}` : 'Specials & Movies';
  } else if (season.season_number === 0 && !snName.toLowerCase().includes('special') && !snName.toLowerCase().includes('movie')) {
    snName = `Specials • ${snName}`;
  } else if (season.season_number > 0 && !snName.toLowerCase().startsWith('season') && !snName.toLowerCase().startsWith('s' + season.season_number)) {
    snName = `S${season.season_number} • ${snName}`;
  }
  label.textContent = snName;

  const count = document.createElement('span');
  count.className = 'sn-count';
  count.textContent = (season.episodes ? season.episodes.length : 0) + ' ep';

  titleWrap.append(label, count);

  const chevron = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  chevron.setAttribute('class', 'sn-chevron');
  chevron.setAttribute('width', '10');
  chevron.setAttribute('height', '10');
  chevron.setAttribute('viewBox', '0 0 10 10');
  chevron.setAttribute('fill', 'none');
  chevron.innerHTML = '<path d="M3.5 1.5L7 5L3.5 8.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>';

  head.append(cbWrap, titleWrap, chevron);

  // episode rows
  const epList = document.createElement('div');
  epList.className = 'ep-list';

  cbWrap.addEventListener('click', (e) => {
    e.stopPropagation();
    const epCbs = [...epList.querySelectorAll('.epc')];
    const allChecked = epCbs.length > 0 && epCbs.every(c => c.checked);
    const shouldCheck = !allChecked;

    seasonCb.checked = shouldCheck;
    seasonCb.indeterminate = false;

    epCbs.forEach(cb => {
      cb.checked = shouldCheck;
      const row = cb.closest('.ep-row');
      if (row) row.classList.toggle('selected', shouldCheck);
    });
    updateSeasonState(block);
    const animeBlock = block.closest('.anime-tree-block');
    if (animeBlock) updateAnimeState(animeBlock);
    updateTotalCount();
  });

  head.addEventListener('click', () => {
    block.classList.toggle('collapsed');
    updateExpandAllBtnText();
  });

  (season.episodes || []).forEach(ep => {
    const row = document.createElement('div');
    row.className = 'ep-row selected';

    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.checked = true;
    cb.className = 'cb-custom epc';
    cb.dataset.id = ep.id;
    cb.dataset.title = ep.title || '';
    cb.dataset.epNum = ep.episode_number || '';
    cb.dataset.snNum = ep.season_number || '';
    cb.dataset.series = ep.series_title || animeTitle || '';
    cb.dataset.seasonTitle = ep.season_title || season.title || '';
    if (animeId) cb.dataset.animeId = animeId;
    cb.tabIndex = -1;

    const num = document.createElement('span');
    num.className = 'ep-num';
    num.textContent = 'E' + String(ep.episode_number).padStart(2, '0');

    const name = document.createElement('span');
    name.className = 'ep-name';
    name.textContent = ep.title;

    row.addEventListener('click', (e) => {
      if (e.target !== cb) {
        cb.checked = !cb.checked;
      }
      row.classList.toggle('selected', cb.checked);
      updateSeasonState(block);
      const animeBlock = block.closest('.anime-tree-block');
      if (animeBlock) updateAnimeState(animeBlock);
      updateTotalCount();
    });

    row.append(cb, num, name);
    epList.appendChild(row);
  });

  block.append(head, epList);
  updateSeasonState(block);
  return block;
}

function updateAnimeState(animeBlock) {
  const animeCb = animeBlock.querySelector('.anime-cb');
  if (!animeCb) return;
  const epCbs = [...animeBlock.querySelectorAll('.epc')];
  const total = epCbs.length;
  const checked = epCbs.filter(c => c.checked).length;

  if (checked === 0) {
    animeCb.checked = false;
    animeCb.indeterminate = false;
  } else if (checked === total) {
    animeCb.checked = true;
    animeCb.indeterminate = false;
  } else {
    animeCb.checked = false;
    animeCb.indeterminate = true;
  }
}

function setAnimeEpisodesChecked(animeBlock, shouldCheck) {
  const animeCb = animeBlock.querySelector('.anime-cb');
  if (animeCb) {
    animeCb.checked = shouldCheck;
    animeCb.indeterminate = false;
  }
  animeBlock.querySelectorAll('.sn-block').forEach(snBlock => {
    const snCb = snBlock.querySelector('.sn-cb');
    if (snCb) { snCb.checked = shouldCheck; snCb.indeterminate = false; }
    snBlock.querySelectorAll('.epc').forEach(cb => {
      cb.checked = shouldCheck;
      const row = cb.closest('.ep-row');
      if (row) row.classList.toggle('selected', shouldCheck);
    });
    updateSeasonState(snBlock);
  });
  updateAnimeState(animeBlock);
  updateTotalCount();
}

// render season and episode checkboxes (supports single or multiple anime)
function renderEpisodeTree(data, appendMode = false) {
  let incoming = [];
  if (Array.isArray(data)) {
    incoming = data;
  } else if (data && data.animes && Array.isArray(data.animes)) {
    incoming = data.animes;
  } else if (data) {
    incoming = [data];
  }

  if (appendMode && loadedAnimeList.length > 0) {
    const existingIds = new Set(loadedAnimeList.map(a => String(a.id || a.title)));
    incoming.forEach(a => {
      const key = String(a.id || a.title);
      if (!existingIds.has(key)) {
        loadedAnimeList.push(a);
        existingIds.add(key);
      }
    });
  } else {
    loadedAnimeList = incoming;
  }

  if (!loadedAnimeList.length) {
    clearTree();
    return;
  }

  const toggleBtn = document.getElementById('toggle-seasons-btn');
  if (toggleBtn) toggleBtn.textContent = 'expand all';

  updateMultiAnimeTreeHeaders();

  const list = document.getElementById('sn-list');
  list.innerHTML = '';

  const isMulti = loadedAnimeList.length > 1;

  loadedAnimeList.forEach((anime, aIdx) => {
    const animeTitle = anime.title || 'Anime';
    const seasons = anime.seasons || [];
    const animeId = String(anime.id || aIdx);

    if (isMulti) {
      const animeBlock = document.createElement('div');
      animeBlock.className = 'anime-tree-block';
      animeBlock.dataset.animeId = animeId;

      const animeHead = document.createElement('div');
      animeHead.className = 'anime-tree-head';

      const cbWrap = document.createElement('div');
      cbWrap.className = 'anime-cb-wrap';
      const animeCb = document.createElement('input');
      animeCb.type = 'checkbox';
      animeCb.className = 'cb-custom anime-cb';
      animeCb.checked = true;
      cbWrap.appendChild(animeCb);

      cbWrap.addEventListener('click', (e) => {
        e.stopPropagation();
        const epCbs = [...animeBlock.querySelectorAll('.epc')];
        const allChecked = epCbs.length > 0 && epCbs.every(c => c.checked);
        const shouldCheck = !allChecked;
        setAnimeEpisodesChecked(animeBlock, shouldCheck);
      });

      let posterHtml = '';
      if (anime.poster) {
        posterHtml = `<img class="anime-tree-poster" src="${escapeHtml(anime.poster)}" alt="" onerror="this.style.display='none'">`;
      }

      let totalAnimeEps = 0;
      seasons.forEach(s => totalAnimeEps += (s.episodes ? s.episodes.length : 0));

      const infoDiv = document.createElement('div');
      infoDiv.className = 'anime-tree-info';
      infoDiv.innerHTML = `
        <div class="anime-tree-title" title="${escapeHtml(animeTitle)}">${escapeHtml(animeTitle)}</div>
        <div class="anime-tree-badges">
          <span class="res-badge">${seasons.length} ${seasons.length === 1 ? 'season' : 'seasons'}</span>
          <span class="res-badge">${totalAnimeEps} ep</span>
        </div>
      `;

      const actionsDiv = document.createElement('div');
      actionsDiv.className = 'anime-tree-actions';

      const allBtn = document.createElement('button');
      allBtn.type = 'button';
      allBtn.className = 'btn-s';
      allBtn.textContent = 'all';
      allBtn.onclick = (e) => {
        e.stopPropagation();
        setAnimeEpisodesChecked(animeBlock, true);
      };

      const noneBtn = document.createElement('button');
      noneBtn.type = 'button';
      noneBtn.className = 'btn-s';
      noneBtn.textContent = 'none';
      noneBtn.onclick = (e) => {
        e.stopPropagation();
        setAnimeEpisodesChecked(animeBlock, false);
      };

      const removeBtn = document.createElement('button');
      removeBtn.type = 'button';
      removeBtn.className = 'anime-remove-btn';
      removeBtn.innerHTML = '&times;';
      removeBtn.title = 'Remove anime from list';
      removeBtn.onclick = (e) => {
        e.stopPropagation();
        removeAnimeFromTree(animeId);
      };

      const chevron = document.createElement('span');
      chevron.className = 'anime-chevron';
      chevron.textContent = '▼';

      actionsDiv.append(allBtn, noneBtn, removeBtn, chevron);

      animeHead.append(cbWrap);
      if (posterHtml) {
        const wrap = document.createElement('div');
        wrap.innerHTML = posterHtml;
        if (wrap.firstElementChild) animeHead.appendChild(wrap.firstElementChild);
      }
      animeHead.append(infoDiv, actionsDiv);

      animeHead.addEventListener('click', (e) => {
        if (e.target.closest('button') || e.target.closest('.anime-cb-wrap')) return;
        animeBlock.classList.toggle('collapsed');
        chevron.style.transform = animeBlock.classList.contains('collapsed') ? 'rotate(-90deg)' : '';
        updateExpandAllBtnText();
      });

      const animeBody = document.createElement('div');
      animeBody.className = 'anime-tree-body';

      seasons.forEach((season, sIdx) => {
        const sBlock = renderSeasonBlock(season, animeTitle, sIdx, animeId);
        animeBody.appendChild(sBlock);
      });

      animeBlock.append(animeHead, animeBody);
      list.appendChild(animeBlock);
      updateAnimeState(animeBlock);
    } else {
      // Single anime view: render season blocks directly in list
      seasons.forEach((season, sIdx) => {
        const sBlock = renderSeasonBlock(season, animeTitle, sIdx, animeId);
        list.appendChild(sBlock);
      });
    }
  });

  updateTotalCount();
  document.getElementById('tree').style.display = 'block';
}

function updateSeasonState(block) {
  const seasonCb = block.querySelector('.sn-cb');
  const epCbs = [...block.querySelectorAll('.epc')];
  const countEl = block.querySelector('.sn-count');

  const total = epCbs.length;
  const checked = epCbs.filter(c => c.checked).length;

  if (checked === 0) {
    seasonCb.checked = false;
    seasonCb.indeterminate = false;
  } else if (checked === total) {
    seasonCb.checked = true;
    seasonCb.indeterminate = false;
  } else {
    seasonCb.checked = false;
    seasonCb.indeterminate = true;
  }

  if (countEl) {
    countEl.textContent = checked === total ? `${total} ep` : `${checked}/${total} ep`;
  }
}

function updateTotalCount() {
  const allEps = document.querySelectorAll('.epc');
  const checkedEps = document.querySelectorAll('.epc:checked');
  const count = checkedEps.length;
  const total = allEps.length;

  const badge = document.getElementById('tree-selected-count');
  if (badge) badge.textContent = `${count} / ${total} selected`;
}

// select / deselect all episodes across all loaded animes
function pickAll(val) {
  document.querySelectorAll('.epc').forEach(cb => {
    cb.checked = val;
    const row = cb.closest('.ep-row');
    if (row) row.classList.toggle('selected', val);
  });
  document.querySelectorAll('.sn-block').forEach(block => updateSeasonState(block));
  document.querySelectorAll('.anime-tree-block').forEach(block => updateAnimeState(block));
  updateTotalCount();
}

// start batch download task across all selected anime episodes
async function startDl() {
  const selected = [...document.querySelectorAll('.epc:checked')].map(c => ({
    id: c.dataset.id,
    title: c.dataset.title || '',
    episode_number: parseInt(c.dataset.epNum) || 0,
    season_number: parseInt(c.dataset.snNum) || 0,
    series_title: c.dataset.series || '',
    season_title: c.dataset.seasonTitle || '',
  }));
  if (!selected.length) {
    toast('pick some episodes first', 'err');
    return;
  }

  const distinctSeries = new Set(selected.map(s => s.series_title).filter(Boolean));
  let taskTitle = 'Anime';
  if (distinctSeries.size === 1) {
    taskTitle = Array.from(distinctSeries)[0];
  } else if (distinctSeries.size > 1) {
    taskTitle = `${distinctSeries.size} Anime Batch`;
  }

  const vqVal = ddVideo ? ddVideo.value : (document.getElementById('vq')?.value || '1080p');
  const aqVal = ddAudioQual ? ddAudioQual.value : (document.getElementById('aq')?.value || '192k');
  const audioVal = ddAudio ? ddAudio.value : (document.getElementById('al')?.value || 'ja-JP');
  const subsVal = ddSubs ? ddSubs.value : (document.getElementById('sl')?.value || 'en-US');
  const dlDirVal = (document.getElementById('download-dir') || {}).value || '';
  const workersVal = parseInt(document.getElementById('workers-slider')?.value || '16', 10);
  const resumeVal = Boolean(document.getElementById('enable-resume')?.checked);
  const audioFallbackVal = Boolean(document.getElementById('audio-fallback')?.checked ?? true);
  const bitrateVal = ddBitrate ? ddBitrate.value : (document.getElementById('bitrate-mode')?.value || 'highest');

  const res = await api('/api/download', {
    items: selected,
    task_title: taskTitle,
    series_title: taskTitle,
    video_quality: vqVal,
    audio_quality: aqVal,
    audio_lang: audioVal,
    subs_lang: subsVal,
    force_download: (document.getElementById('force-download') || {}).checked || false,
    download_dir: dlDirVal.trim() || 'anime',
    workers: workersVal,
    enable_resume: resumeVal,
    audio_fallback: audioFallbackVal,
    bitrate_mode: bitrateVal,
  });

  if (!res.success) {
    toast(res.error || 'download failed to start', 'err');
    return;
  }

  toast(res.message || (`${selected.length} episode(s) added to queue`));
  document.getElementById('dl-panel').style.display = 'block';
  startPolling();
}

function startPolling() {
  if (pollTimer) return;
  pollTimer = setInterval(async () => {
    const state = await api('/api/state');
    if (state) {
      if (state.watcher) updateWatcherState(state.watcher);
      if (state.download) {
        updateProgressPanel(state.download);
        const isRunning = state.download.status === 'running' || state.download.status === 'paused';
        const hasQueue = state.download.queue && state.download.queue.length > 0;
        const hasActiveTasks = state.download.tasks && state.download.tasks.some(t => t.status === 'running' || t.status === 'queued');
        if (!isRunning && !hasQueue && !hasActiveTasks) {
          clearInterval(pollTimer);
          pollTimer = null;
        }
      }
    }
  }, 800);
}

async function togglePause() {
  const btn = document.getElementById('dl-pause-btn');
  if (!btn) return;
  if (btn.dataset.action === 'resume') {
    const res = await api('/api/download/resume', {});
    if (res && res.success) {
      btn.textContent = 'pause';
      btn.dataset.action = 'pause';
      toast('download resumed');
      startPolling();
    } else {
      toast(res?.error || 'failed to resume', 'err');
    }
  } else {
    const res = await api('/api/download/pause', {});
    if (res && res.success) {
      btn.textContent = 'resume';
      btn.dataset.action = 'resume';
      toast('download paused');
    } else {
      toast(res?.error || 'failed to pause', 'err');
    }
  }
}

async function skipDl() {
  const btn = document.getElementById('dl-skip-btn');
  if (btn) {
    if (btn.disabled) return;
    btn.disabled = true;
    btn.textContent = 'skipping...';
  }
  try {
    const res = await api('/api/download/skip', {});
    if (res && res.success) {
      toast('Skipped active episode');
      startPolling();
      const state = await api('/api/state');
      if (state && state.download) {
        updateProgressPanel(state.download);
      }
    } else {
      toast(res?.error || 'failed to skip', 'err');
    }
  } catch (e) {
    console.error('Skip episode error:', e);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = 'skip';
    }
  }
}

async function cancelCurrentEp() {
  const btn = document.getElementById('dl-cancel-btn');
  if (btn) {
    if (btn.disabled) return;
    btn.disabled = true;
    btn.textContent = 'canceling...';
  }
  try {
    const res = await api('/api/download/cancel-current', {});
    if (res && res.success) {
      toast('Active episode canceled');
      startPolling();
      const state = await api('/api/state');
      if (state && state.download) {
        updateProgressPanel(state.download);
      }
    } else {
      toast(res?.error || 'failed to cancel episode', 'err');
    }
  } catch (e) {
    console.error('Cancel episode error:', e);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = 'cancel ep';
    }
  }
}

async function cancelDl() {
  await cancelCurrentEp();
}

async function removeFromQueue(jobId, epRow) {
  // Immediately update UI: animate out row, update total volume and circular meter
  if (epRow) {
    const taskCard = epRow.closest('.task-card');
    if (taskCard) {
      const epCountEl = taskCard.querySelector('.task-ep-count');
      if (epCountEl) {
        const match = epCountEl.textContent.match(/(\d+)\s*\/\s*(\d+)/);
        if (match) {
          const completed = parseInt(match[1], 10);
          const oldTotal = parseInt(match[2], 10);
          const newTotal = Math.max(completed, oldTotal - 1);
          epCountEl.textContent = `${completed} / ${newTotal} eps`;

          // Recalculate meter percentage immediately
          const newPct = newTotal > 0 ? Math.min(100, Math.round((completed / newTotal) * 100)) : 0;
          const dashoffset = (100 - newPct).toFixed(1);
          const circleProg = taskCard.querySelector('.circle-prog');
          const circleText = taskCard.querySelector('.circle-text');
          if (circleProg) circleProg.setAttribute('stroke-dashoffset', dashoffset);
          if (circleText) {
            circleText.textContent = (newPct >= 100 && newTotal > 0) ? '✓' : `${newPct}%`;
          }
        }
      }
    }
    epRow.style.opacity = '0';
    epRow.style.transform = 'translateX(8px)';
    epRow.style.transition = 'all 0.2s ease';
    setTimeout(() => {
      if (epRow && epRow.parentNode) epRow.remove();
    }, 200);
  }

  const qBadge = document.getElementById('queue-badge');
  if (qBadge) {
    const curVal = parseInt(qBadge.textContent || '0', 10);
    if (curVal > 0) qBadge.textContent = String(curVal - 1);
  }

  const res = await api('/api/queue/remove', { id: jobId });
  if (res && res.success) {
    toast('Removed from queue');
    const state = await api('/api/state');
    if (state && state.download) {
      updateProgressPanel(state.download);
    }
  } else {
    toast(res?.error || 'failed to remove from queue', 'err');
  }
}

async function clearQueue() {
  if (!confirm('Clear all upcoming episodes and finished tasks?')) return;
  const res = await api('/api/queue/clear', {});
  const qList = document.getElementById('queue-list');
  if (qList) {
    Array.from(qList.querySelectorAll('.task-card')).forEach(card => {
      if (card.classList.contains('completed') || card.classList.contains('canceled') || card.classList.contains('failed')) {
        card.remove();
      }
    });
    Array.from(qList.querySelectorAll('.queue-item')).forEach(item => item.remove());
  }
  if (res && res.success) {
    toast('Queue cleared (' + (res.cleared || 0) + ' items)');
  } else {
    toast(res?.error || 'failed to clear queue', 'err');
  }
  const state = await api('/api/state');
  if (state && state.download) {
    updateProgressPanel(state.download);
  }
}

async function clearFinishedTasks() {
  const res = await api('/api/tasks/clear-finished', {});
  const qList = document.getElementById('queue-list');
  if (qList) {
    Array.from(qList.querySelectorAll('.task-card')).forEach(card => {
      if (card.classList.contains('completed') || card.classList.contains('canceled') || card.classList.contains('failed')) {
        card.remove();
      }
    });
  }
  if (res && res.success) {
    if (res.cleared > 0) {
      toast('Cleared ' + res.cleared + ' finished task(s)');
    } else {
      toast('Finished task(s) cleared');
    }
  } else {
    toast(res?.error || 'failed to clear tasks', 'err');
  }
  const state = await api('/api/state');
  if (state && state.download) {
    updateProgressPanel(state.download);
  }
}

const collapsedTaskIds = new Set();

function toggleTaskAccordion(taskId) {
  if (collapsedTaskIds.has(taskId)) {
    collapsedTaskIds.delete(taskId);
  } else {
    collapsedTaskIds.add(taskId);
  }
  const card = document.querySelector(`.task-card[data-task-id="${taskId}"]`);
  if (card) {
    card.classList.toggle('collapsed', collapsedTaskIds.has(taskId));
  }
}

async function cancelTask(taskId, e) {
  if (e) e.stopPropagation();
  const card = document.querySelector(`.task-card[data-task-id="${taskId}"]`);
  const isFinished = card && (card.classList.contains('completed') || card.classList.contains('canceled') || card.classList.contains('failed'));
  if (!isFinished && !confirm('Cancel this anime download task?')) return;

  const res = await api('/api/task/remove', { id: taskId });
  if (card && (isFinished || (res && res.success))) {
    card.remove();
  }
  if (res && res.success) {
    toast(isFinished ? 'Task dismissed' : 'Task canceled');
  } else {
    if (isFinished && card) {
      toast('Task dismissed');
    } else {
      toast(res?.error || 'Failed to update task', 'err');
    }
  }
  const state = await api('/api/state');
  if (state && state.download) {
    updateProgressPanel(state.download);
  }
}

function updateProgressPanel(dl) {
  if (!dl) return;
  const hasTasks = dl.tasks && dl.tasks.length > 0;
  const hasQueue = dl.queue && dl.queue.length > 0;
  const isRunning = dl.status === 'running' || dl.status === 'paused';

  const dlPanel = document.getElementById('dl-panel');
  if (dlPanel) {
    if (!isRunning && !hasTasks && !hasQueue && dl.status === 'idle') {
      dlPanel.style.display = 'none';
    } else {
      dlPanel.style.display = 'block';
    }
  }

  const pill = document.getElementById('pill');
  const pauseBtn = document.getElementById('dl-pause-btn');
  const skipBtn = document.getElementById('dl-skip-btn');
  const cancelBtn = document.getElementById('dl-cancel-btn');

  if (pauseBtn && cancelBtn) {
    if (isRunning) {
      pauseBtn.style.display = 'inline-block';
      cancelBtn.style.display = 'inline-block';
      if (skipBtn) skipBtn.style.display = 'inline-block';
      if (dl.status === 'paused') {
        pauseBtn.textContent = 'resume';
        pauseBtn.dataset.action = 'resume';
      } else {
        pauseBtn.textContent = 'pause';
        pauseBtn.dataset.action = 'pause';
      }
      if (!cancelBtn.disabled) {
        cancelBtn.textContent = 'cancel ep';
      }
      if (skipBtn && !skipBtn.disabled) {
        skipBtn.textContent = 'skip';
      }
    } else {
      pauseBtn.style.display = 'none';
      cancelBtn.style.display = 'none';
      if (skipBtn) skipBtn.style.display = 'none';
    }
  }

  const openFolderBtn = document.getElementById('dl-open-folder-btn');
  if (openFolderBtn) {
    openFolderBtn.style.display = (dl.status === 'completed') ? 'inline-block' : 'none';
  }

  if (dl.status === 'running') {
    pill.className = 'pill pill-run';
    if (dl.track === 'muxing') {
      pill.innerHTML = '<span class="spin"></span>muxing mkv';
    } else if (dl.track) {
      pill.innerHTML = `<span class="spin"></span>downloading ${dl.track}`;
    } else {
      pill.innerHTML = '<span class="spin"></span>downloading';
    }
  } else if (dl.status === 'paused') {
    pill.className = 'pill pill-paused';
    pill.innerHTML = '\u23f8 paused';
  } else if (dl.status === 'completed') {
    pill.className = 'pill pill-ok';
    pill.innerHTML = '\u2713 done';
  } else if (dl.status === 'partial_error') {
    pill.className = 'pill pill-err';
    pill.innerHTML = '\u26a0 partial';
  } else if (dl.status === 'canceled') {
    pill.className = 'pill pill-err';
    pill.innerHTML = '\u2717 canceled';
  } else if (dl.status === 'error' || dl.status === 'failed') {
    pill.className = 'pill pill-err';
    pill.innerHTML = '\u2717 error';
  } else {
    pill.className = 'pill pill-err';
    pill.innerHTML = '\u2717 ' + dl.status;
  }

  const epIdx   = (dl.ep_idx  || 0) + 1;
  const epTotal = dl.ep_total || 1;
  document.getElementById('dl-ep-counter').textContent =
    (dl.status === 'completed' || dl.status === 'partial_error' || dl.status === 'error') ? `${Math.min(epTotal, (dl.ep_idx || epTotal))} / ${epTotal}` : `${epIdx} / ${epTotal}`;

  document.getElementById('cur-ep').textContent = dl.episode || '';

  const overallPct = Math.min(100, dl.overall_pct || 0);
  document.getElementById('pbar-overall').style.width = overallPct + '%';
  document.getElementById('ppct-overall').textContent  = overallPct.toFixed(1) + '%';

  const trackPct = Math.min(100, dl.track_pct || 0);
  document.getElementById('pbar-track').style.width = trackPct + '%';

  const segsEl = document.getElementById('dl-segs');
  if (dl.segs_total > 0) {
    const trackSuffix = dl.track ? ` [${dl.track}]` : '';
    if (dl.complete_file) {
      const doneMb = (dl.segs_done / (1024 * 1024)).toFixed(1);
      const totalMb = (dl.segs_total / (1024 * 1024)).toFixed(1);
      segsEl.textContent = `${trackPct.toFixed(1)}% • ${doneMb} / ${totalMb} MB${trackSuffix}`;
    } else {
      segsEl.textContent = `${trackPct.toFixed(1)}% • ${dl.segs_done} / ${dl.segs_total} parts${trackSuffix}`;
    }
  } else if (dl.track) {
    segsEl.textContent = `${trackPct.toFixed(1)}% • ${dl.track}`;
  } else {
    segsEl.textContent = '';
  }

  document.getElementById('dl-speed').textContent = dl.speed || '';

  const logBox = document.getElementById('log');
  if (dl.log && dl.log.length) {
    logBox.textContent = dl.log.join('\n');
    logBox.scrollTop = logBox.scrollHeight;
  }

  // Update Tasks & Queue Panel
  const qPanel = document.getElementById('queue-panel');
  const qList = document.getElementById('queue-list');
  const qBadge = document.getElementById('queue-badge');
  if (qPanel && qList) {
    const tasks = dl.tasks || [];
    const queue = dl.queue || [];

    const queuedCount = dl.queued_count !== undefined ? dl.queued_count : queue.length;
    if (qBadge) {
      qBadge.textContent = String(queuedCount);
    }

    if (tasks.length > 0) {
      qPanel.style.display = 'block';
      // Collect task IDs currently present in state
      const taskIdsInState = new Set(tasks.map(t => String(t.id)));

      // Remove DOM task cards that are no longer in state
      Array.from(qList.querySelectorAll('.task-card')).forEach(card => {
        if (!taskIdsInState.has(card.dataset.taskId)) {
          card.remove();
        }
      });

      // Clean up fallback flat queue items if we now have task cards
      Array.from(qList.querySelectorAll('.queue-item')).forEach(item => item.remove());

      tasks.forEach((task) => {
        let card = qList.querySelector(`.task-card[data-task-id="${task.id}"]`);
        if (!card) {
          card = createTaskCard(task);
          qList.appendChild(card);
        } else {
          updateTaskCard(card, task);
        }
      });
    } else if (queue.length > 0) {
      qPanel.style.display = 'block';
      qList.innerHTML = '';
      queue.forEach((item, index) => {
        const row = document.createElement('div');
        row.className = 'queue-item';

        const num = document.createElement('span');
        num.className = 'queue-num';
        num.textContent = `#${index + 1}`;

        const info = document.createElement('div');
        info.className = 'queue-info';

        const title = document.createElement('div');
        title.className = 'queue-title';
        title.textContent = item.label || item.title || item.ep_id;

        const meta = document.createElement('div');
        meta.className = 'queue-meta';

        if (item.video_quality) {
          const vqTag = document.createElement('span');
          vqTag.className = 'queue-tag';
          vqTag.textContent = item.video_quality;
          meta.appendChild(vqTag);
        }

        if (item.audio_langs && item.audio_langs.length) {
          const alTag = document.createElement('span');
          alTag.className = 'queue-tag';
          alTag.textContent = item.audio_langs.join(', ');
          meta.appendChild(alTag);
        }

        info.append(title, meta);

        const removeBtn = document.createElement('button');
        removeBtn.className = 'queue-remove-btn';
        removeBtn.innerHTML = '✕';
        removeBtn.title = 'Remove from queue';
        removeBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          removeFromQueue(item.id || item.ep_id, row);
        });

        row.append(num, info, removeBtn);
        qList.appendChild(row);
      });
    } else {
      qList.innerHTML = '';
      qPanel.style.display = 'none';
    }
  }
}

function getCleanEpTitle(ep) {
  if (ep.title && !ep.title.match(/^S\d+E\d+\s*—/i)) {
    return ep.title;
  }
  if (ep.label) {
    const parts = ep.label.split(/—|-/);
    if (parts.length > 1) {
      return parts.slice(1).join('—').trim();
    }
    return ep.label;
  }
  return ep.title || ep.ep_id || 'Episode';
}

function getEpIndexLabel(ep, epIdx) {
  if (ep.episode_number && Number(ep.episode_number) > 0) {
    return `#${ep.episode_number}`;
  }
  return `#${epIdx + 1}`;
}

function updateEpIcon(epIco, status) {
  if (status === 'completed') {
    epIco.className = 'ep-ico ep-ico-done';
    epIco.textContent = '✓';
  } else if (status === 'running') {
    epIco.className = 'ep-ico ep-ico-run';
    epIco.innerHTML = '<span class="spin"></span>';
  } else if (status === 'paused') {
    epIco.className = 'ep-ico ep-ico-paused';
    epIco.textContent = '⏸';
  } else if (status === 'canceled') {
    epIco.className = 'ep-ico ep-ico-err';
    epIco.textContent = '✕';
  } else if (status === 'skipped') {
    epIco.className = 'ep-ico ep-ico-skipped';
    epIco.textContent = '↷';
  } else if (status === 'failed') {
    epIco.className = 'ep-ico ep-ico-err';
    epIco.textContent = '!';
  } else {
    epIco.className = 'ep-ico ep-ico-queued';
    epIco.textContent = '⋯';
  }
}

function updateEpRight(right, ep, epRow) {
  right.innerHTML = '';

  if (ep.status === 'running') {
    if (ep.progress !== undefined) {
      const epProg = document.createElement('span');
      epProg.className = 'task-ep-prog';
      epProg.textContent = `${Number(ep.progress).toFixed(0)}%`;
      right.appendChild(epProg);
    }
    const statusPill = document.createElement('span');
    statusPill.className = 'task-ep-status-pill status-running';
    statusPill.textContent = 'downloading';
    right.appendChild(statusPill);
  } else if (ep.status === 'completed') {
    if (ep.file_size_mb) {
      const epSize = document.createElement('span');
      epSize.className = 'task-ep-size';
      epSize.textContent = `${ep.file_size_mb} MB`;
      right.appendChild(epSize);
    }
    const statusPill = document.createElement('span');
    statusPill.className = 'task-ep-status-pill status-completed';
    statusPill.textContent = 'done';
    right.appendChild(statusPill);
  } else if (ep.status === 'paused') {
    const statusPill = document.createElement('span');
    statusPill.className = 'task-ep-status-pill status-paused';
    statusPill.textContent = 'paused';
    right.appendChild(statusPill);
  } else if (ep.status === 'queued') {
    const statusPill = document.createElement('span');
    statusPill.className = 'task-ep-status-pill status-queued';
    statusPill.textContent = 'queued';
    right.appendChild(statusPill);

    const epRemove = document.createElement('button');
    epRemove.className = 'task-ep-remove-btn';
    epRemove.innerHTML = '✕';
    epRemove.title = 'Remove episode from queue';
    epRemove.onclick = (e) => {
      e.stopPropagation();
      removeFromQueue(ep.id || ep.ep_id, epRow);
    };
    right.appendChild(epRemove);
  } else if (ep.status === 'canceled' || ep.status === 'skipped') {
    const statusPill = document.createElement('span');
    statusPill.className = `task-ep-status-pill status-${ep.status}`;
    statusPill.textContent = ep.status;
    right.appendChild(statusPill);
  } else if (ep.status === 'failed') {
    const statusPill = document.createElement('span');
    statusPill.className = 'task-ep-status-pill status-failed';
    statusPill.textContent = 'failed';
    right.appendChild(statusPill);
  }
}

function renderEpisodeRow(ep, epIdx, task) {
  const epKey = String(ep.id || ep.ep_id);
  const row = document.createElement('div');
  row.className = `task-ep-row status-${ep.status}`;
  row.dataset.epId = epKey;

  const left = document.createElement('div');
  left.className = 'task-ep-left';

  const epIco = document.createElement('span');
  epIco.className = 'ep-ico';
  updateEpIcon(epIco, ep.status);

  const epIdxSpan = document.createElement('span');
  epIdxSpan.className = 'task-ep-idx';
  epIdxSpan.textContent = getEpIndexLabel(ep, epIdx);

  const epTitle = document.createElement('span');
  epTitle.className = 'task-ep-title';
  epTitle.textContent = getCleanEpTitle(ep);
  epTitle.title = ep.label || ep.title || ep.ep_id;

  left.append(epIco, epIdxSpan, epTitle);

  const right = document.createElement('div');
  right.className = 'task-ep-right';
  updateEpRight(right, ep, row);

  row.append(left, right);
  return row;
}

function updateEpisodeRow(epRow, ep, epIdx, task) {
  epRow.className = `task-ep-row status-${ep.status}`;

  const epIco = epRow.querySelector('.ep-ico');
  if (epIco) updateEpIcon(epIco, ep.status);

  const epIdxSpan = epRow.querySelector('.task-ep-idx');
  if (epIdxSpan) epIdxSpan.textContent = getEpIndexLabel(ep, epIdx);

  const epTitle = epRow.querySelector('.task-ep-title');
  if (epTitle) {
    epTitle.textContent = getCleanEpTitle(ep);
    epTitle.title = ep.label || ep.title || ep.ep_id;
  }

  const right = epRow.querySelector('.task-ep-right');
  if (right) updateEpRight(right, ep, epRow);
}

function createTaskCard(task) {
  const isCollapsed = collapsedTaskIds.has(task.id);
  const card = document.createElement('div');
  card.className = `task-card ${task.status}` + (isCollapsed ? ' collapsed' : '');
  card.dataset.taskId = task.id;

  const header = document.createElement('div');
  header.className = 'task-header';
  header.onclick = () => toggleTaskAccordion(task.id);

  const left = document.createElement('div');
  left.className = 'task-left';

  const pct = Math.max(0, Math.min(100, Number(task.progress_pct) || 0));
  const dashoffset = (100 - pct).toFixed(1);
  let meterText = Math.round(pct) + '%';
  if (task.status === 'completed' || (pct >= 100 && task.status !== 'failed' && task.status !== 'canceled')) {
    meterText = '✓';
  } else if (task.status === 'canceled' || task.status === 'failed') {
    meterText = '✕';
  }

  const meterWrap = document.createElement('div');
  meterWrap.className = 'task-meter-wrap';
  meterWrap.innerHTML = `
    <svg class="task-circle-meter ${task.status}" viewBox="0 0 36 36">
      <path class="circle-bg" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
      <path class="circle-prog" stroke-dasharray="100 100" stroke-dashoffset="${dashoffset}" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
      <text x="18" y="20.5" class="circle-text">${meterText}</text>
    </svg>
  `;

  const titleGroup = document.createElement('div');
  titleGroup.className = 'task-title-group';

  const animeTitle = document.createElement('div');
  animeTitle.className = 'task-anime-title';
  animeTitle.textContent = task.series_title || task.title || 'Anime Download';
  animeTitle.title = animeTitle.textContent;

  const metaRow = document.createElement('div');
  metaRow.className = 'task-meta-row';

  const statusPill = document.createElement('span');
  statusPill.className = `task-status-pill ${task.status}`;
  statusPill.textContent = task.status;
  metaRow.appendChild(statusPill);

  const epCount = document.createElement('span');
  epCount.className = 'task-ep-count';
  epCount.textContent = `${task.completed || 0} / ${task.total || 0} eps`;
  metaRow.appendChild(epCount);

  if (task.video_quality) {
    const vqTag = document.createElement('span');
    vqTag.className = 'task-tag';
    vqTag.textContent = task.video_quality;
    metaRow.appendChild(vqTag);
  }

  if (task.audio_langs && task.audio_langs.length) {
    const alTag = document.createElement('span');
    alTag.className = 'task-tag';
    alTag.textContent = task.audio_langs.join(', ');
    metaRow.appendChild(alTag);
  }

  titleGroup.append(animeTitle, metaRow);
  left.append(meterWrap, titleGroup);

  const right = document.createElement('div');
  right.className = 'task-right';

  const cancelBtn = document.createElement('button');
  cancelBtn.className = 'task-cancel-btn';
  cancelBtn.innerHTML = '✕';
  cancelBtn.title = (task.status === 'completed' || task.status === 'canceled' || task.status === 'failed') ? 'Dismiss task' : 'Cancel task';
  cancelBtn.onclick = (e) => cancelTask(task.id, e);

  const chevron = document.createElement('span');
  chevron.className = 'task-chevron';
  chevron.textContent = '▼';

  right.append(cancelBtn, chevron);
  header.append(left, right);

  const body = document.createElement('div');
  body.className = 'task-body';

  const episodes = task.episodes || [];
  if (episodes.length === 0) {
    const emptyMsg = document.createElement('div');
    emptyMsg.style.cssText = 'color:var(--dim);font-size:0.72rem;padding:4px;';
    emptyMsg.textContent = 'No episodes';
    body.appendChild(emptyMsg);
  } else {
    episodes.forEach((ep, epIdx) => {
      body.appendChild(renderEpisodeRow(ep, epIdx, task));
    });
  }

  card.append(header, body);
  return card;
}

function updateTaskCard(card, task) {
  const isCollapsed = collapsedTaskIds.has(task.id);
  card.className = `task-card ${task.status}` + (isCollapsed ? ' collapsed' : '');

  const cancelBtn = card.querySelector('.task-cancel-btn');
  if (cancelBtn) {
    const isFinished = task.status === 'completed' || task.status === 'canceled' || task.status === 'failed';
    cancelBtn.title = isFinished ? 'Dismiss task' : 'Cancel task';
  }

  const pct = Math.max(0, Math.min(100, Number(task.progress_pct) || 0));
  const dashoffset = (100 - pct).toFixed(1);
  let meterText = Math.round(pct) + '%';
  if (task.status === 'completed' || (pct >= 100 && task.status !== 'failed' && task.status !== 'canceled')) {
    meterText = '✓';
  } else if (task.status === 'canceled' || task.status === 'failed') {
    meterText = '✕';
  }

  const meterSvg = card.querySelector('.task-circle-meter');
  if (meterSvg) meterSvg.setAttribute('class', `task-circle-meter ${task.status}`);

  const circleProg = card.querySelector('.circle-prog');
  if (circleProg) circleProg.setAttribute('stroke-dashoffset', dashoffset);

  const circleText = card.querySelector('.circle-text');
  if (circleText) circleText.textContent = meterText;

  const statusPill = card.querySelector('.task-status-pill');
  if (statusPill) {
    statusPill.className = `task-status-pill ${task.status}`;
    statusPill.textContent = task.status;
  }

  const epCount = card.querySelector('.task-ep-count');
  if (epCount) {
    epCount.textContent = `${task.completed || 0} / ${task.total || 0} eps`;
  }

  const body = card.querySelector('.task-body');
  if (body) {
    const episodes = task.episodes || [];
    if (episodes.length === 0) {
      body.innerHTML = '<div style="color:var(--dim);font-size:0.72rem;padding:4px;">No episodes</div>';
    } else {
      const epIdsInState = new Set(episodes.map(ep => String(ep.id || ep.ep_id)));
      Array.from(body.querySelectorAll('.task-ep-row')).forEach(row => {
        if (!epIdsInState.has(row.dataset.epId)) {
          row.remove();
        }
      });

      episodes.forEach((ep, epIdx) => {
        const epKey = String(ep.id || ep.ep_id);
        let epRow = body.querySelector(`.task-ep-row[data-ep-id="${epKey}"]`);
        if (!epRow) {
          epRow = renderEpisodeRow(ep, epIdx, task);
          body.appendChild(epRow);
        } else {
          updateEpisodeRow(epRow, ep, epIdx, task);
        }
      });
    }
  }
}

// ── Custom Desktop Context Menu (Right Click) ────────────────────────────────

let lastContextMenuTarget = null;
let lastSelectedText = '';

function initCustomContextMenu() {
  const menu = document.getElementById('custom-context-menu');
  if (!menu) return;

  let lastSelectionStart = null;
  let lastSelectionEnd = null;

  menu.addEventListener('mousedown', (e) => {
    // Prevent context menu buttons from stealing focus / clearing selection from inputs
    e.preventDefault();
  });

  window.addEventListener('contextmenu', (e) => {
    // If Shift is pressed, allow native developer fallback if available
    if (e.shiftKey) return;

    e.preventDefault();
    lastContextMenuTarget = e.target;

    const isInput = e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA');
    const isEditable = isInput && !e.target.readOnly && !e.target.disabled;

    let selectedText = '';
    if (isInput) {
      lastSelectionStart = e.target.selectionStart;
      lastSelectionEnd = e.target.selectionEnd;
      if (typeof lastSelectionStart === 'number' && typeof lastSelectionEnd === 'number' && lastSelectionEnd > lastSelectionStart) {
        selectedText = e.target.value.substring(lastSelectionStart, lastSelectionEnd);
      }
    } else {
      lastSelectionStart = null;
      lastSelectionEnd = null;
      selectedText = window.getSelection() ? window.getSelection().toString() : '';
    }
    lastSelectedText = selectedText;

    const copyBtn = document.getElementById('ctx-copy');
    const cutBtn = document.getElementById('ctx-cut');
    const pasteBtn = document.getElementById('ctx-paste');
    const selectAllBtn = document.getElementById('ctx-selectall');

    if (copyBtn) {
      copyBtn.disabled = !selectedText && (!isInput || !e.target.value);
    }
    if (cutBtn) {
      cutBtn.disabled = !isEditable || !selectedText;
    }
    if (pasteBtn) {
      pasteBtn.disabled = !isEditable;
    }
    if (selectAllBtn) {
      selectAllBtn.disabled = false;
    }

    menu.style.display = 'flex';

    // Viewport-aware boundary positioning
    const mWidth = menu.offsetWidth || 165;
    const mHeight = menu.offsetHeight || 135;
    let x = e.clientX;
    let y = e.clientY;

    if (x + mWidth > window.innerWidth - 8) {
      x = Math.max(8, window.innerWidth - mWidth - 8);
    }
    if (y + mHeight > window.innerHeight - 8) {
      y = Math.max(8, window.innerHeight - mHeight - 8);
    }

    menu.style.left = `${x}px`;
    menu.style.top = `${y}px`;
  });

  // Auto-dismiss on click outside, scroll, resize, or Escape
  window.addEventListener('click', (e) => {
    if (!menu.contains(e.target)) {
      hideContextMenu();
    }
  });

  window.addEventListener('scroll', () => hideContextMenu(), true);
  window.addEventListener('resize', () => hideContextMenu());
  window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') hideContextMenu();
  });
}

function hideContextMenu() {
  const menu = document.getElementById('custom-context-menu');
  if (menu) menu.style.display = 'none';
}

async function contextMenuAction(action) {
  const el = lastContextMenuTarget;
  const isInput = el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA');
  const isEditable = isInput && !el.readOnly && !el.disabled;

  hideContextMenu();

  try {
    if (action === 'copy') {
      let textToCopy = lastSelectedText;
      if (!textToCopy && isInput) {
        textToCopy = el.value || '';
      }
      if (textToCopy) {
        let copied = false;
        try {
          if (isInput) {
            el.focus();
            copied = document.execCommand('copy');
          }
        } catch (_) {}

        if (!copied) {
          try {
            const ta = document.createElement('textarea');
            ta.value = textToCopy;
            ta.style.position = 'fixed';
            ta.style.opacity = '0';
            ta.style.left = '-9999px';
            document.body.appendChild(ta);
            ta.select();
            document.execCommand('copy');
            document.body.removeChild(ta);
            copied = true;
          } catch (_) {}
        }

        try {
          await api('/api/clipboard/copy', { text: textToCopy });
        } catch (_) {}

        toast('Copied to clipboard');
      }
    } else if (action === 'cut') {
      if (isEditable) {
        el.focus();
        let start = typeof el.selectionStart === 'number' ? el.selectionStart : lastSelectionStart;
        let end = typeof el.selectionEnd === 'number' ? el.selectionEnd : lastSelectionEnd;
        if (typeof start === 'number' && typeof end === 'number' && end > start) {
          const textToCut = el.value.substring(start, end);
          let cutSuccess = false;
          try {
            cutSuccess = document.execCommand('cut');
          } catch (_) {}

          if (!cutSuccess) {
            try {
              const ta = document.createElement('textarea');
              ta.value = textToCut;
              ta.style.position = 'fixed';
              ta.style.opacity = '0';
              ta.style.left = '-9999px';
              document.body.appendChild(ta);
              ta.select();
              document.execCommand('copy');
              document.body.removeChild(ta);
            } catch (_) {}

            el.value = el.value.substring(0, start) + el.value.substring(end);
            el.selectionStart = el.selectionEnd = start;
          }

          try {
            await api('/api/clipboard/copy', { text: textToCut });
          } catch (_) {}

          el.dispatchEvent(new Event('input', { bubbles: true }));
          el.dispatchEvent(new Event('change', { bubbles: true }));
          toast('Cut to clipboard');
        }
      }
    } else if (action === 'paste') {
      if (isEditable) {
        el.focus();
        let textToPaste = '';

        // 1. Try modern clipboard API
        if (navigator.clipboard && navigator.clipboard.readText) {
          try {
            textToPaste = await navigator.clipboard.readText();
          } catch (_) {}
        }

        // 2. Desktop backend clipboard fallback
        if (!textToPaste) {
          try {
            const res = await api('/api/clipboard/paste');
            if (res && res.success && typeof res.text === 'string') {
              textToPaste = res.text;
            }
          } catch (_) {}
        }

        // 3. Fallback execCommand
        if (!textToPaste) {
          try {
            document.execCommand('paste');
          } catch (_) {}
        }

        // 4. Insert into the target input/textarea
        if (textToPaste) {
          const val = el.value || '';
          let start = typeof el.selectionStart === 'number' ? el.selectionStart : lastSelectionStart;
          let end = typeof el.selectionEnd === 'number' ? el.selectionEnd : lastSelectionEnd;

          if (typeof start !== 'number' || isNaN(start)) start = val.length;
          if (typeof end !== 'number' || isNaN(end)) end = start;

          el.value = val.substring(0, start) + textToPaste + val.substring(end);
          el.selectionStart = el.selectionEnd = start + textToPaste.length;
          el.dispatchEvent(new Event('input', { bubbles: true }));
          el.dispatchEvent(new Event('change', { bubbles: true }));
          toast('Pasted from clipboard');
        } else {
          toast('Clipboard is empty');
        }
      }
    } else if (action === 'selectall') {
      if (isInput) {
        el.focus();
        el.select();
      } else {
        const selection = window.getSelection();
        const range = document.createRange();
        range.selectNodeContents(document.body);
        selection.removeAllRanges();
        selection.addRange(range);
      }
    }
  } catch (err) {
    console.warn('Context menu action failed:', err);
  }
}


// ==============================================
// CATALOG (BROWSE API) - ADVANCED FILTER & MULTI-SELECT
// ==============================================

let browseLoaded = false;
let allCatalogItems = [];
let selectedCatalogIds = new Set();
let currentCatalogFilter = '';

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
}

async function copyUrlToDownload(url) {
  try {
    const input = document.getElementById('search-input');
    if (input) {
      input.value = url;
      input.focus();
      input.select();
      switchTab('dashboard');
      searchSeries();
    }
  } catch (err) {
    console.warn('copyUrlToDownload failed:', err);
  }
}

async function loadBrowseAnimes(forceRefresh = false) {
  const loadingEl = document.getElementById('catalog-loading');
  const errorEl = document.getElementById('catalog-error');
  const listEl = document.getElementById('catalog-list');
  const filterInput = document.getElementById('catalog-filter-input');

  try {
    loadingEl.style.display = 'flex';
    errorEl.style.display = 'none';
    listEl.innerHTML = '';
    selectedCatalogIds.clear();
    updateCatalogBatchBar();

    const url = forceRefresh ? '/api/browse?refresh=1' : '/api/browse';
    const res = await api(url);
    if (!res || !res.success) {
      throw new Error(res?.error || 'Error loading catalog');
    }

    allCatalogItems = Array.isArray(res.data?.data) ? res.data.data : [];

    if (filterInput) {
      filterInput.placeholder = `search ${allCatalogItems.length} animes...`;
      currentCatalogFilter = filterInput.value.trim().toLowerCase();
    }

    renderCatalogList();
  } catch (err) {
    console.error('loadBrowseAnimes error:', err);
    errorEl.textContent = 'Error: ' + (err.message || err);
    errorEl.style.display = 'block';
    toast('Could not load catalog', 'err');
    browseLoaded = false;
  } finally {
    loadingEl.style.display = 'none';
  }
}

function filterCatalog(query) {
  currentCatalogFilter = (query || '').trim().toLowerCase();
  const clearBtn = document.getElementById('catalog-filter-clear');
  if (clearBtn) {
    clearBtn.style.display = currentCatalogFilter ? 'block' : 'none';
  }
  renderCatalogList();
}

function clearCatalogFilter() {
  const filterInput = document.getElementById('catalog-filter-input');
  if (filterInput) {
    filterInput.value = '';
    filterInput.focus();
  }
  filterCatalog('');
}

function renderCatalogList() {
  const listEl = document.getElementById('catalog-list');
  if (!listEl) return;

  if (!allCatalogItems.length) {
    listEl.innerHTML = '<div class="catalog-empty">No anime found in broadcast catalog</div>';
    return;
  }

  const filtered = currentCatalogFilter
    ? allCatalogItems.filter(anime => {
        const title = (anime.title || '').toLowerCase();
        const desc = (anime.description || '').toLowerCase();
        const meta = anime.series_metadata || {};
        const year = String(meta.series_launch_year || '');
        return title.includes(currentCatalogFilter) || desc.includes(currentCatalogFilter) || year.includes(currentCatalogFilter);
      })
    : allCatalogItems;

  if (!filtered.length) {
    listEl.innerHTML = `<div class="catalog-empty">No anime matching "${escapeHtml(currentCatalogFilter)}"</div>`;
    return;
  }

  listEl.innerHTML = filtered.map((anime, idx) => {
    const meta = anime.series_metadata || {};
    const id = anime.id || `anime-${idx + 1}`;
    const title = anime.title || 'Untitled';
    const type = (anime.type === 'movie_listing' || (meta.is_mature && meta.mature_blocked)) ? 'Movie' : 'Series';
    const year = meta.series_launch_year || '';

    const seasonsCount = meta.season_count;
    const episodesCount = meta.episode_count;
    let episodesStr = '';
    if (seasonsCount != null && episodesCount != null) {
      episodesStr = `${seasonsCount} ${seasonsCount === 1 ? 'season' : 'seasons'} • ${episodesCount} ep`;
    } else if (episodesCount != null) {
      episodesStr = `${episodesCount} ep`;
    }

    const description = anime.description || meta.extended_description || '';

    const tallList = anime.images?.poster_tall?.[0] || [];
    const wideList = anime.images?.poster_wide?.[0] || [];
    const posterSrc = (tallList[tallList.length - 1]?.source) || (wideList[wideList.length - 1]?.source) || '';

    const seriesId = anime.id || (anime.linked_resource_key || '').replace(/.*\/series\//, '');
    const url = `https://www.crunchyroll.com/series/${seriesId}`;

    const audioLocales = (meta.audio_locales || []).map(l => l.split('-')[0].toUpperCase());
    const uniqueAudios = Array.from(new Set(audioLocales)).slice(0, 4).join(', ');
    const isMonitored = monitoredSeriesMap.has(seriesId);

    const badges = [];
    badges.push(`<span class="res-badge ${type === 'Movie' ? 'res-badge-movie' : ''}">${type}</span>`);
    if (year) badges.push(`<span class="res-badge">${year}</span>`);
    if (episodesStr) badges.push(`<span class="res-badge">${episodesStr}</span>`);
    if (isMonitored) badges.push('<span class="res-badge res-badge-monitored">AUTO-DL</span>');
    if (meta.is_subbed) badges.push('<span class="res-badge res-badge-sub">SUB</span>');
    if (meta.is_dubbed) badges.push('<span class="res-badge res-badge-dub">DUB</span>');

    const isSelected = selectedCatalogIds.has(id);

    return `
      <div class="catalog-card ${isSelected ? 'selected' : ''}" data-id="${escapeHtml(id)}" data-url="${escapeHtml(url)}" tabindex="0">
        <div class="catalog-poster-box">
          ${posterSrc
            ? `<img class="catalog-poster" src="${escapeHtml(posterSrc)}" alt="${escapeHtml(title)}" loading="lazy" onerror="this.style.opacity='0.2'">`
            : `<div class="catalog-poster catalog-poster-empty"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg></div>`
          }
        </div>
        <div class="catalog-content">
          <div class="catalog-title-row">
            <h3 class="catalog-title" title="${escapeHtml(title)}">${escapeHtml(title)}</h3>
            <div class="catalog-selected-badge">
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="20 6 9 17 4 12"></polyline>
              </svg>
              <span>selected</span>
            </div>
          </div>
          <div class="res-badges">${badges.join('')}</div>
          ${description ? `<p class="catalog-desc" title="${escapeHtml(description)}">${escapeHtml(description)}</p>` : ''}
          <div class="catalog-bottom-row">
            ${uniqueAudios ? `<span class="catalog-langs" title="Audio: ${escapeHtml((meta.audio_locales || []).join(', '))}">audio: ${escapeHtml(uniqueAudios)}</span>` : '<span class="catalog-langs"></span>'}
            <div class="catalog-card-actions">
              <button type="button" class="btn-s ${isMonitored ? 'btn-monitor-active' : 'btn-monitor'} catalog-autodl-btn" data-id="${escapeHtml(seriesId)}" data-title="${escapeHtml(title)}" data-url="${escapeHtml(url)}" data-poster="${escapeHtml(posterSrc)}" title="${isMonitored ? 'Auto-download active. Click to stop.' : 'Auto-download new episodes when they air'}">${isMonitored ? 'auto-dl ✓' : 'auto-dl'}</button>
              <button type="button" class="btn-s catalog-fetch-btn" data-url="${escapeHtml(url)}" data-title="${escapeHtml(title)}" title="Inspect seasons and episodes on Dashboard">
                <span>fetch</span>
              </button>
              <button type="button" class="btn-s btn-pri catalog-dl-btn" data-url="${escapeHtml(url)}" data-title="${escapeHtml(title)}" title="Instantly enqueue all episodes to download queue">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                  <polyline points="7 10 12 15 17 10"></polyline>
                  <line x1="12" y1="15" x2="12" y2="3"></line>
                </svg>
                <span>download</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    `;
  }).join('');

  listEl.onclick = (e) => {
    // 0. Auto-download button
    const monitorBtn = e.target.closest('.catalog-autodl-btn');
    if (monitorBtn) {
      e.preventDefault();
      e.stopPropagation();
      toggleMonitorSeries(e, monitorBtn.dataset.id, monitorBtn.dataset.title, monitorBtn.dataset.url, monitorBtn.dataset.poster);
      return;
    }

    // 1. Explicit Download button
    const dlBtn = e.target.closest('.catalog-dl-btn');
    if (dlBtn) {
      e.preventDefault();
      e.stopPropagation();
      instantDownloadAnimeList([dlBtn.dataset.url], dlBtn.dataset.title);
      return;
    }

    // 2. Explicit Fetch button
    const fetchBtn = e.target.closest('.catalog-fetch-btn');
    if (fetchBtn) {
      e.preventDefault();
      e.stopPropagation();
      copyUrlToDownload(fetchBtn.dataset.url);
      return;
    }

    // 3. Clicking anywhere on the card toggles its selection state
    const card = e.target.closest('.catalog-card');
    if (card && card.dataset.id) {
      toggleSelectCatalogCard(card.dataset.id);
    }
  };

  updateCatalogBatchBar();
}

function toggleSelectCatalogCard(id, forceValue = null) {
  if (!id) return;
  const isSelected = forceValue !== null ? forceValue : !selectedCatalogIds.has(id);
  if (isSelected) {
    selectedCatalogIds.add(id);
  } else {
    selectedCatalogIds.delete(id);
  }

  const card = document.querySelector(`.catalog-card[data-id="${id}"]`);
  if (card) {
    card.classList.toggle('selected', isSelected);
  }

  updateCatalogBatchBar();
}

function toggleSelectAllCatalog() {
  const visibleCards = document.querySelectorAll('.catalog-card');
  if (!visibleCards.length) return;

  const allVisibleSelected = Array.from(visibleCards).every(card => selectedCatalogIds.has(card.dataset.id));
  const newSelection = !allVisibleSelected;

  visibleCards.forEach(card => {
    const id = card.dataset.id;
    if (newSelection) {
      selectedCatalogIds.add(id);
    } else {
      selectedCatalogIds.delete(id);
    }
    card.classList.toggle('selected', newSelection);
  });

  updateCatalogBatchBar();
}

function selectAllCatalog(select) {
  if (!select) {
    selectedCatalogIds.clear();
    document.querySelectorAll('.catalog-card').forEach(card => {
      card.classList.remove('selected');
    });
    updateCatalogBatchBar();
  } else {
    toggleSelectAllCatalog();
  }
}

function updateCatalogBatchBar() {
  const count = selectedCatalogIds.size;
  const batchBar = document.getElementById('catalog-batch-bar');
  const countEl = document.getElementById('catalog-selected-count');
  const selectAllBtn = document.getElementById('catalog-select-all-btn');

  if (batchBar && countEl) {
    if (count > 0) {
      batchBar.style.display = 'flex';
      countEl.textContent = `${count} anime${count === 1 ? '' : 's'} selected`;
    } else {
      batchBar.style.display = 'none';
    }
  }

  if (selectAllBtn) {
    const visibleCards = document.querySelectorAll('.catalog-card');
    const allSelected = visibleCards.length > 0 && Array.from(visibleCards).every(c => selectedCatalogIds.has(c.dataset.id));
    selectAllBtn.querySelector('span').textContent = allSelected ? 'deselect all' : 'select all';
  }
}

function getSelectedCatalogUrls() {
  const urls = [];
  selectedCatalogIds.forEach(id => {
    urls.push(`https://www.crunchyroll.com/series/${id}`);
  });
  return urls;
}

async function fetchSelectedCatalog() {
  const urls = getSelectedCatalogUrls();
  if (!urls.length) {
    toast('No animes selected', 'err');
    return;
  }
  switchTab('dashboard');
  await fetchUrl(urls, true);
  selectedCatalogIds.clear();
  updateCatalogBatchBar();
}

async function instantDownloadSelectedCatalog() {
  const urls = getSelectedCatalogUrls();
  if (!urls.length) {
    toast('No animes selected', 'err');
    return;
  }
  await instantDownloadAnimeList(urls);
  selectedCatalogIds.clear();
  updateCatalogBatchBar();
}

async function monitorSelectedCatalog() {
  const ids = Array.from(selectedCatalogIds);
  if (!ids.length) return;
  toast(`Enabling auto-download for ${ids.length} catalog show(s)...`, 'info');

  let successCount = 0;
  for (const sid of ids) {
    const item = allCatalogItems.find(it => it.id === sid) || {};
    const seriesId = item.id || (item.linked_resource_key || '').replace(/.*\/series\//, '');
    const tallList = item.images?.poster_tall?.[0] || [];
    const wideList = item.images?.poster_wide?.[0] || [];
    const posterSrc = (tallList[tallList.length - 1]?.source) || (wideList[wideList.length - 1]?.source) || '';
    try {
      const res = await api('/api/watcher/monitor', {
        series_id: seriesId,
        title: item.title || seriesId,
        url: `https://www.crunchyroll.com/series/${seriesId}`,
        poster: posterSrc,
        mode: 'latest_only',
      });
      if (res && res.success) {
        monitoredSeriesMap.set(seriesId, res.series);
        successCount++;
      }
    } catch (_) {}
  }
  selectedCatalogIds.clear();
  updateCatalogBatchBar();
  toast(`Auto-download enabled for ${successCount} show(s)!`, 'ok');
  syncAllMonitoredCards();
  const sRes = await api('/api/watcher/status');
  if (sRes && sRes.success) updateWatcherState(sRes);
}

async function instantDownloadAnimeList(urls, singleTitle = '') {
  if (!urls || !urls.length) return;

  const countStr = urls.length > 1 ? `${urls.length} animes` : (singleTitle || 'anime');
  toast(`Fetching episodes for ${countStr}...`, 'info');

  try {
    const fetchRes = await api('/api/fetch', { urls: urls });
    if (!fetchRes || !fetchRes.success) {
      toast(fetchRes?.error || 'Failed to fetch anime episodes', 'err');
      return;
    }

    const fetched = fetchRes.animes || (fetchRes.seasons ? [fetchRes] : []);
    if (!fetched.length) {
      toast('No anime found for selected URL(s)', 'err');
      return;
    }

    const allEpisodes = [];
    fetched.forEach(anime => {
      const seriesTitle = anime.title || 'Anime';
      (anime.seasons || []).forEach(season => {
        (season.episodes || []).forEach(ep => {
          allEpisodes.push({
            ...ep,
            series_title: seriesTitle,
          });
        });
      });
    });

    if (!allEpisodes.length) {
      toast('No episodes found to download', 'err');
      return;
    }

    let taskTitle = singleTitle || fetched[0].title || 'Anime';
    if (fetched.length > 1) {
      taskTitle = `${fetched.length} Anime Batch`;
    }

    const vqVal = ddVideo ? ddVideo.value : (document.getElementById('vq')?.value || '1080p');
    const aqVal = ddAudioQual ? ddAudioQual.value : (document.getElementById('aq')?.value || '192k');
    const audioVal = ddAudio ? ddAudio.value : (document.getElementById('al')?.value || 'ja-JP');
    const subsVal = ddSubs ? ddSubs.value : (document.getElementById('sl')?.value || 'en-US');
    const dlDirVal = (document.getElementById('download-dir') || {}).value || '';
    const workersVal = parseInt(document.getElementById('workers-slider')?.value || '16', 10);
    const resumeVal = Boolean(document.getElementById('enable-resume')?.checked);
    const audioFallbackVal = Boolean(document.getElementById('audio-fallback')?.checked ?? true);
    const bitrateVal = ddBitrate ? ddBitrate.value : (document.getElementById('bitrate-mode')?.value || 'highest');

    const dlRes = await api('/api/download', {
      items: allEpisodes,
      task_title: taskTitle,
      series_title: taskTitle,
      video_quality: vqVal,
      audio_quality: aqVal,
      audio_lang: audioVal,
      subs_lang: subsVal,
      force_download: (document.getElementById('force-download') || {}).checked || false,
      download_dir: dlDirVal.trim() || 'anime',
      workers: workersVal,
      enable_resume: resumeVal,
      audio_fallback: audioFallbackVal,
      bitrate_mode: bitrateVal,
    });

    if (!dlRes || !dlRes.success) {
      toast(dlRes?.error || 'Failed to start download', 'err');
      return;
    }

    toast(dlRes.message || `Enqueued ${allEpisodes.length} episode(s) to download queue!`, 'ok');
    switchTab('dashboard');
    const dlPanel = document.getElementById('dl-panel');
    if (dlPanel) dlPanel.style.display = 'block';
    startPolling();
  } catch (err) {
    console.error('instantDownloadAnimeList error:', err);
    toast('Download error: ' + (err.message || err), 'err');
  }
}

// ==========================================
// WATCHLIST LOGIC
// ==========================================
let watchlistLoaded = false;
let allWatchlistItems = [];
let currentWatchlistFilter = '';
let currentWatchlistSort = 'recent';
let currentWatchlistFilterMode = 'all';
let activeProfile = null;
let cachedUserProfiles = null;
const sessionProfilePins = {};
let pendingPinProfile = null;
const selectedWatchlistIds = new Set();

function toggleWatchlistProfileMenu(e) {
  if (e) e.stopPropagation();
  closeWatchlistSortMenu();
  closeWatchlistFilterMenu();
  const wrap = document.getElementById('watchlist-profile-wrap');
  const menu = document.getElementById('watchlist-profile-menu');
  if (!wrap || !menu) return;
  const isOpen = wrap.classList.toggle('open');
  menu.style.display = isOpen ? 'flex' : 'none';
}

function closeWatchlistProfileMenu() {
  const wrap = document.getElementById('watchlist-profile-wrap');
  const menu = document.getElementById('watchlist-profile-menu');
  if (wrap) wrap.classList.remove('open');
  if (menu) menu.style.display = 'none';
}

function toggleWatchlistSortMenu(e) {
  if (e) e.stopPropagation();
  closeWatchlistProfileMenu();
  closeWatchlistFilterMenu();
  const wrap = document.getElementById('watchlist-sort-wrap');
  const menu = document.getElementById('watchlist-sort-menu');
  if (!wrap || !menu) return;
  const isOpen = wrap.classList.toggle('open');
  menu.style.display = isOpen ? 'flex' : 'none';
}

function closeWatchlistSortMenu() {
  const wrap = document.getElementById('watchlist-sort-wrap');
  const menu = document.getElementById('watchlist-sort-menu');
  if (wrap) wrap.classList.remove('open');
  if (menu) menu.style.display = 'none';
}

function toggleWatchlistFilterMenu(e) {
  if (e) e.stopPropagation();
  closeWatchlistProfileMenu();
  closeWatchlistSortMenu();
  const wrap = document.getElementById('watchlist-filter-mode-wrap');
  const menu = document.getElementById('watchlist-filter-menu');
  if (!wrap || !menu) return;
  const isOpen = wrap.classList.toggle('open');
  menu.style.display = isOpen ? 'flex' : 'none';
}

function closeWatchlistFilterMenu() {
  const wrap = document.getElementById('watchlist-filter-mode-wrap');
  const menu = document.getElementById('watchlist-filter-menu');
  if (wrap) wrap.classList.remove('open');
  if (menu) menu.style.display = 'none';
}

function setWatchlistSort(sortKey) {
  currentWatchlistSort = sortKey;
  closeWatchlistSortMenu();

  const labels = {
    'recent': 'Recent Activity',
    'alpha-asc': 'Alphabetical (A - Z)',
    'alpha-desc': 'Alphabetical (Z - A)',
    'watched-newest': 'Recently Watched',
    'updated-newest': 'Recently Updated',
    'added-newest': 'Recently Added'
  };

  const labelEl = document.getElementById('watchlist-sort-label');
  const triggerEl = document.getElementById('watchlist-sort-trigger');
  if (labelEl) labelEl.textContent = labels[sortKey] || 'Sort';
  if (triggerEl) triggerEl.classList.toggle('is-active', sortKey !== 'recent');

  const menu = document.getElementById('watchlist-sort-menu');
  if (menu) {
    menu.querySelectorAll('.watchlist-menu-item').forEach(item => {
      const active = item.getAttribute('onclick')?.includes(`'${sortKey}'`);
      item.classList.toggle('active', active);
      const existingCheck = item.querySelector('.watchlist-check');
      if (active && !existingCheck) {
        item.insertAdjacentHTML('beforeend', '<svg class="watchlist-check" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"></polyline></svg>');
      } else if (!active && existingCheck) {
        existingCheck.remove();
      }
    });
  }

  renderWatchlistList();
}

function setWatchlistFilterMode(modeKey) {
  currentWatchlistFilterMode = modeKey;
  closeWatchlistFilterMenu();

  const labels = {
    'all': 'All',
    'unwatched': 'Unwatched',
    'in-progress': 'In Progress',
    'watched': 'Watched',
    'favorites': 'Favorites',
    'monitored': 'Monitored',
    'series': 'Series',
    'movies': 'Movies'
  };

  const labelEl = document.getElementById('watchlist-filter-label');
  const triggerEl = document.getElementById('watchlist-filter-trigger');
  if (labelEl) labelEl.textContent = labels[modeKey] || 'Filter';
  if (triggerEl) triggerEl.classList.toggle('is-active', modeKey !== 'all');

  const menu = document.getElementById('watchlist-filter-menu');
  if (menu) {
    menu.querySelectorAll('.watchlist-menu-item').forEach(item => {
      const active = item.getAttribute('onclick')?.includes(`'${modeKey}'`);
      item.classList.toggle('active', active);
      const existingCheck = item.querySelector('.watchlist-check');
      if (active && !existingCheck) {
        item.insertAdjacentHTML('beforeend', '<svg class="watchlist-check" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"></polyline></svg>');
      } else if (!active && existingCheck) {
        existingCheck.remove();
      }
    });
  }

  renderWatchlistList();
}

document.addEventListener('click', (e) => {
  if (!document.contains(e.target)) return;
  const wrap = document.getElementById('watchlist-profile-wrap');
  if (wrap && !wrap.contains(e.target)) {
    closeWatchlistProfileMenu();
  }
  const sWrap = document.getElementById('watchlist-sort-wrap');
  if (sWrap && !sWrap.contains(e.target)) {
    closeWatchlistSortMenu();
  }
  const fWrap = document.getElementById('watchlist-filter-mode-wrap');
  if (fWrap && !fWrap.contains(e.target)) {
    closeWatchlistFilterMenu();
  }
});

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    closeWatchlistProfileMenu();
    closeWatchlistSortMenu();
    closeWatchlistFilterMenu();
    const modal = document.getElementById('profile-pin-modal');
    if (modal && modal.style.display !== 'none') {
      closeProfilePinModal();
    }
    const wModal = document.getElementById('watcher-modal');
    if (wModal && wModal.style.display !== 'none') {
      closeWatcherModal();
    }
  }
});

function openProfilePinModal(profile, errorMsg = '') {
  pendingPinProfile = profile;
  const avatarEl = document.getElementById('modal-pin-avatar');
  const subEl = document.getElementById('modal-pin-subtitle');
  const inputEl = document.getElementById('profile-pin-input');
  const rememberCb = document.getElementById('profile-pin-remember');
  const errEl = document.getElementById('modal-pin-error');
  const modal = document.getElementById('profile-pin-modal');
  const btn = document.getElementById('btn-submit-pin');

  if (avatarEl) {
    avatarEl.src = profile?.avatar_url || 'https://static.crunchyroll.com/assets/avatar/170x170/0001-cr-white-orange.png';
  }
  if (subEl) {
    subEl.textContent = profile?.name ? `Enter PIN for ${profile.name}` : 'Profile is protected';
  }
  if (inputEl) {
    inputEl.value = '';
  }
  if (rememberCb) {
    rememberCb.checked = true;
  }
  if (errEl) {
    if (errorMsg) {
      errEl.textContent = errorMsg;
      errEl.style.display = 'block';
    } else {
      errEl.textContent = '';
      errEl.style.display = 'none';
    }
  }
  if (btn) {
    btn.disabled = false;
    btn.textContent = 'unlock';
  }
  if (modal) {
    modal.style.display = 'flex';
  }
  setTimeout(() => {
    if (inputEl) inputEl.focus();
  }, 60);
}

function closeProfilePinModal() {
  const modal = document.getElementById('profile-pin-modal');
  if (modal) modal.style.display = 'none';
  pendingPinProfile = null;
  const inputEl = document.getElementById('profile-pin-input');
  if (inputEl) inputEl.value = '';
}

function handlePinModalBackdropClick(e) {
  if (e && e.target && e.target.id === 'profile-pin-modal') {
    closeProfilePinModal();
  }
}

async function submitProfilePin(e) {
  if (e) e.preventDefault();
  if (!pendingPinProfile) return;

  const inputEl = document.getElementById('profile-pin-input');
  const rememberCb = document.getElementById('profile-pin-remember');
  const pin = (inputEl ? inputEl.value : '').trim();
  const rememberPin = rememberCb ? Boolean(rememberCb.checked) : false;
  const errEl = document.getElementById('modal-pin-error');
  const btn = document.getElementById('btn-submit-pin');

  if (!pin) {
    if (errEl) {
      errEl.textContent = 'Please enter your profile PIN';
      errEl.style.display = 'block';
    }
    if (inputEl) inputEl.focus();
    return;
  }

  if (btn) {
    btn.disabled = true;
    btn.textContent = 'verifying...';
  }

  const targetProfile = pendingPinProfile;
  const res = await executeProfileSwitch(targetProfile.profile_id, pin, rememberPin);

  if (res && res.success) {
    sessionProfilePins[targetProfile.profile_id] = pin;
    closeProfilePinModal();
  } else {
    delete sessionProfilePins[targetProfile.profile_id];
    if (errEl) {
      errEl.textContent = res?.error || 'Invalid PIN. Try again.';
      errEl.style.display = 'block';
    }
    if (inputEl) {
      inputEl.select();
      inputEl.focus();
    }
  }

  if (btn) {
    btn.disabled = false;
    btn.textContent = 'unlock';
  }
}

function renderWatchlistProfileSwitcher(profiles) {
  const wrap = document.getElementById('watchlist-profile-wrap');
  const triggerAvatar = document.getElementById('watchlist-profile-avatar');
  const triggerName = document.getElementById('watchlist-profile-name');
  const menu = document.getElementById('watchlist-profile-menu');
  if (!wrap || !profiles || !profiles.length) {
    if (wrap) wrap.style.display = 'none';
    return;
  }

  const active = profiles.find(p => p.is_selected) || profiles.find(p => p.is_primary) || profiles[0];
  activeProfile = active;

  if (triggerAvatar) {
    triggerAvatar.src = active.avatar_url || 'https://static.crunchyroll.com/assets/avatar/170x170/0001-cr-white-orange.png';
  }
  if (triggerName) {
    triggerName.textContent = active.name || 'Profile';
  }

  if (menu) {
    menu.innerHTML = profiles.map(p => `
      <div class="watchlist-profile-item ${p.profile_id === active.profile_id ? 'active' : ''}" onclick="switchWatchlistProfile('${escapeHtml(p.profile_id)}')">
        <img class="watchlist-profile-avatar-sm" src="${escapeHtml(p.avatar_url || 'https://static.crunchyroll.com/assets/avatar/170x170/0001-cr-white-orange.png')}" alt="" onerror="this.src='https://static.crunchyroll.com/assets/avatar/170x170/0001-cr-white-orange.png'">
        <div class="watchlist-profile-meta">
          <div class="watchlist-profile-meta-top">
            <span class="watchlist-profile-item-name">${escapeHtml(p.name)}</span>
            ${p.is_pin_protected ? `<span class="watchlist-profile-lock" title="${p.has_saved_pin ? 'PIN protected (remembered on this device)' : 'PIN protected'}"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect><path d="M7 11V7a5 5 0 0 1 10 0v4"></path></svg></span>` : ''}
          </div>
          ${p.is_primary ? '<span class="watchlist-profile-tag">Primary</span>' : ''}
        </div>
        ${p.profile_id === active.profile_id ? '<svg class="watchlist-profile-check" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"></polyline></svg>' : ''}
      </div>
    `).join('');
  }

  wrap.style.display = 'inline-flex';
}

async function loadUserWatchlist(force = false) {
  const loadingEl = document.getElementById('watchlist-loading');
  const errorEl = document.getElementById('watchlist-error');
  const emptyEl = document.getElementById('watchlist-empty');
  const unauthEl = document.getElementById('watchlist-unauth');
  const listEl = document.getElementById('watchlist-list');
  const filterInput = document.getElementById('watchlist-filter-input');

  try {
    if (loadingEl) loadingEl.style.display = 'flex';
    if (errorEl) errorEl.style.display = 'none';
    if (emptyEl) emptyEl.style.display = 'none';
    if (unauthEl) unauthEl.style.display = 'none';
    if (listEl) listEl.innerHTML = '';
    selectedWatchlistIds.clear();
    updateWatchlistBatchBar();

    // Fetch watchlist and profiles in parallel for maximum speed
    const promises = [
      api('/api/watchlist' + (force ? '?_t=' + Date.now() : ''))
    ];
    if (!cachedUserProfiles || force) {
      promises.push(api('/api/profiles'));
    }

    const [wRes, pRes] = await Promise.all(promises);

    if (pRes && pRes.success && pRes.profiles) {
      cachedUserProfiles = pRes.profiles;
      renderWatchlistProfileSwitcher(pRes.profiles);
    } else if (cachedUserProfiles) {
      renderWatchlistProfileSwitcher(cachedUserProfiles);
    }

    if (!wRes || !wRes.success) {
      if (wRes && wRes.error && wRes.error.toLowerCase().includes('authentication required')) {
        if (unauthEl) unauthEl.style.display = 'block';
        return;
      }
      throw new Error(wRes?.error || 'Failed to fetch watchlist');
    }

    allWatchlistItems = (wRes.items || []).map((item, idx) => ({ ...item, _origIdx: idx }));
    if (filterInput) filterInput.value = '';
    currentWatchlistFilter = '';
    const clearBtn = document.getElementById('watchlist-filter-clear');
    if (clearBtn) clearBtn.style.display = 'none';

    renderWatchlistList();
  } catch (err) {
    console.error('loadUserWatchlist error:', err);
    if (errorEl) {
      errorEl.textContent = 'Error: ' + (err.message || err);
      errorEl.style.display = 'block';
    }
    toast('Could not load watchlist', 'err');
    watchlistLoaded = false;
  } finally {
    if (loadingEl) loadingEl.style.display = 'none';
  }
}

async function switchWatchlistProfile(profileId) {
  if (!profileId) return;
  closeWatchlistProfileMenu();

  if (activeProfile && activeProfile.profile_id === profileId) {
    return;
  }

  const target = (cachedUserProfiles || []).find(p => p.profile_id === profileId);

  // If in-memory session has a PIN, try it first
  if (sessionProfilePins[profileId]) {
    const res = await executeProfileSwitch(profileId, sessionProfilePins[profileId]);
    if (res.success) return;
    // Session PIN was rejected (e.g. changed on Crunchyroll)
    delete sessionProfilePins[profileId];
    if (target) {
      openProfilePinModal(target, 'Invalid PIN. Please enter your new PIN.');
    }
    return;
  }

  // If profile is marked PIN protected but has saved PIN on backend:
  // attempt switch without pin to let backend test the saved_profile_pins
  if (target && target.is_pin_protected && target.has_saved_pin) {
    const res = await executeProfileSwitch(profileId, null);
    if (res.success) return;
    // Backend saved pin was invalid or expired: prompt for new pin
    openProfilePinModal(target, 'Invalid PIN. Please enter your new PIN.');
    return;
  }

  // If profile is PIN protected with no saved PIN, open PIN prompt directly
  if (target && target.is_pin_protected) {
    openProfilePinModal(target);
    return;
  }

  // Standard switch (unprotected profile)
  const res = await executeProfileSwitch(profileId, null);
  if (!res.success && res.requires_pin && target) {
    openProfilePinModal(target, res.error ? 'Invalid PIN. Please enter your new PIN.' : '');
  }
}

async function executeProfileSwitch(profileId, pin = null, rememberPin = false) {
  const loadingEl = document.getElementById('watchlist-loading');
  try {
    if (loadingEl) loadingEl.style.display = 'flex';
    const payload = { profile_id: profileId };
    if (pin) payload.pin = pin;
    if (rememberPin) payload.remember_pin = true;

    const res = await api('/api/profiles/switch', payload);
    if (res && res.success) {
      toast('Switched profile', 'ok');
      cachedUserProfiles = null;
      await loadUserWatchlist(true);
      return { success: true };
    } else {
      const isPinReq = Boolean(res?.requires_pin);
      if (!isPinReq) {
        toast('Failed to switch profile: ' + (res?.error || 'Unknown error'), 'err');
      }
      return { success: false, requires_pin: isPinReq, error: res?.error || 'Failed to switch profile' };
    }
  } catch (err) {
    console.error('executeProfileSwitch error:', err);
    toast('Error switching profile', 'err');
    return { success: false, error: err.message || 'Error switching profile' };
  } finally {
    if (loadingEl) loadingEl.style.display = 'none';
  }
}

function filterWatchlist(query) {
  currentWatchlistFilter = (query || '').trim().toLowerCase();
  const clearBtn = document.getElementById('watchlist-filter-clear');
  if (clearBtn) clearBtn.style.display = currentWatchlistFilter ? 'inline-block' : 'none';
  renderWatchlistList();
}

function clearWatchlistFilter() {
  const filterInput = document.getElementById('watchlist-filter-input');
  if (filterInput) {
    filterInput.value = '';
    filterInput.focus();
  }
  filterWatchlist('');
}

function renderWatchlistList() {
  const listEl = document.getElementById('watchlist-list');
  const emptyEl = document.getElementById('watchlist-empty');
  if (!listEl) return;

  if (!allWatchlistItems.length) {
    listEl.innerHTML = '';
    if (emptyEl) emptyEl.style.display = 'block';
    return;
  }
  if (emptyEl) emptyEl.style.display = 'none';

  // 1. Filter by mode (unwatched, in-progress, watched, favorites, series, movies)
  let filtered = allWatchlistItems.filter((item, idx) => {
    if (typeof item._origIdx === 'undefined') item._origIdx = idx;

    if (currentWatchlistFilterMode === 'unwatched') {
      return Boolean(item.never_watched) || (Number(item.playhead || 0) === 0 && !item.fully_watched);
    }
    if (currentWatchlistFilterMode === 'in-progress') {
      return Number(item.playhead || 0) > 0 && !item.fully_watched;
    }
    if (currentWatchlistFilterMode === 'watched') {
      return Boolean(item.fully_watched);
    }
    if (currentWatchlistFilterMode === 'favorites') {
      return Boolean(item.is_favorite);
    }
    if (currentWatchlistFilterMode === 'monitored') {
      return monitoredSeriesMap.has(item.id);
    }
    if (currentWatchlistFilterMode === 'series') {
      return item.type !== 'movie';
    }
    if (currentWatchlistFilterMode === 'movies') {
      return item.type === 'movie';
    }
    return true; // 'all'
  });

  // 2. Filter by search input query
  if (currentWatchlistFilter) {
    filtered = filtered.filter(item => {
      const title = (item.title || '').toLowerCase();
      const desc = (item.description || '').toLowerCase();
      return title.includes(currentWatchlistFilter) || desc.includes(currentWatchlistFilter);
    });
  }

  // 3. Handle empty state
  if (!filtered.length) {
    if (currentWatchlistFilter) {
      listEl.innerHTML = `<div class="catalog-empty">No anime in watchlist matching "${escapeHtml(currentWatchlistFilter)}"</div>`;
    } else {
      const modeLabels = {
        'unwatched': 'unwatched',
        'in-progress': 'in-progress',
        'watched': 'watched',
        'favorites': 'favorite',
        'monitored': 'monitored for auto-download',
        'series': 'series',
        'movies': 'movie'
      };
      const label = modeLabels[currentWatchlistFilterMode] || currentWatchlistFilterMode;
      listEl.innerHTML = `
        <div class="catalog-empty">
          <p>No ${escapeHtml(label)} items found in your watchlist.</p>
          <button type="button" class="btn-s" style="margin-top:10px;" onclick="setWatchlistFilterMode('all')">Show all items</button>
        </div>
      `;
    }
    return;
  }

  // 4. Sort items
  const sorted = [...filtered].sort((a, b) => {
    switch (currentWatchlistSort) {
      case 'alpha-asc':
        return (a.title || '').localeCompare(b.title || '', undefined, { sensitivity: 'base' });
      case 'alpha-desc':
        return (b.title || '').localeCompare(a.title || '', undefined, { sensitivity: 'base' });
      case 'watched-newest': {
        const scoreA = a.fully_watched ? 2 : (a.playhead > 0 ? 1 : 0);
        const scoreB = b.fully_watched ? 2 : (b.playhead > 0 ? 1 : 0);
        if (scoreA !== scoreB) return scoreB - scoreA;
        if ((b.playhead || 0) !== (a.playhead || 0)) return (b.playhead || 0) - (a.playhead || 0);
        return (a._origIdx || 0) - (b._origIdx || 0);
      }
      case 'updated-newest': {
        const dateA = a.upload_date ? new Date(a.upload_date).getTime() : 0;
        const dateB = b.upload_date ? new Date(b.upload_date).getTime() : 0;
        if (dateA !== dateB) return dateB - dateA;
        return (a._origIdx || 0) - (b._origIdx || 0);
      }
      case 'added-newest':
      case 'recent':
      default:
        return (a._origIdx || 0) - (b._origIdx || 0);
    }
  });

  listEl.innerHTML = sorted.map((item, idx) => {
    const id = item.id || `item-${idx + 1}`;
    const title = item.title || 'Untitled';
    const desc = item.description || '';
    const posterSrc = item.poster_url || '';
    const url = item.url || `https://www.crunchyroll.com/series/${id}`;
    const isSelected = selectedWatchlistIds.has(id);
    const isFav = Boolean(item.is_favorite);
    const isWatched = Boolean(item.fully_watched);
    const isProgress = !isWatched && Number(item.playhead || 0) > 0;
    const isUnwatched = Boolean(item.never_watched) || (!isWatched && Number(item.playhead || 0) === 0);
    const isMovie = item.type === 'movie';
    const isMonitored = monitoredSeriesMap.has(id);

    let pct = 0;
    if (isWatched) {
      pct = 100;
    } else if (isProgress && item.duration_ms) {
      const durSec = item.duration_ms / 1000;
      const curSec = item.playhead > 36000 ? item.playhead / 1000 : item.playhead;
      pct = Math.min(100, Math.max(5, Math.round((curSec / durSec) * 100)));
    }

    const badges = [];
    badges.push('<span class="res-badge">WATCHLIST</span>');
    if (isMovie) {
      badges.push('<span class="res-badge">MOVIE</span>');
    }
    if (isMonitored) {
      badges.push('<span class="res-badge res-badge-monitored">AUTO-DL</span>');
    }
    if (isFav) {
      badges.push('<span class="res-badge res-badge-sub">FAVORITE</span>');
    }
    if (isWatched) {
      badges.push('<span class="res-badge res-badge-watched">WATCHED</span>');
    } else if (isProgress) {
      badges.push('<span class="res-badge res-badge-progress">IN PROGRESS</span>');
    } else if (isUnwatched) {
      badges.push('<span class="res-badge res-badge-unwatched">UNWATCHED</span>');
    }
    if (item.is_new) {
      badges.push('<span class="res-badge" style="background:rgba(255,255,255,0.12);color:var(--white);border:1px solid rgba(255,255,255,0.3);">NEW</span>');
    }

    return `
      <div class="catalog-card ${isSelected ? 'selected' : ''}" data-id="${escapeHtml(id)}" data-url="${escapeHtml(url)}" tabindex="0">
        <div class="catalog-poster-box">
          ${posterSrc
            ? `<img class="catalog-poster" src="${escapeHtml(posterSrc)}" alt="${escapeHtml(title)}" loading="lazy" onerror="this.style.opacity='0.2'">`
            : `<div class="catalog-poster catalog-poster-empty"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg></div>`
          }
          ${pct > 0 ? `<div class="catalog-poster-progress-track"><div class="catalog-poster-progress-fill" style="width: ${pct}%"></div></div>` : ''}
        </div>
        <div class="catalog-content">
          <div class="catalog-title-row">
            <h3 class="catalog-title" title="${escapeHtml(title)}">${escapeHtml(title)}</h3>
            <div class="catalog-selected-badge">
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="20 6 9 17 4 12"></polyline>
              </svg>
            </div>
          </div>
          <div class="catalog-badges">
            ${badges.join('')}
          </div>
          <p class="catalog-desc" title="${escapeHtml(desc)}">${escapeHtml(desc)}</p>
          <div class="catalog-footer">
            <span class="catalog-meta-info" title="${escapeHtml(id)}">${escapeHtml(id)}</span>
            <div class="catalog-card-actions">
              <button type="button" class="btn-s ${isMonitored ? 'btn-monitor-active' : 'btn-monitor'}" onclick="toggleMonitorSeries(event, '${escapeHtml(id)}')" title="${isMonitored ? 'Auto-download active. Click to stop.' : 'Auto-download new episodes when they air'}">${isMonitored ? 'auto-dl ✓' : 'auto-dl'}</button>
              <button type="button" class="btn-s catalog-fetch-btn" data-url="${escapeHtml(url)}" title="Fetch this anime into dashboard">fetch</button>
              <button type="button" class="btn-s btn-pri catalog-fetch-btn catalog-dl-now-btn" data-url="${escapeHtml(url)}" title="Directly enqueue full series">download</button>
            </div>
          </div>
        </div>
      </div>
    `;
  }).join('');

  // Attach card click handlers for selection
  listEl.querySelectorAll('.catalog-card').forEach(card => {
    card.addEventListener('click', (e) => {
      if (e.target.closest('.catalog-card-actions')) return;
      const id = card.dataset.id;
      if (!id) return;
      if (selectedWatchlistIds.has(id)) {
        selectedWatchlistIds.delete(id);
        card.classList.remove('selected');
      } else {
        selectedWatchlistIds.add(id);
        card.classList.add('selected');
      }
      updateWatchlistBatchBar();
    });
  });

  // Attach fetch & download button listeners
  listEl.querySelectorAll('.catalog-fetch-btn:not(.catalog-dl-now-btn)').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      e.stopPropagation();
      const url = btn.dataset.url;
      if (!url) return;
      switchTab('dashboard');
      await fetchUrl(url, true);
    });
  });

  listEl.querySelectorAll('.catalog-dl-now-btn').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      e.stopPropagation();
      const url = btn.dataset.url;
      if (!url) return;
      await instantDownloadAnimeList([url]);
    });
  });

  updateWatchlistBatchBar();
}

function toggleSelectAllWatchlist() {
  const visibleCards = document.querySelectorAll('#watchlist-list .catalog-card');
  if (!visibleCards.length) return;

  const allVisibleSelected = Array.from(visibleCards).every(card => selectedWatchlistIds.has(card.dataset.id));
  const newSelection = !allVisibleSelected;

  visibleCards.forEach(card => {
    const id = card.dataset.id;
    if (newSelection) {
      selectedWatchlistIds.add(id);
    } else {
      selectedWatchlistIds.delete(id);
    }
    card.classList.toggle('selected', newSelection);
  });

  updateWatchlistBatchBar();
}

function selectAllWatchlist(select) {
  if (!select) {
    selectedWatchlistIds.clear();
    document.querySelectorAll('#watchlist-list .catalog-card').forEach(card => {
      card.classList.remove('selected');
    });
    updateWatchlistBatchBar();
  } else {
    toggleSelectAllWatchlist();
  }
}

function updateWatchlistBatchBar() {
  const count = selectedWatchlistIds.size;
  const batchBar = document.getElementById('watchlist-batch-bar');
  const countEl = document.getElementById('watchlist-selected-count');
  const selectAllBtn = document.getElementById('watchlist-select-all-btn');

  if (batchBar && countEl) {
    if (count > 0) {
      countEl.textContent = `${count} ${count === 1 ? 'anime' : 'animes'} selected`;
      batchBar.style.display = 'flex';
    } else {
      batchBar.style.display = 'none';
    }
  }

  if (selectAllBtn) {
    const visibleCards = document.querySelectorAll('#watchlist-list .catalog-card');
    const allSelected = visibleCards.length > 0 && Array.from(visibleCards).every(c => selectedWatchlistIds.has(c.dataset.id));
    const span = selectAllBtn.querySelector('span');
    if (span) span.textContent = allSelected ? 'deselect all' : 'select all';
  }
}

function getSelectedWatchlistUrls() {
  const urls = [];
  selectedWatchlistIds.forEach(id => {
    urls.push(`https://www.crunchyroll.com/series/${id}`);
  });
  return urls;
}

async function fetchSelectedWatchlist() {
  const urls = getSelectedWatchlistUrls();
  if (!urls.length) {
    toast('No animes selected', 'err');
    return;
  }
  switchTab('dashboard');
  await fetchUrl(urls, true);
  selectedWatchlistIds.clear();
  updateWatchlistBatchBar();
}

async function instantDownloadSelectedWatchlist() {
  const urls = getSelectedWatchlistUrls();
  if (!urls.length) {
    toast('No animes selected', 'err');
    return;
  }
  await instantDownloadAnimeList(urls);
  selectedWatchlistIds.clear();
  updateWatchlistBatchBar();
}

async function monitorSelectedWatchlist() {
  if (!selectedWatchlistIds.size) return;

  const ids = Array.from(selectedWatchlistIds);
  toast(`Enabling auto-download for ${ids.length} show(s)...`, 'info');

  let successCount = 0;
  for (const sid of ids) {
    const item = allWatchlistItems.find(it => it.id === sid) || {};
    try {
      const res = await api('/api/watcher/monitor', {
        series_id: sid,
        title: item.title || sid,
        url: item.url || `https://www.crunchyroll.com/series/${sid}`,
        poster: item.poster_url || '',
        mode: 'latest_only',
      });
      if (res && res.success) {
        monitoredSeriesMap.set(sid, res.series);
        successCount++;
      }
    } catch (_) {}
  }

  selectedWatchlistIds.clear();
  updateWatchlistBatchBar();
  toast(`Auto-download enabled for ${successCount} show(s)!`, 'ok');
  renderWatchlistList();

  const sRes = await api('/api/watcher/status');
  if (sRes && sRes.success) updateWatcherState(sRes);
}

function formatTimeAgo(isoStr) {
  if (!isoStr) return '';
  try {
    const diffSec = Math.round((Date.now() - new Date(isoStr).getTime()) / 1000);
    if (diffSec < 60) return 'just now';
    const mins = Math.floor(diffSec / 60);
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    return `${days}d ago`;
  } catch (_) {
    return '';
  }
}

function updateWatcherState(wState) {
  if (!wState) return;
  watcherState = { ...watcherState, ...wState };
  monitoredSeriesMap = new Map((wState.series || []).map(s => [s.id, s]));

  const strip = document.getElementById('watcher-strip');
  const dot = document.getElementById('watcher-dot');
  const statusText = document.getElementById('watcher-status-text');
  const metaText = document.getElementById('watcher-last-check');

  if (strip && dot && statusText && metaText) {
    if (wState.enabled) {
      dot.className = 'watcher-pulse-dot' + (wState.is_checking ? ' scanning' : '');
      dot.title = wState.is_checking ? 'Scanning anime...' : 'Auto-downloader active';
      statusText.textContent = wState.is_checking
        ? 'Auto-Downloader: Scanning...'
        : 'Auto-Downloader: Active';
      const count = wState.monitored_count || 0;
      const timeStr = formatTimeAgo(wState.last_check_time);
      metaText.textContent = `Monitoring ${count} show${count === 1 ? '' : 's'}${timeStr ? ' • Checked ' + timeStr : ''}`;
    } else {
      dot.className = 'watcher-pulse-dot disabled';
      dot.title = 'Auto-downloader disabled';
      statusText.textContent = 'Auto-Downloader: Paused';
      metaText.textContent = 'Auto-downloader paused';
    }
  }

  // Update master toggle button and interval select
  updateWatcherMasterButton();
  const intervalSelect = document.getElementById('watcher-interval');
  if (intervalSelect && wState.interval_minutes !== undefined && document.activeElement !== intervalSelect) {
    const intStr = String(wState.interval_minutes);
    if (intervalSelect.value !== intStr) {
      intervalSelect.value = intStr;
    }
  }

  // Handle unread notifications
  if (Array.isArray(wState.unread_notifications) && wState.unread_notifications.length) {
    wState.unread_notifications.forEach(n => {
      toast(`Auto-Downloader: Detected new episode for ${n.series_title} (${n.last_episode})! Added to queue.`, 'ok');
    });
  }

  // If modal is open, refresh series list
  const modal = document.getElementById('watcher-modal');
  if (modal && modal.style.display !== 'none') {
    renderWatcherModalSeries();
  }

  // Synchronize badges and cards across all tabs
  syncAllMonitoredCards();
}

async function triggerWatcherCheckNow() {
  const btn = document.getElementById('btn-watcher-check-now');
  if (btn) {
    btn.disabled = true;
    btn.classList.add('loading');
  }
  toast('Checking monitored anime for new episodes...', 'info');
  try {
    const res = await api('/api/watcher/check-now', {});
    if (res && res.success) {
      toast('Scan started! Check queue/logs for updates.', 'ok');
    } else {
      toast(res?.error || 'Failed to start scan', 'err');
    }
  } catch (err) {
    toast('Error checking episodes: ' + err.message, 'err');
  } finally {
    setTimeout(() => {
      if (btn) {
        btn.disabled = false;
        btn.classList.remove('loading');
      }
    }, 1500);
  }
}

// ==========================================
// Auto-DL Mode Popover (Individual Series Mode Picker)
// ==========================================

let activePopoverSeries = null;

function openAutoDlModePopover(anchorEl, seriesData) {
  let popover = document.getElementById('autodl-mode-popover');
  if (!popover) {
    popover = document.createElement('div');
    popover.id = 'autodl-mode-popover';
    popover.className = 'autodl-mode-popover';
    document.body.appendChild(popover);
  }

  // If already open for this same anchor, close it
  if (popover.style.display !== 'none' && activePopoverSeries && activePopoverSeries.id === seriesData.id) {
    hideAutoDlModePopover();
    return;
  }

  const sid = seriesData.id;
  const isMon = monitoredSeriesMap.has(sid);
  const monItem = monitoredSeriesMap.get(sid) || {};
  const curMode = monItem.mode || 'latest_only';
  const title = seriesData.title || monItem.title || sid;
  const url = seriesData.url || monItem.url || `https://www.crunchyroll.com/series/${sid}`;
  const poster = seriesData.poster || monItem.poster || '';

  activePopoverSeries = {
    id: sid,
    title: title,
    url: url,
    poster: poster,
    isMonitored: isMon,
    curMode: curMode,
  };

  if (!isMon) {
    popover.innerHTML = `
      <div class="autodl-popover-header">
        <div class="autodl-popover-title">Add to Auto-Downloader</div>
        <div class="autodl-popover-subtitle" title="${escapeHtml(title)}">${escapeHtml(title)}</div>
      </div>
      <div class="autodl-popover-options">
        <button type="button" class="autodl-popover-option" onclick="handlePopoverSelectMode('latest_only')">
          <div class="autodl-popover-opt-body">
            <div class="autodl-popover-opt-title">Future Only</div>
            <div class="autodl-popover-opt-desc">Only downloads new weekly episodes as they air</div>
          </div>
        </button>
        <button type="button" class="autodl-popover-option" onclick="handlePopoverSelectMode('all_missing')">
          <div class="autodl-popover-opt-body">
            <div class="autodl-popover-opt-title">All Missing</div>
            <div class="autodl-popover-opt-desc">Downloads entire backlog + new episodes</div>
          </div>
        </button>
      </div>
    `;
  } else {
    popover.innerHTML = `
      <div class="autodl-popover-header">
        <div class="autodl-popover-title">Auto-Download Settings</div>
        <div class="autodl-popover-subtitle" title="${escapeHtml(title)}">${escapeHtml(title)}</div>
      </div>
      <div class="autodl-popover-options">
        <button type="button" class="autodl-popover-option ${curMode === 'latest_only' ? 'active' : ''}" onclick="handlePopoverSelectMode('latest_only')">
          <div class="autodl-popover-opt-body">
            <div class="autodl-popover-opt-title">Future Only</div>
            <div class="autodl-popover-opt-desc">Only downloads new weekly episodes</div>
          </div>
        </button>
        <button type="button" class="autodl-popover-option ${curMode === 'all_missing' ? 'active' : ''}" onclick="handlePopoverSelectMode('all_missing')">
          <div class="autodl-popover-opt-body">
            <div class="autodl-popover-opt-title">All Missing</div>
            <div class="autodl-popover-opt-desc">Downloads entire backlog + new episodes</div>
          </div>
        </button>
      </div>
      <div class="autodl-popover-divider"></div>
      <div class="autodl-popover-footer">
        <button type="button" class="autodl-popover-stop-btn" onclick="handlePopoverStop()">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
          Stop Auto-Download
        </button>
      </div>
    `;
  }

  popover.style.display = 'flex';
  const rect = anchorEl.getBoundingClientRect();
  const popWidth = 260;
  const popHeight = popover.offsetHeight || 180;

  let left = rect.left;
  if (left + popWidth > window.innerWidth - 12) {
    left = Math.max(12, window.innerWidth - popWidth - 12);
  }

  let top = rect.bottom + 6;
  if (top + popHeight > window.innerHeight - 10) {
    top = Math.max(10, rect.top - popHeight - 6);
  }

  popover.style.left = `${Math.round(left)}px`;
  popover.style.top = `${Math.round(top)}px`;
}

function hideAutoDlModePopover() {
  const popover = document.getElementById('autodl-mode-popover');
  if (popover) {
    popover.style.display = 'none';
  }
  activePopoverSeries = null;
}

async function handlePopoverSelectMode(mode) {
  if (!activePopoverSeries) return;
  const series = { ...activePopoverSeries };
  hideAutoDlModePopover();

  if (series.isMonitored) {
    await changeAutoDlSeriesMode(series.id, mode);
  } else {
    await toggleMonitorSeries(null, series.id, series.title, series.url, series.poster, mode);
  }
}

async function handlePopoverStop() {
  if (!activePopoverSeries) return;
  const sid = activePopoverSeries.id;
  hideAutoDlModePopover();
  await removeMonitoredSeries(sid);
}

document.addEventListener('click', (e) => {
  if (!document.contains(e.target)) return;
  const popover = document.getElementById('autodl-mode-popover');
  if (popover && popover.style.display !== 'none') {
    if (!popover.contains(e.target) && !e.target.closest('.btn-monitor, .btn-monitor-active, .catalog-autodl-btn, .search-autodl-btn, #url-autodl-btn')) {
      hideAutoDlModePopover();
    }
  }
});

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    hideAutoDlModePopover();
  }
});

window.addEventListener('resize', hideAutoDlModePopover);

async function toggleMonitorSeries(e, seriesId, customTitle, customUrl, customPoster, customMode) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  if (!seriesId) return;

  const isMonitored = monitoredSeriesMap.has(seriesId);

  // If no custom mode specified and triggered by user click, open the mode popover
  const anchor = e ? (e.currentTarget || e.target) : null;
  if (!customMode && anchor && anchor.getBoundingClientRect) {
    const wItem = allWatchlistItems.find(it => it.id === seriesId) || {};
    const cItem = allCatalogItems.find(it => it.id === seriesId) || {};
    const title = customTitle || wItem.title || cItem.title || seriesId;
    const url = customUrl || wItem.url || (cItem.id ? `https://www.crunchyroll.com/series/${cItem.id}` : `https://www.crunchyroll.com/series/${seriesId}`);
    const poster = customPoster || wItem.poster_url || '';

    openAutoDlModePopover(anchor, {
      id: seriesId,
      title: title,
      url: url,
      poster: poster,
      isMonitored: isMonitored,
    });
    return;
  }

  if (isMonitored && customMode === 'unmonitor') {
    try {
      const res = await api('/api/watcher/unmonitor', { series_id: seriesId });
      if (res && res.success) {
        monitoredSeriesMap.delete(seriesId);
        toast('Stopped auto-downloading for series');
        syncAllMonitoredCards();
        const sRes = await api('/api/watcher/status');
        if (sRes && sRes.success) updateWatcherState(sRes);
      } else {
        toast(res?.error || 'Failed to remove series', 'err');
      }
    } catch (err) {
      toast('Error removing series: ' + err.message, 'err');
    }
  } else {
    // Find anime details across watchlist, catalog, or custom parameters
    const wItem = allWatchlistItems.find(it => it.id === seriesId) || {};
    const cItem = allCatalogItems.find(it => it.id === seriesId) || {};
    const title = customTitle || wItem.title || cItem.title || seriesId;
    const url = customUrl || wItem.url || (cItem.id ? `https://www.crunchyroll.com/series/${cItem.id}` : `https://www.crunchyroll.com/series/${seriesId}`);
    const poster = customPoster || wItem.poster_url || '';
    const mode = customMode || 'latest_only';

    try {
      const res = await api('/api/watcher/monitor', {
        series_id: seriesId,
        title: title,
        url: url,
        poster: poster,
        mode: mode,
      });
      if (res && res.success) {
        monitoredSeriesMap.set(seriesId, res.series);
        const modeLabel = mode === 'all_missing' ? 'All Missing (Backlog + Future)' : 'Future Releases Only';
        toast(`Auto-download enabled for "${title}"! (${modeLabel})`, 'ok');
        syncAllMonitoredCards();
        if (mode === 'all_missing') {
          checkSingleMonitoredSeries(seriesId);
        }
        const sRes = await api('/api/watcher/status');
        if (sRes && sRes.success) updateWatcherState(sRes);
      } else {
        toast(res?.error || 'Failed to monitor series', 'err');
      }
    } catch (err) {
      toast('Error monitoring series: ' + err.message, 'err');
    }
  }
}

function openWatcherModal() {
  const modal = document.getElementById('watcher-modal');
  if (!modal) return;
  modal.style.display = 'flex';
  renderWatcherModalSeries();
}

function closeWatcherModal() {
  const modal = document.getElementById('watcher-modal');
  if (modal) modal.style.display = 'none';
}

function handleWatcherModalBackdropClick(e) {
  if (e && e.target && e.target.id === 'watcher-modal') {
    closeWatcherModal();
  }
}

function seriesHasOverrides(s) {
  return !!(s && (s.audio_lang || s.subs_lang || s.video_quality || s.download_dir
    || (s.audio_fallback !== null && s.audio_fallback !== undefined)));
}

const SERIES_CUSTOM_BADGE_HTML = '<span class="res-badge res-badge-custom" style="font-size:0.6rem;padding:1px 5px;" title="This anime has its own settings">CUSTOM</span>';

function renderWatcherModalSeries() {
  const listEl = document.getElementById('watcher-series-list');
  const emptyEl = document.getElementById('watcher-empty-list');
  if (!listEl) return;

  const seriesList = watcherState.series || [];
  if (!seriesList.length) {
    listEl.innerHTML = '';
    if (emptyEl) emptyEl.style.display = 'block';
    return;
  }
  if (emptyEl) emptyEl.style.display = 'none';

  const existingRows = listEl.querySelectorAll('.watcher-series-row');
  const existingIds = Array.from(existingRows).map(r => r.dataset.id).filter(Boolean);
  const newIds = seriesList.map(s => s.id);

  const hasStructureChanged = (existingIds.length !== newIds.length) ||
    existingIds.some((id, idx) => id !== newIds[idx]);

  if (!hasStructureChanged) {
    existingRows.forEach(row => {
      const sid = row.dataset.id;
      if (!sid) return;
      const s = seriesList.find(item => item.id === sid);
      if (!s) return;

      const modeBadge = row.querySelector('.res-badge-monitored');
      if (modeBadge) {
        modeBadge.textContent = s.mode === 'all_missing' ? 'ALL MISSING' : 'LATEST ONLY';
      }
      const lastEp = s.last_episode_name ? ` • Last: ${escapeHtml(s.last_episode_name)}` : '';
      const lastCheck = s.last_checked ? ` • Checked ${formatTimeAgo(s.last_checked)}` : '';
      const subSpan = row.querySelector('.watcher-series-sub span:last-child');
      if (subSpan) {
        subSpan.textContent = `${lastCheck}${lastEp}`;
      }
      const modeSel = row.querySelector('.autodl-card-mode-select');
      if (modeSel && document.activeElement !== modeSel) {
        const targetVal = s.mode === 'all_missing' ? 'all_missing' : 'latest_only';
        if (modeSel.value !== targetVal) modeSel.value = targetVal;
      }
      const subEl = row.querySelector('.watcher-series-sub');
      const customBadge = subEl ? subEl.querySelector('.res-badge-custom') : null;
      if (seriesHasOverrides(s) && !customBadge && modeBadge) {
        modeBadge.insertAdjacentHTML('afterend', SERIES_CUSTOM_BADGE_HTML);
      } else if (!seriesHasOverrides(s) && customBadge) {
        customBadge.remove();
      }
    });
    return;
  }

  if (listEl.contains(document.activeElement) && document.activeElement.tagName === 'SELECT') {
    return;
  }

  listEl.innerHTML = seriesList.map(s => {
    const sid = s.id || '';
    const title = s.title || sid;
    const poster = s.poster || '';
    const mode = s.mode === 'all_missing' ? 'ALL MISSING' : 'LATEST ONLY';
    const lastEp = s.last_episode_name ? ` • Last: ${escapeHtml(s.last_episode_name)}` : '';
    const lastCheck = s.last_checked ? ` • Checked ${formatTimeAgo(s.last_checked)}` : '';
    const overrideBadge = seriesHasOverrides(s) ? SERIES_CUSTOM_BADGE_HTML : '';

    return `
      <div class="watcher-series-row" data-id="${escapeHtml(sid)}">
        <div class="watcher-series-info">
          ${poster
            ? `<img class="watcher-series-poster" src="${escapeHtml(poster)}" alt="" onerror="this.style.opacity='0.2'">`
            : `<div class="watcher-series-poster" style="display:flex;align-items:center;justify-content:center;background:#1a1a1a;color:#555;"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2"/></svg></div>`
          }
          <div class="watcher-series-meta">
            <span class="watcher-series-title" title="${escapeHtml(title)}">${escapeHtml(title)}</span>
            <div class="watcher-series-sub">
              <span class="res-badge res-badge-monitored" style="font-size:0.6rem;padding:1px 5px;">${mode}</span>
              ${overrideBadge}
              <span>${lastCheck}${lastEp}</span>
            </div>
          </div>
        </div>
        <div class="watcher-series-actions">
          <select class="autodl-card-mode-select" onchange="changeAutoDlSeriesMode('${escapeHtml(sid)}', this.value)" title="Monitoring Mode">
            <option value="latest_only" ${s.mode !== 'all_missing' ? 'selected' : ''}>Future Only</option>
            <option value="all_missing" ${s.mode === 'all_missing' ? 'selected' : ''}>All Missing</option>
          </select>
          <button type="button" class="btn-s btn-gear" onclick="openSeriesSettings('${escapeHtml(sid)}')" title="Per-series settings (audio, subtitles, quality)">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>
          </button>
          <button type="button" class="btn-s" onclick="checkSingleMonitoredSeries('${escapeHtml(sid)}')" title="Check this anime for new episodes now">check</button>
          <button type="button" class="btn-s" onclick="removeMonitoredSeries('${escapeHtml(sid)}')" title="Stop monitoring this anime" style="color:#ff6666;">stop</button>
        </div>
      </div>
    `;
  }).join('');
}

// ---- Per-series settings (gear icon) ----
let seriesSettingsSid = null;
let ssAudioDD = null;
let ssSubsDD = null;
let ssQualityDD = null;
let ssFallbackDD = null;

function ensureSeriesSettingsDropdowns() {
  if (ssAudioDD) return;
  const inherit = { val: '', label: 'default (global)' };
  const noop = () => {};
  ssAudioDD = new CheckboxDropdown('ss-audio', null, [inherit, ...AUDIO_OPTIONS], '', noop, false);
  ssSubsDD = new CheckboxDropdown('ss-subs', null, [inherit, ...SUBS_OPTIONS], '', noop, false);
  ssQualityDD = new CheckboxDropdown('ss-quality', null, [inherit, ...VIDEO_OPTIONS], '', noop, false);
  ssFallbackDD = new CheckboxDropdown('ss-fallback', null, [
    inherit,
    { val: 'on', label: 'on' },
    { val: 'off', label: 'off' },
  ], '', noop, false);
}

function openSeriesSettings(sid) {
  const s = monitoredSeriesMap.get(sid);
  if (!s) return;
  seriesSettingsSid = sid;
  ensureSeriesSettingsDropdowns();
  document.getElementById('series-settings-title').textContent = s.title || sid;
  ssAudioDD.setValue(s.audio_lang || '', false);
  ssSubsDD.setValue(s.subs_lang || '', false);
  ssQualityDD.setValue(s.video_quality || '', false);
  ssFallbackDD.setValue(s.audio_fallback === true ? 'on' : (s.audio_fallback === false ? 'off' : ''), false);
  document.getElementById('ss-dir').value = s.download_dir || '';
  document.getElementById('series-settings-modal').style.display = 'flex';
}

function closeSeriesSettings() {
  const modal = document.getElementById('series-settings-modal');
  if (modal) modal.style.display = 'none';
  seriesSettingsSid = null;
}

function handleSeriesSettingsBackdropClick(e) {
  if (e.target && e.target.id === 'series-settings-modal') closeSeriesSettings();
}

function resetSeriesSettings() {
  if (!ssAudioDD) return;
  ssAudioDD.setValue('', false);
  ssSubsDD.setValue('', false);
  ssQualityDD.setValue('', false);
  ssFallbackDD.setValue('', false);
  document.getElementById('ss-dir').value = '';
}

async function saveSeriesSettings() {
  const sid = seriesSettingsSid;
  if (!sid) return;
  const fb = ssFallbackDD.value;
  const payload = {
    series_id: sid,
    audio_lang: ssAudioDD.value || null,
    subs_lang: ssSubsDD.value || null,
    video_quality: ssQualityDD.value || null,
    download_dir: (document.getElementById('ss-dir').value || '').trim() || null,
    audio_fallback: fb === 'on' ? true : (fb === 'off' ? false : null),
  };
  try {
    const res = await api('/api/watcher/update-series', payload);
    if (res && res.success) {
      monitoredSeriesMap.set(sid, res.series);
      toast('Series settings saved');
      closeSeriesSettings();
      const sRes = await api('/api/watcher/status');
      if (sRes && sRes.success) updateWatcherState(sRes);
      renderWatcherModalSeries();
    } else {
      toast(res?.error || 'Failed to save series settings', 'err');
    }
  } catch (err) {
    toast('Error saving series settings: ' + err.message, 'err');
  }
}

async function checkSingleMonitoredSeries(sid) {
  if (!sid) return;
  toast('Checking for new episodes...', 'info');
  try {
    const res = await api('/api/watcher/check-series', { series_id: sid });
    if (res && res.success) {
      if (res.new_episodes > 0) {
        toast(`Found & queued ${res.new_episodes} new episode(s)!`, 'ok');
      } else {
        toast('Already up to date — no new episodes.', 'ok');
      }
      const sRes = await api('/api/watcher/status');
      if (sRes && sRes.success) updateWatcherState(sRes);
    } else {
      toast(res?.error || 'Failed to check series', 'err');
    }
  } catch (err) {
    toast('Error checking series: ' + err.message, 'err');
  }
}

async function simulateWatcherRelease(sid) {
  if (!sid) return;
  toast('Simulating new episode drop (state rollback)...', 'info');
  try {
    const res = await api('/api/watcher/simulate-release', { series_id: sid });
    if (res && res.success) {
      if (res.new_episodes > 0) {
        toast(`Simulated drop detected! Queued ${res.new_episodes} episode(s) to download queue.`, 'ok');
      } else {
        toast('Simulated check completed (no episodes found).', 'info');
      }
      const sRes = await api('/api/watcher/status');
      if (sRes && sRes.success) updateWatcherState(sRes);
    } else {
      toast(res?.error || 'Failed to simulate release', 'err');
    }
  } catch (err) {
    toast('Simulation error: ' + err.message, 'err');
  }
}

async function removeMonitoredSeries(sid) {
  if (!sid) return;
  try {
    const res = await api('/api/watcher/unmonitor', { series_id: sid });
    if (res && res.success) {
      monitoredSeriesMap.delete(sid);
      toast('Stopped monitoring series');
      syncAllMonitoredCards();
      const sRes = await api('/api/watcher/status');
      if (sRes && sRes.success) updateWatcherState(sRes);
    } else {
      toast(res?.error || 'Failed to stop monitoring', 'err');
    }
  } catch (err) {
    toast('Error removing series: ' + err.message, 'err');
  }
}

function updateWatcherMasterButton() {
  const btn = document.getElementById('btn-autodl-master-pause');
  const txt = document.getElementById('btn-autodl-master-text');
  if (!btn || !txt) return;
  const isEnabled = watcherState.enabled !== false;
  const pauseIcon = btn.querySelector('.autodl-pause-icon');
  const resumeIcon = btn.querySelector('.autodl-resume-icon');

  if (isEnabled) {
    btn.classList.remove('paused');
    txt.textContent = 'pause';
    btn.title = 'Pause auto-downloader background checking';
    if (pauseIcon) pauseIcon.style.display = 'inline-block';
    if (resumeIcon) resumeIcon.style.display = 'none';
  } else {
    btn.classList.add('paused');
    txt.textContent = 'resume';
    btn.title = 'Resume auto-downloader background checking';
    if (pauseIcon) pauseIcon.style.display = 'none';
    if (resumeIcon) resumeIcon.style.display = 'inline-block';
  }
}

async function toggleWatcherMaster() {
  const newEnabled = !(watcherState.enabled !== false);
  const intervalVal = document.getElementById('watcher-interval')?.value || String(watcherState.interval_minutes || 60);
  try {
    const res = await api('/api/watcher/settings', {
      enabled: newEnabled,
      interval_minutes: parseFloat(intervalVal) || 60,
    });
    if (res && res.success) {
      watcherState = { ...watcherState, ...(res.settings || {}) };
      toast(newEnabled ? 'Auto-downloader resumed' : 'Auto-downloader paused', 'ok');
      updateWatcherMasterButton();
      syncAllMonitoredCards();
    }
  } catch (err) {
    toast('Failed to toggle auto-downloader: ' + err.message, 'err');
  }
}

async function saveWatcherSettings() {
  const enabled = watcherState.enabled !== false;
  const intervalVal = document.getElementById('watcher-interval')?.value || String(watcherState.interval_minutes || 60);

  try {
    const res = await api('/api/watcher/settings', {
      enabled: enabled,
      interval_minutes: parseFloat(intervalVal) || 60,
    });
    if (res && res.success) {
      toast('Auto-downloader interval saved', 'ok');
      watcherState = { ...watcherState, ...(res.settings || {}) };
      updateWatcherMasterButton();
      syncAllMonitoredCards();
    }
  } catch (err) {
    toast('Failed to save watcher settings: ' + err.message, 'err');
  }
}

// ==========================================
// AUTO-DOWNLOADER (WATCHER) DEDICATED TAB & SYNC
// ==========================================

let autoDlFilterQuery = '';
let autoDlFilterMode = 'all';

function syncAllMonitoredCards() {
  const count = monitoredSeriesMap.size;
  const navBadge = document.getElementById('nav-autodl-badge');
  if (navBadge) {
    navBadge.textContent = count;
    navBadge.style.display = count > 0 ? 'inline-flex' : 'none';
  }

  // Sync Watchlist cards
  document.querySelectorAll('#watchlist-list .catalog-card').forEach(card => {
    const id = card.dataset.id;
    if (!id) return;
    const isMon = monitoredSeriesMap.has(id);
    const mItem = monitoredSeriesMap.get(id);
    const modeDesc = mItem && mItem.mode === 'all_missing' ? 'All Missing' : 'Future Only';
    const btn = card.querySelector('.btn-monitor, .btn-monitor-active');
    if (btn) {
      btn.className = `btn-s ${isMon ? 'btn-monitor-active' : 'btn-monitor'}`;
      btn.textContent = isMon ? 'auto-dl ✓' : 'auto-dl';
      btn.title = isMon ? `Auto-download active (${modeDesc}). Click to change mode or stop.` : 'Add to auto-downloader';
    }
    const badgesEl = card.querySelector('.catalog-badges');
    if (badgesEl) {
      let monBadge = badgesEl.querySelector('.res-badge-monitored');
      if (isMon && !monBadge) {
        const span = document.createElement('span');
        span.className = 'res-badge res-badge-monitored';
        span.textContent = mItem && mItem.mode === 'all_missing' ? 'AUTO-DL (ALL)' : 'AUTO-DL';
        badgesEl.appendChild(span);
      } else if (isMon && monBadge) {
        monBadge.textContent = mItem && mItem.mode === 'all_missing' ? 'AUTO-DL (ALL)' : 'AUTO-DL';
      } else if (!isMon && monBadge) {
        monBadge.remove();
      }
    }
  });

  // Sync Catalog cards
  document.querySelectorAll('#catalog-list .catalog-card').forEach(card => {
    const id = card.dataset.id;
    if (!id) return;
    const seriesId = (card.dataset.url || '').replace(/.*\/series\//, '') || id;
    const isMon = monitoredSeriesMap.has(id) || monitoredSeriesMap.has(seriesId);
    const mItem = monitoredSeriesMap.get(id) || monitoredSeriesMap.get(seriesId);
    const modeDesc = mItem && mItem.mode === 'all_missing' ? 'All Missing' : 'Future Only';
    const btn = card.querySelector('.catalog-autodl-btn');
    if (btn) {
      btn.className = `btn-s ${isMon ? 'btn-monitor-active' : 'btn-monitor'} catalog-autodl-btn`;
      btn.textContent = isMon ? 'auto-dl ✓' : 'auto-dl';
      btn.title = isMon ? `Auto-download active (${modeDesc}). Click to change mode or stop.` : 'Add to auto-downloader';
    }
    const badgesEl = card.querySelector('.res-badges');
    if (badgesEl) {
      let monBadge = badgesEl.querySelector('.res-badge-monitored');
      if (isMon && !monBadge) {
        const span = document.createElement('span');
        span.className = 'res-badge res-badge-monitored';
        span.textContent = mItem && mItem.mode === 'all_missing' ? 'AUTO-DL (ALL)' : 'AUTO-DL';
        badgesEl.appendChild(span);
      } else if (isMon && monBadge) {
        monBadge.textContent = mItem && mItem.mode === 'all_missing' ? 'AUTO-DL (ALL)' : 'AUTO-DL';
      } else if (!isMon && monBadge) {
        monBadge.remove();
      }
    }
  });

  // Sync Search cards
  document.querySelectorAll('#search-results-list .search-result-card').forEach(card => {
    const cb = card.querySelector('.search-select-cb');
    const id = cb ? cb.dataset.id : null;
    if (!id) return;
    const isMon = monitoredSeriesMap.has(id);
    const mItem = monitoredSeriesMap.get(id);
    const modeDesc = mItem && mItem.mode === 'all_missing' ? 'All Missing' : 'Future Only';
    const btn = card.querySelector('.search-autodl-btn');
    if (btn) {
      btn.className = `btn-s ${isMon ? 'btn-monitor-active' : 'btn-monitor'} search-autodl-btn`;
      btn.textContent = isMon ? 'auto-dl ✓' : 'auto-dl';
      btn.title = isMon ? `Auto-download active (${modeDesc}). Click to change mode or stop.` : 'Add to auto-downloader';
    }
  });

  // Synchronize Auto-DL tab cards in place without destroying DOM
  const autodlTab = document.getElementById('tab-autodl');
  if (autodlTab && autodlTab.style.display !== 'none') {
    const gridEl = document.getElementById('autodl-series-grid');
    if (gridEl) {
      const existingCards = gridEl.querySelectorAll('.autodl-card-item');
      const existingIds = Array.from(existingCards).map(c => c.dataset.id).filter(Boolean);
      const allSeries = Array.from(monitoredSeriesMap.values());

      let filtered = allSeries;
      if (autoDlFilterMode === 'active') {
        filtered = filtered.filter(s => (s.status || 'active') === 'active');
      } else if (autoDlFilterMode === 'paused') {
        filtered = filtered.filter(s => s.status === 'paused');
      } else if (autoDlFilterMode === 'latest_only') {
        filtered = filtered.filter(s => (s.mode || 'latest_only') === 'latest_only');
      } else if (autoDlFilterMode === 'all_missing') {
        filtered = filtered.filter(s => s.mode === 'all_missing');
      }

      const filteredIds = filtered.map(s => s.id);
      const hasStructureChanged = (existingIds.length !== filteredIds.length) ||
        existingIds.some((id, idx) => id !== filteredIds[idx]);

      if (hasStructureChanged) {
        const activeTag = document.activeElement ? document.activeElement.tagName : '';
        const isInteracting = gridEl.contains(document.activeElement) && (activeTag === 'SELECT' || activeTag === 'INPUT');
        if (!isInteracting) {
          renderAutoDlTab();
        }
      } else {
        existingCards.forEach(card => {
          const sid = card.dataset.id;
          if (!sid) return;
          const s = monitoredSeriesMap.get(sid);
          if (!s) return;

          const isAllMissing = s.mode === 'all_missing';
          const pillWrap = card.querySelector('.autodl-pill-select-wrap');
          if (pillWrap) {
            pillWrap.classList.toggle('pill-all', isAllMissing);
            pillWrap.classList.toggle('pill-future', !isAllMissing);
          }

          const modeSel = card.querySelector('.autodl-card-mode-select');
          if (modeSel && document.activeElement !== modeSel) {
            const targetVal = isAllMissing ? 'all_missing' : 'latest_only';
            if (modeSel.value !== targetVal) modeSel.value = targetVal;
          }

          const isPaused = s.status === 'paused';
          card.classList.toggle('paused', isPaused);

          const headerLine = card.querySelector('.autodl-card-header-line');
          if (headerLine) {
            let pausedBadge = headerLine.querySelector('.res-badge-paused');
            if (isPaused && !pausedBadge) {
              const span = document.createElement('span');
              span.className = 'res-badge res-badge-paused';
              span.style.cssText = 'font-size:0.58rem;padding:1px 5px;flex-shrink:0;';
              span.textContent = 'PAUSED';
              headerLine.appendChild(span);
            } else if (!isPaused && pausedBadge) {
              pausedBadge.remove();
            }
          }

          const pauseBtn = card.querySelector('.btn-autodl-pause');
          if (pauseBtn) {
            pauseBtn.title = isPaused ? 'Resume monitoring' : 'Pause monitoring';
            const pauseSvg = isPaused
              ? '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>'
              : '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="4" width="4" height="16"></rect><rect x="14" y="4" width="4" height="16"></rect></svg>';
            if (pauseBtn.innerHTML.replace(/\s+/g, '') !== pauseSvg.replace(/\s+/g, '')) {
              pauseBtn.innerHTML = pauseSvg;
            }
          }

          const lastCheck = s.last_checked ? `Checked ${formatTimeAgo(s.last_checked)}` : 'Not checked yet';
          const knownCount = Array.isArray(s.known_episodes) ? s.known_episodes.length : 0;
          const dlCount = Array.isArray(s.downloaded_episodes) ? s.downloaded_episodes.length : 0;
          const lastEp = s.last_episode_name ? `Last: ${escapeHtml(s.last_episode_name)}` : '';

          const metaEl = card.querySelector('.autodl-card-meta');
          if (metaEl) {
            const metaHtml = `
              <span${lastEp ? ` title="${lastEp}"` : ''}>${lastCheck} • ${dlCount}/${knownCount} eps${lastEp ? ` • ${lastEp}` : ''}</span>
            `;
            if (metaEl.innerHTML.replace(/\s+/g, ' ') !== metaHtml.replace(/\s+/g, ' ')) {
              metaEl.innerHTML = metaHtml;
            }
          }
        });

        const statusDot = document.getElementById('autodl-page-status-dot');
        const statusTxt = document.getElementById('autodl-page-status-text');
        const countTxt = document.getElementById('autodl-page-count-text');
        if (statusDot && statusTxt && countTxt) {
          if (watcherState.enabled) {
            const isScanning = Boolean(watcherState.is_checking);
            statusDot.className = 'watcher-pulse-dot' + (isScanning ? ' scanning' : '');
            statusTxt.textContent = isScanning ? 'Scanning...' : 'Active';
            countTxt.textContent = `Monitoring ${allSeries.length} anime`;
          } else {
            statusDot.className = 'watcher-pulse-dot disabled';
            statusTxt.textContent = 'Paused';
            countTxt.textContent = 'Auto-downloader paused';
          }
        }
      }
    }
  }
}

async function monitorUrlInput() {
  const urlEl = document.getElementById('url');
  const btn = document.getElementById('url-autodl-btn');
  if (!urlEl) return;
  const raw = urlEl.value.trim();
  if (!raw) {
    toast('Please enter a Crunchyroll series URL or ID first', 'err');
    return;
  }
  const urls = raw.split(/[\r\n,]+/).map(u => u.trim()).filter(Boolean);
  if (!urls.length) return;

  if (urls.length === 1 && btn) {
    const target = urls[0];
    const isMon = monitoredSeriesMap.has(target);
    openAutoDlModePopover(btn, {
      id: target,
      title: target,
      url: target.startsWith('http') ? target : `https://www.crunchyroll.com/series/${target}`,
      isMonitored: isMon,
    });
    return;
  }

  toast(`Adding ${urls.length} show(s) to auto-downloader...`, 'info');
  let successCount = 0;
  for (const target of urls) {
    try {
      const res = await api('/api/watcher/monitor', {
        series_id: target,
        url: target,
        mode: 'latest_only',
      });
      if (res && res.success) {
        monitoredSeriesMap.set(res.series.id, res.series);
        successCount++;
      }
    } catch (_) {}
  }

  if (successCount > 0) {
    toast(`Successfully added ${successCount} show(s) to Auto-DL!`, 'ok');
    syncAllMonitoredCards();
    const sRes = await api('/api/watcher/status');
    if (sRes && sRes.success) updateWatcherState(sRes);
  } else {
    toast('Failed to add series to Auto-DL. Verify URL or ID.', 'err');
  }
}

function setAutoDlFilterMode(mode) {
  autoDlFilterMode = mode || 'all';
  document.querySelectorAll('.autodl-filter-chips .catalog-filter-chip').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.filter === autoDlFilterMode);
  });
  renderAutoDlTab();
}

function toggleAutoDlSearch(forceOpen) {
  const wrapper = document.getElementById('autodl-search-wrapper');
  const iconBtn = document.getElementById('btn-toggle-autodl-search');
  const headerBtn = document.getElementById('btn-toggle-add-anime');
  if (!wrapper) return;
  const isCurrentlyOpen = wrapper.style.display !== 'none';
  const show = forceOpen !== undefined ? Boolean(forceOpen) : !isCurrentlyOpen;
  wrapper.style.display = show ? 'flex' : 'none';
  if (iconBtn) iconBtn.classList.toggle('active', show);
  if (headerBtn) headerBtn.classList.toggle('active', show);
  if (show) {
    const input = document.getElementById('autodl-search-input');
    if (input) {
      input.focus();
      input.select();
    }
  } else {
    closeAutoDlSearchDropdown();
  }
}

// Backwards-compatible alias for any other callers
function toggleAutoDlAddSection(forceOpen) {
  toggleAutoDlSearch(forceOpen);
}

function isCrunchyrollUrlOrId(val) {
  const str = (val || '').trim();
  if (!str) return false;
  if (/^https?:\/\//i.test(str) || str.includes('crunchyroll.com/')) return true;
  if (str.startsWith('series/') || str.startsWith('watch/')) return true;
  if (/^[A-Za-z0-9]{8,12}$/.test(str) && !/[a-z]{4,}/.test(str)) return true;
  return false;
}

let autoDlSearchDebounceTimer = null;
let lastAutoDlSearchQuery = '';

function onAutoDlSearchInput(val) {
  const query = (val || '').trim();
  const clearBtn = document.getElementById('autodl-search-clear');
  const addBtn = document.getElementById('btn-autodl-search-add');
  const btnText = document.getElementById('btn-autodl-search-text');
  if (clearBtn) clearBtn.style.display = query ? 'inline-flex' : 'none';

  if (isCrunchyrollUrlOrId(query)) {
    if (addBtn) addBtn.style.display = 'inline-flex';
    if (btnText) btnText.textContent = 'monitor anime';
    closeAutoDlSearchDropdown();
    return;
  } else {
    if (addBtn) addBtn.style.display = 'none';
  }

  if (!query) {
    closeAutoDlSearchDropdown();
    return;
  }

  if (query.length >= 2) {
    if (autoDlSearchDebounceTimer) clearTimeout(autoDlSearchDebounceTimer);
    autoDlSearchDebounceTimer = setTimeout(() => {
      fetchAutoDlCrunchyrollSearchResults(query);
    }, 300);
  } else {
    closeAutoDlSearchDropdown();
  }
}

function onAutoDlSearchKeydown(e) {
  if (e.key === 'Enter') {
    e.preventDefault();
    submitAutoDlSearch();
  } else if (e.key === 'Escape') {
    closeAutoDlSearchDropdown();
    toggleAutoDlSearch(false);
  }
}

function clearAutoDlSearch() {
  const inputEl = document.getElementById('autodl-search-input');
  const clearBtn = document.getElementById('autodl-search-clear');
  const addBtn = document.getElementById('btn-autodl-search-add');
  if (inputEl) inputEl.value = '';
  if (clearBtn) clearBtn.style.display = 'none';
  if (addBtn) addBtn.style.display = 'none';
  closeAutoDlSearchDropdown();
}

function closeAutoDlSearchDropdown() {
  const dropdown = document.getElementById('autodl-search-dropdown');
  if (dropdown) dropdown.style.display = 'none';
}

async function fetchAutoDlCrunchyrollSearchResults(query) {
  const dropdown = document.getElementById('autodl-search-dropdown');
  if (!dropdown) return;

  lastAutoDlSearchQuery = query;
  dropdown.style.display = 'flex';
  dropdown.innerHTML = `
    <div class="autodl-dropdown-loading">
      <div class="spinner"></div>
      <span>Searching Crunchyroll for "${escapeHtml(query)}"...</span>
    </div>
  `;

  try {
    const res = await api('/api/search', { q: query, n: 8 });
    const currentInp = document.getElementById('autodl-search-input')?.value.trim();
    if (currentInp !== query) return;

    const items = res?.results || [];
    if (!items.length) {
      dropdown.innerHTML = `
        <div class="autodl-dropdown-empty">
          No anime found on Crunchyroll matching "${escapeHtml(query)}"
        </div>
      `;
      return;
    }

    dropdown.innerHTML = items.map(item => {
      const id = item.id;
      const title = item.title || id;
      const poster = item.poster || '';
      const isMon = monitoredSeriesMap.has(id);
      const isMovie = item.type === 'movie_listing';
      const typeLabel = isMovie ? 'MOVIE' : 'SERIES';
      const eps = item.episode_count ? `${item.episode_count} ep` : '';
      const safeId = escapeHtml(id);
      const safeTitle = escapeHtml(title);
      const safePoster = escapeHtml(poster);

      return `
        <div class="autodl-dropdown-item" data-id="${safeId}" data-title="${safeTitle}" data-poster="${safePoster}">
          <div class="autodl-dropdown-item-left">
            ${poster
              ? `<img class="autodl-dropdown-poster" src="${safePoster}" alt="" onerror="this.style.opacity='0.2'">`
              : `<div class="autodl-dropdown-poster" style="display:flex;align-items:center;justify-content:center;background:#1e1e1e;color:#555;"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2"/></svg></div>`
            }
            <div class="autodl-dropdown-info">
              <span class="autodl-dropdown-title" title="${safeTitle}">${safeTitle}</span>
              <div class="autodl-dropdown-badges">
                <span class="res-badge ${isMovie ? 'res-badge-movie' : ''}" style="font-size:0.6rem;padding:1px 4px;">${typeLabel}</span>
                ${eps ? `<span class="res-badge" style="font-size:0.6rem;padding:1px 4px;">${eps}</span>` : ''}
                ${item.year ? `<span class="res-badge" style="font-size:0.6rem;padding:1px 4px;">${item.year}</span>` : ''}
              </div>
            </div>
          </div>
          <button type="button" class="btn-s ${isMon ? 'btn-monitor-active' : 'btn-monitor'} autodl-dropdown-add-btn" title="${isMon ? 'Already monitored. Click to toggle mode or manage.' : 'Add to auto-downloader'}">
            ${isMon ? 'auto-dl ✓' : '+ auto-dl'}
          </button>
        </div>
      `;
    }).join('');

    dropdown.onclick = (e) => {
      const itemEl = e.target.closest('.autodl-dropdown-item');
      if (itemEl && itemEl.dataset.id) {
        selectAnimeFromAutoDlSearch(itemEl.dataset.id, itemEl.dataset.title, itemEl.dataset.poster);
      }
    };
  } catch (err) {
    dropdown.innerHTML = `
      <div class="autodl-dropdown-empty" style="color:#ff6666;">
        Search error: ${escapeHtml(err.message)}
      </div>
    `;
  }
}

async function selectAnimeFromAutoDlSearch(id, title, poster) {
  if (!id) return;
  const modeEl = document.getElementById('autodl-search-mode');
  const mode = modeEl ? modeEl.value : 'latest_only';

  closeAutoDlSearchDropdown();
  clearAutoDlSearch();

  toast(`Adding "${title}" to Auto-Downloader...`, 'info');

  try {
    const res = await api('/api/watcher/monitor', {
      series_id: id,
      title: title,
      url: `https://www.crunchyroll.com/series/${id}`,
      poster: poster,
      mode: mode,
    });
    if (res && res.success) {
      monitoredSeriesMap.set(res.series.id, res.series);
      const modeLabel = mode === 'all_missing' ? 'All Missing' : 'Future Only';
      toast(`Added "${res.series.title || title}" to Auto-DL! (${modeLabel})`, 'ok');
      syncAllMonitoredCards();
      if (mode === 'all_missing') {
        checkSingleMonitoredSeries(id);
      }
      const sRes = await api('/api/watcher/status');
      if (sRes && sRes.success) updateWatcherState(sRes);
    } else {
      toast(res?.error || 'Failed to add series to auto-downloader', 'err');
    }
  } catch (err) {
    toast('Error adding series: ' + err.message, 'err');
  }
}

async function submitAutoDlSearch() {
  const inputEl = document.getElementById('autodl-search-input');
  const modeEl = document.getElementById('autodl-search-mode');
  const btn = document.getElementById('btn-autodl-search-add');
  if (!inputEl) return;
  const raw = inputEl.value.trim();
  if (!raw) {
    toast('Search for an anime by title or paste a URL / ID', 'err');
    inputEl.focus();
    return;
  }
  const mode = modeEl ? modeEl.value : 'latest_only';

  if (isCrunchyrollUrlOrId(raw)) {
    closeAutoDlSearchDropdown();
    if (btn) {
      btn.disabled = true;
      btn.classList.add('loading');
    }
    toast('Adding series to Auto-Downloader...', 'info');

    try {
      const res = await api('/api/watcher/monitor', {
        series_id: raw,
        url: raw.startsWith('http') ? raw : `https://www.crunchyroll.com/series/${raw}`,
        mode: mode,
      });
      if (res && res.success) {
        monitoredSeriesMap.set(res.series.id, res.series);
        clearAutoDlSearch();
        const modeLabel = mode === 'all_missing' ? 'All Missing' : 'Future Only';
        toast(`Added "${res.series.title || res.series.id}" to Auto-DL! (${modeLabel})`, 'ok');
        syncAllMonitoredCards();
        if (mode === 'all_missing') {
          checkSingleMonitoredSeries(res.series.id);
        }
        const sRes = await api('/api/watcher/status');
        if (sRes && sRes.success) updateWatcherState(sRes);
      } else {
        toast(res?.error || 'Failed to add series to auto-downloader', 'err');
      }
    } catch (err) {
      toast('Error adding series: ' + err.message, 'err');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.classList.remove('loading');
      }
    }
    return;
  }

  // If title search, trigger search immediately
  if (autoDlSearchDebounceTimer) clearTimeout(autoDlSearchDebounceTimer);
  await fetchAutoDlCrunchyrollSearchResults(raw);
}

document.addEventListener('click', (e) => {
  if (!document.contains(e.target)) return;
  if (!e.target.closest('#autodl-search-wrapper') && !e.target.closest('#btn-toggle-autodl-search')) {
    closeAutoDlSearchDropdown();
  }
});

async function changeAutoDlSeriesMode(sid, newMode) {
  if (!sid) return;
  const cur = monitoredSeriesMap.get(sid);
  if (!cur) return;
  const modeVal = newMode === 'all_missing' ? 'all_missing' : 'latest_only';
  const modeLabel = modeVal === 'all_missing' ? 'All Missing' : 'Future Only';
  toast(`Updating "${cur.title || sid}" to ${modeLabel}...`, 'info');
  try {
    const res = await api('/api/watcher/monitor', {
      series_id: sid,
      mode: modeVal,
      title: cur.title,
      url: cur.url,
      poster: cur.poster,
    });
    if (res && res.success) {
      monitoredSeriesMap.set(sid, res.series);
      toast(`"${cur.title || sid}" mode set to ${modeLabel}!`, 'ok');
      syncAllMonitoredCards();
      if (modeVal === 'all_missing') {
        checkSingleMonitoredSeries(sid);
      }
    } else {
      toast(res?.error || 'Failed to change mode', 'err');
    }
  } catch (err) {
    toast('Error changing mode: ' + err.message, 'err');
  }
}

async function toggleAutoDlSeriesMode(sid) {
  if (!sid) return;
  const cur = monitoredSeriesMap.get(sid);
  if (!cur) return;
  const newMode = cur.mode === 'all_missing' ? 'latest_only' : 'all_missing';
  await changeAutoDlSeriesMode(sid, newMode);
}

async function toggleMonitoredSeriesStatus(sid) {
  if (!sid) return;
  try {
    const res = await api('/api/watcher/toggle', { series_id: sid });
    if (res && res.success) {
      const cur = monitoredSeriesMap.get(sid);
      if (cur) {
        cur.status = res.status;
        monitoredSeriesMap.set(sid, cur);
      }
      toast(`Series is now ${res.status}`, 'ok');
      syncAllMonitoredCards();
    } else {
      toast(res?.error || 'Failed to toggle status', 'err');
    }
  } catch (err) {
    toast('Error toggling series: ' + err.message, 'err');
  }
}

function renderAutoDlTab() {
  const gridEl = document.getElementById('autodl-series-grid');
  const emptyEl = document.getElementById('autodl-empty-view');
  const emptyTitle = document.getElementById('autodl-empty-title');
  const emptyDesc = document.getElementById('autodl-empty-desc');
  const statusDot = document.getElementById('autodl-page-status-dot');
  const statusTxt = document.getElementById('autodl-page-status-text');
  const countTxt = document.getElementById('autodl-page-count-text');

  if (!gridEl) return;

  // Protect active user interaction with select dropdowns
  if (document.activeElement && (document.activeElement.tagName === 'SELECT' || document.activeElement.classList.contains('autodl-card-mode-select'))) {
    return;
  }

  const allSeries = Array.from(monitoredSeriesMap.values());
  const count = allSeries.length;

  if (statusDot && statusTxt && countTxt) {
    if (watcherState.enabled) {
      statusDot.className = 'watcher-pulse-dot' + (watcherState.is_checking ? ' scanning' : '');
      statusTxt.textContent = watcherState.is_checking ? 'Scanning...' : 'Active';
      countTxt.textContent = `Monitoring ${count} anime`;
    } else {
      statusDot.className = 'watcher-pulse-dot disabled';
      statusTxt.textContent = 'Paused';
      countTxt.textContent = 'Auto-downloader paused';
    }
  }

  // Filter series by status / mode chip
  let filtered = allSeries;
  if (autoDlFilterMode === 'active') {
    filtered = filtered.filter(s => (s.status || 'active') === 'active');
  } else if (autoDlFilterMode === 'paused') {
    filtered = filtered.filter(s => s.status === 'paused');
  } else if (autoDlFilterMode === 'latest_only') {
    filtered = filtered.filter(s => (s.mode || 'latest_only') === 'latest_only');
  } else if (autoDlFilterMode === 'all_missing') {
    filtered = filtered.filter(s => s.mode === 'all_missing');
  }

  if (!filtered.length) {
    gridEl.innerHTML = '';
    if (emptyEl) {
      emptyEl.style.display = 'block';
      if (count > 0 && autoDlFilterMode !== 'all') {
        if (emptyTitle) emptyTitle.textContent = `No ${autoDlFilterMode} anime found`;
        if (emptyDesc) emptyDesc.textContent = 'Click "all" to view all your monitored anime.';
      } else {
        if (emptyTitle) emptyTitle.textContent = 'No anime monitored yet';
        if (emptyDesc) emptyDesc.textContent = 'Click the search icon above or "+ add anime" to search Crunchyroll or monitor a series.';
      }
    }
    return;
  }

  if (emptyEl) emptyEl.style.display = 'none';

  gridEl.innerHTML = filtered.map(s => {
    const sid = s.id || '';
    const title = s.title || sid;
    const url = s.url || `https://www.crunchyroll.com/series/${sid}`;
    const poster = s.poster || '';
    const isAllMissing = s.mode === 'all_missing';
    const isPaused = s.status === 'paused';
    const lastCheck = s.last_checked ? `Checked ${formatTimeAgo(s.last_checked)}` : 'Not checked yet';
    const knownCount = Array.isArray(s.known_episodes) ? s.known_episodes.length : 0;
    const dlCount = Array.isArray(s.downloaded_episodes) ? s.downloaded_episodes.length : 0;
    const lastEp = s.last_episode_name ? `Last: ${escapeHtml(s.last_episode_name)}` : '';

    return `
      <div class="autodl-card-item ${isPaused ? 'paused' : ''}" data-id="${escapeHtml(sid)}">
        ${poster
          ? `<img class="autodl-card-poster" src="${escapeHtml(poster)}" alt="${escapeHtml(title)}" loading="lazy" onerror="this.style.opacity='0.2'">`
          : `<div class="autodl-card-poster" style="display:flex;align-items:center;justify-content:center;color:#444;"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2"/></svg></div>`
        }
        <div class="autodl-card-info">
          <div class="autodl-card-top">
            <div class="autodl-card-header-line">
              <a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer" class="autodl-card-title" title="${escapeHtml(title)}">${escapeHtml(title)}</a>
              ${isPaused ? '<span class="res-badge res-badge-paused" style="font-size:0.58rem;padding:1px 5px;flex-shrink:0;">PAUSED</span>' : ''}
            </div>
            <div class="autodl-card-meta">
              <span${lastEp ? ` title="${lastEp}"` : ''}>${lastCheck} • ${dlCount}/${knownCount} eps${lastEp ? ` • ${lastEp}` : ''}</span>
            </div>
          </div>
          <div class="autodl-card-actions">
            <div class="autodl-pill-select-wrap ${isAllMissing ? 'pill-all' : 'pill-future'}" title="Monitoring mode: click to change">
              <select class="autodl-card-mode-select autodl-mode-pill-select" onchange="changeAutoDlSeriesMode('${escapeHtml(sid)}', this.value)" title="Choose monitoring mode: Future Only or All Missing">
                <option value="latest_only" ${!isAllMissing ? 'selected' : ''}>FUTURE ONLY</option>
                <option value="all_missing" ${isAllMissing ? 'selected' : ''}>ALL MISSING</option>
              </select>
              <svg class="autodl-pill-arrow" width="8" height="5" viewBox="0 0 10 6" fill="none"><path d="M1 1L5 5L9 1" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
            </div>
            <button type="button" class="btn-icon btn-autodl-card-settings" onclick="openSeriesSettings('${escapeHtml(sid)}')" title="Settings for this anime (audio, subtitles, quality, folder)">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82.33l.06.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>
            </button>
            <div class="autodl-card-btn-group">
              <button type="button" class="btn-icon btn-autodl-check" onclick="checkSingleMonitoredSeries('${escapeHtml(sid)}')" title="Check for new episodes now">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"></polyline><polyline points="1 20 1 14 7 14"></polyline><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path></svg>
              </button>
              <button type="button" class="btn-icon btn-autodl-pause" onclick="toggleMonitoredSeriesStatus('${escapeHtml(sid)}')" title="${isPaused ? 'Resume monitoring' : 'Pause monitoring'}">
                ${isPaused
                  ? '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>'
                  : '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="4" width="4" height="16"></rect><rect x="14" y="4" width="4" height="16"></rect></svg>'
                }
              </button>
              <button type="button" class="btn-icon btn-autodl-stop" onclick="removeMonitoredSeries('${escapeHtml(sid)}')" title="Stop monitoring this anime">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
              </button>
            </div>
          </div>
        </div>
      </div>
    `;
  }).join('');
}

// Background heartbeat polling (every 10 seconds when no active download poll is running)
setInterval(async () => {
  if (!pollTimer) {
    try {
      const state = await api('/api/state');
      if (state) {
        if (state.watcher) updateWatcherState(state.watcher);
        if (state.download && state.download.status === 'running') startPolling();
      }
    } catch (_) {}
  }
}, 10000);
