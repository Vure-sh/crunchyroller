// crunchyroller - web dashboard logic

let pollTimer = null;
let ddVideo = null;
let ddAudioQual = null;
let ddAudio = null;
let ddSubs = null;
let ddBitrate = null;
let ddAudioFormat = null;

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
    if (!this.multi) {
      this.value = val || (this.options[0] ? this.options[0].val : '');
    } else {
      this.value = val || 'all';
    }
    if (this.hiddenInput) this.hiddenInput.value = this.value;
    this.render();
    if (triggerChange && this.onChange) {
      this.onChange(this.value);
    }
  }

  selectSingle(val) {
    this.setValue(val);
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

  render() {
    if (!this.multi) {
      const found = this.options.find(o => o.val.toLowerCase() === (this.value || '').toLowerCase());
      this.btnText.textContent = found ? found.label : (this.value || 'Select');

      this.menu.innerHTML = '';
      this.options.forEach(opt => {
        const isChecked = opt.val.toLowerCase() === (this.value || '').toLowerCase();
        const row = document.createElement('div');
        row.className = 'select-opt' + (isChecked ? ' selected' : '');
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
          e.stopPropagation();
          this.selectSingle(opt.val);
        });

        this.menu.appendChild(row);
      });
      return;
    }

    const selected = this.getSelectedList();
    const isAll = selected.includes('all');

    if (isAll) {
      this.btnText.textContent = 'All available';
    } else {
      const labels = selected.map(code => {
        const found = this.options.find(o => o.val.toLowerCase() === code.toLowerCase());
        return found ? found.label : code;
      });
      if (labels.length === 1) {
        this.btnText.textContent = labels[0];
      } else if (labels.length === 2) {
        this.btnText.textContent = `${labels[0]}, ${labels[1]}`;
      } else {
        this.btnText.textContent = `${labels[0]}, ${labels[1]} +${labels.length - 2}`;
      }
    }

    this.menu.innerHTML = '';
    this.options.forEach(opt => {
      const isChecked = isAll ? (opt.val === 'all') : selected.some(c => c.toLowerCase() === opt.val.toLowerCase());
      const row = document.createElement('div');
      row.className = 'select-opt' + (isChecked ? ' selected' : '') + (opt.val === 'all' ? ' opt-all' : '');
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
        e.stopPropagation();
        this.toggleItem(opt.val);
      });

      this.menu.appendChild(row);
    });
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

  initCustomContextMenu();
  checkForUpdates(false);
});

// Prompt banner for starring the repo (disabled)
function initStarBanner() {}
function dismissStarBanner() {}

// sync UI with backend state
function applyState(state) {
  const badge = document.getElementById('badge');
  const badgeTxt = document.getElementById('badge-txt');

  if (state.authenticated) {
    badge.classList.add('on');
    if (state.auth_type === 'android_tv') {
      badgeTxt.textContent = 'connected (login)';
    } else if (state.auth_type === 'token') {
      badgeTxt.textContent = 'connected (token)';
    } else {
      badgeTxt.textContent = 'connected';
    }
  } else {
    badge.classList.remove('on');
    badgeTxt.textContent = 'offline';
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
    document.getElementById('badge-txt').textContent = 'connected (token)';
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
      document.getElementById('badge-txt').textContent = 'connected (login)';
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
        statusIco.textContent = item.status === 'completed' ? '✓' : (item.status === 'canceled' ? '✕' : '!');

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

// fetch URL metadata & show episode tree
async function fetchUrl() {
  const url = document.getElementById('url').value.trim();
  if (!url) {
    toast('paste a crunchyroll url', 'err');
    return;
  }

  const btn = document.getElementById('fetch-btn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spin"></span>';

  const res = await api('/api/fetch', { url });
  btn.disabled = false;
  btn.textContent = 'fetch';

  if (!res.success) {
    toast(res.error || 'fetch failed', 'err');
    return;
  }

  renderEpisodeTree(res);
  toast(res.title, 'ok');
}

// toggle expand/collapse all seasons
function toggleAllSeasons() {
  const blocks = document.querySelectorAll('.sn-block');
  const btn = document.getElementById('toggle-seasons-btn');
  if (!blocks.length) return;
  const anyCollapsed = [...blocks].some(b => b.classList.contains('collapsed'));
  blocks.forEach(b => b.classList.toggle('collapsed', !anyCollapsed));
  if (btn) btn.textContent = anyCollapsed ? 'collapse all' : 'expand all';
}

// render season and episode checkboxes
function renderEpisodeTree(data) {
  document.getElementById('ser-title').textContent = data.title;
  const toggleBtn = document.getElementById('toggle-seasons-btn');
  if (toggleBtn) toggleBtn.textContent = 'expand all';

  const list = document.getElementById('sn-list');
  list.innerHTML = '';

  data.seasons.forEach((season, sIdx) => {
    const block = document.createElement('div');
    block.className = 'sn-block collapsed';

    // season header
    const head = document.createElement('div');
    head.className = 'sn-head';

    const cbWrap = document.createElement('div');
    cbWrap.className = 'sn-cb-wrap';

    const seasonCb = document.createElement('input');
    seasonCb.type = 'checkbox';
    seasonCb.className = 'cb-custom sn-cb';
    seasonCb.checked = true;
    seasonCb.id = 's' + sIdx;

    cbWrap.appendChild(seasonCb);

    const titleWrap = document.createElement('div');
    titleWrap.className = 'sn-title-wrap';

    const label = document.createElement('span');
    label.className = 'sn-title';

    let snName = (season.title || '').trim();
    if (data.title && snName.toLowerCase().startsWith(data.title.toLowerCase())) {
      snName = snName.slice(data.title.length).replace(/^[\s:–—-]+/, '').trim();
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
    count.textContent = season.episodes.length + ' ep';

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
      updateTotalCount();
    });

    head.addEventListener('click', () => {
      block.classList.toggle('collapsed');
      const blocks = document.querySelectorAll('.sn-block');
      const tBtn = document.getElementById('toggle-seasons-btn');
      if (tBtn && blocks.length) {
        const anyCollapsed = [...blocks].some(b => b.classList.contains('collapsed'));
        tBtn.textContent = anyCollapsed ? 'expand all' : 'collapse all';
      }
    });

    season.episodes.forEach(ep => {
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
      cb.dataset.series = ep.series_title || '';
      cb.dataset.seasonTitle = ep.season_title || season.title || '';
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
        updateTotalCount();
      });

      row.append(cb, num, name);
      epList.appendChild(row);
    });

    block.append(head, epList);
    list.appendChild(block);
    updateSeasonState(block);
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

// select / deselect all episodes
function pickAll(val) {
  document.querySelectorAll('.epc').forEach(cb => {
    cb.checked = val;
    const row = cb.closest('.ep-row');
    if (row) row.classList.toggle('selected', val);
  });
  document.querySelectorAll('.sn-block').forEach(block => updateSeasonState(block));
  updateTotalCount();
}

// start batch download task
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

  const animeTitle = (document.getElementById('ser-title')?.textContent || '').trim() ||
                     (selected.find(s => s.series_title)?.series_title) || 'Anime';

  const vqVal = ddVideo ? ddVideo.value : (document.getElementById('vq')?.value || '1080p');
  const aqVal = ddAudioQual ? ddAudioQual.value : (document.getElementById('aq')?.value || '192k');
  const audioVal = ddAudio ? ddAudio.value : (document.getElementById('al')?.value || 'ja-JP');
  const subsVal = ddSubs ? ddSubs.value : (document.getElementById('sl')?.value || 'en-US');
  const dlDirVal = (document.getElementById('download-dir') || {}).value || '';
  const workersVal = parseInt(document.getElementById('workers-slider')?.value || '16', 10);
  const resumeVal = Boolean(document.getElementById('enable-resume')?.checked);
  const bitrateVal = ddBitrate ? ddBitrate.value : (document.getElementById('bitrate-mode')?.value || 'highest');

  const res = await api('/api/download', {
    items: selected,
    task_title: animeTitle,
    series_title: animeTitle,
    video_quality: vqVal,
    audio_quality: aqVal,
    audio_lang: audioVal,
    subs_lang: subsVal,
    force_download: (document.getElementById('force-download') || {}).checked || false,
    download_dir: dlDirVal.trim() || 'anime',
    workers: workersVal,
    enable_resume: resumeVal,
    bitrate_mode: bitrateVal,
  });

  if (!res.success) {
    toast(res.error || 'download failed to start', 'err');
    return;
  }

  toast(res.message || (`${selected.length} episode(s) added to task: ${animeTitle}`));
  document.getElementById('dl-panel').style.display = 'block';
  startPolling();
}

function startPolling() {
  if (pollTimer) return;
  pollTimer = setInterval(async () => {
    const state = await api('/api/state');
    if (state && state.download) {
      updateProgressPanel(state.download);
      const isRunning = state.download.status === 'running' || state.download.status === 'paused';
      const hasQueue = state.download.queue && state.download.queue.length > 0;
      const hasActiveTasks = state.download.tasks && state.download.tasks.some(t => t.status === 'running' || t.status === 'queued');
      if (!isRunning && !hasQueue && !hasActiveTasks) {
        clearInterval(pollTimer);
        pollTimer = null;
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
  if (res && res.success) {
    toast('Queue cleared (' + (res.cleared || 0) + ' items)');
    const state = await api('/api/state');
    if (state && state.download) {
      updateProgressPanel(state.download);
    }
  } else {
    toast(res?.error || 'failed to clear queue', 'err');
  }
}

async function clearFinishedTasks() {
  const res = await api('/api/tasks/clear-finished', {});
  if (res && res.success) {
    if (res.cleared > 0) {
      toast('Cleared ' + res.cleared + ' finished task(s)');
    } else {
      toast('No finished tasks to clear');
    }
    const state = await api('/api/state');
    if (state && state.download) {
      updateProgressPanel(state.download);
    }
  } else {
    toast(res?.error || 'failed to clear tasks', 'err');
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
  if (res && res.success) {
    toast(isFinished ? 'Task dismissed' : 'Task canceled');
    const state = await api('/api/state');
    if (state && state.download) {
      updateProgressPanel(state.download);
    }
  } else {
    toast(res?.error || 'Failed to update task', 'err');
  }
}

function updateProgressPanel(dl) {
  if (!dl) return;
  const hasTasks = dl.tasks && dl.tasks.length > 0;
  const hasQueue = dl.queue && dl.queue.length > 0;
  const isRunning = dl.status === 'running' || dl.status === 'paused';

  if (!isRunning && !hasTasks && !hasQueue && dl.status === 'idle') {
    return;
  }
  document.getElementById('dl-panel').style.display = 'block';

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
    if (dl.status === 'completed') {
      openFolderBtn.style.display = 'inline-block';
    } else {
      openFolderBtn.style.display = 'none';
    }
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
  } else if (dl.status === 'canceled') {
    pill.className = 'pill pill-err';
    pill.innerHTML = '\u2717 canceled';
  } else {
    pill.className = 'pill pill-err';
    pill.innerHTML = '\u2717 ' + dl.status;
  }

  const epIdx   = (dl.ep_idx  || 0) + 1;
  const epTotal = dl.ep_total || 1;
  document.getElementById('dl-ep-counter').textContent =
    dl.status === 'completed' ? `${epTotal} / ${epTotal}` : `${epIdx} / ${epTotal}`;

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

    if (tasks.length > 0 || queue.length > 0) {
      qPanel.style.display = 'block';
      if (qBadge) {
        const queuedCount = dl.queued_count !== undefined ? dl.queued_count : queue.length;
        qBadge.textContent = String(queuedCount);
      }

      if (tasks.length > 0) {
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
      } else {
        // Fallback flat queue items rendering
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
      }
    } else {
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
  } else if (ep.status === 'canceled') {
    const statusPill = document.createElement('span');
    statusPill.className = 'task-ep-status-pill status-canceled';
    statusPill.textContent = 'canceled';
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
