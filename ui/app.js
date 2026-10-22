/* The launch credential stays in this closure and is never persisted. */
(() => {
  'use strict';

  let bootstrapStarted = false;

  class LocalRequestError extends Error {
    constructor(code, safeMessage) {
      super(safeMessage);
      this.code = code;
      this.safeMessage = safeMessage;
    }
  }

  function createTransport(credential) {
    const sessionHeaders = Object.freeze({'X-Athena-Session': credential});

    async function request(path, method, body, extraHeaders) {
      const headers = new Headers(sessionHeaders);
      for (const [name, value] of Object.entries(extraHeaders || {})) headers.set(name, value);
      const options = {
        method,
        headers,
        cache: 'no-store',
        redirect: 'error',
        credentials: 'omit',
      };
      if (body !== undefined) {
        headers.set('Content-Type', 'application/json');
        options.body = JSON.stringify(body);
      }

      let response;
      try {
        response = await fetch(path, options);
      } catch (_) {
        throw new LocalRequestError('LOCAL_REQUEST_UNAVAILABLE',
          'The local session could not complete this request.');
      }

      let payload = null;
      try {
        payload = await response.json();
      } catch (_) {
        payload = null;
      }
      if (!response.ok) {
        const code = payload && typeof payload.code === 'string'
          ? payload.code : 'LOCAL_REQUEST_FAILED';
        const message = payload && typeof payload.safe_message === 'string'
          ? payload.safe_message : 'The local request could not be completed.';
        throw new LocalRequestError(code, message);
      }
      if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
        throw new LocalRequestError('LOCAL_RESPONSE_INVALID',
          'The local application returned an unreadable response.');
      }
      return payload;
    }

    return Object.freeze({
      get: (path, extraHeaders) => request(path, 'GET', undefined, extraHeaders),
      post: (path, body) => request(path, 'POST', body),
    });
  }

  function createState(capabilities) {
    const prefersLight = window.matchMedia
      && window.matchMedia('(prefers-color-scheme: light)').matches;
    return {
      capabilities,
      activeView: 'overview',
      activeProfile: null,
      dates: [],
      preview: null,
      previewing: false,
      formRevision: 0,
      latestRun: null,
      theme: prefersLight ? 'light' : 'dark',
    };
  }

  function element(tag, className, text) {
    const item = document.createElement(tag);
    if (className) item.className = className;
    if (text !== undefined) item.textContent = text;
    return item;
  }

  function capability(state, id) {
    const rows = state.capabilities && Array.isArray(state.capabilities.capabilities)
      ? state.capabilities.capabilities : [];
    return rows.find((row) => row && row.capability_id === id) || null;
  }

  function setNotice(message, kind) {
    const notice = document.getElementById('workspace-notice');
    notice.textContent = message;
    notice.className = 'workspace-notice' + (kind ? ' is-' + kind : '');
    notice.hidden = !message;
  }

  function renderCapabilities(state) {
    const list = document.getElementById('capability-list');
    list.replaceChildren();
    const rows = state.capabilities && Array.isArray(state.capabilities.capabilities)
      ? state.capabilities.capabilities : [];
    if (!rows.length) {
      list.append(element('li', 'capability-empty', 'Capability evidence is unavailable.'));
      return;
    }
    for (const row of rows) {
      if (!row || typeof row.capability_id !== 'string') continue;
      const item = element('li', 'capability-row');
      const copy = element('div', 'capability-copy');
      copy.append(element('strong', 'capability-name', row.capability_id.replaceAll('_', ' ')));
      copy.append(element('span', 'capability-reason',
        typeof row.reason === 'string' ? row.reason : 'Reason not available.'));
      const stateLabel = typeof row.state === 'string' ? row.state : 'unavailable_unproven';
      item.append(copy, element('span', 'state-pill state-' + stateLabel, stateLabel.replaceAll('_', ' ')));
      list.append(item);
    }
  }

  function renderRelease(state) {
    const list = document.getElementById('release-identity');
    list.replaceChildren();
    const release = state.capabilities && state.capabilities.release;
    if (!release || typeof release !== 'object') {
      const row = element('div', 'identity-row');
      row.append(element('dt', '', 'Identity'), element('dd', 'identity-empty', 'Release identity is unavailable.'));
      list.append(row);
      return;
    }
    const fields = [
      ['Mode', release.source_mode], ['Release', release.release_id],
      ['Build', release.build_id], ['Platform', release.platform],
      ['Architecture', release.architecture], ['Identity reference', release.identity_ref],
    ];
    for (const [label, value] of fields) {
      if (value === undefined || value === null || value === '') continue;
      const row = element('div', 'identity-row');
      row.append(element('dt', '', label), element('dd', '', String(value)));
      list.append(row);
    }
  }

  function setPage(state, page) {
    state.activeView = page;
    for (const section of document.querySelectorAll('[data-screen]')) {
      section.hidden = section.dataset.screen !== page;
    }
    for (const button of document.querySelectorAll('.nav-item[data-view]')) {
      const active = button.dataset.view === page;
      button.classList.toggle('is-active', active);
      if (active) button.setAttribute('aria-current', 'page');
      else button.removeAttribute('aria-current');
    }
    document.getElementById('page-title').textContent = page === 'build' ? 'Build' : 'Overview';
    setNotice('', '');
  }

  function lagosDate(offsetDays) {
    try {
      const parts = new Intl.DateTimeFormat('en', {
        timeZone: 'Africa/Lagos', year: 'numeric', month: '2-digit', day: '2-digit',
      }).formatToParts(new Date());
      const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
      const date = new Date(Date.UTC(Number(values.year), Number(values.month) - 1,
        Number(values.day) + offsetDays));
      return date.toISOString().slice(0, 10);
    } catch (_) {
      return null;
    }
  }

  function renderDates(state) {
    const list = document.getElementById('selected-dates');
    list.replaceChildren();
    for (const value of state.dates) {
      const item = element('li', 'selected-date');
      item.append(element('span', '', value));
      const remove = element('button', 'remove-date', 'Remove');
      remove.type = 'button';
      remove.setAttribute('aria-label', 'Remove date ' + value);
      remove.addEventListener('click', () => {
        state.dates = state.dates.filter((date) => date !== value);
        invalidatePreview(state);
        renderDates(state);
      });
      item.append(remove);
      list.append(item);
    }
    const input = document.getElementById('request-date');
    const add = document.getElementById('add-date');
    add.disabled = state.dates.length >= 7 || !input.value;
    updatePreviewButton(state);
  }

  function updatePreviewButton(state) {
    const button = document.getElementById('preview-button');
    if (!button) return;
    const readiness = document.getElementById('preview-readiness');
    const previewCapability = capability(state, 'run_preview');
    const canPreview = Boolean(previewCapability && previewCapability.state === 'available');
    if (readiness) {
      readiness.textContent = canPreview
        ? 'Local read-only preview is available for this session.'
        : previewCapability && typeof previewCapability.reason === 'string'
          ? previewCapability.reason
          : 'Preview is unavailable because this session has no proven run_preview capability.';
    }
    const value = document.getElementById('target-legs').value;
    const legs = value === '' ? NaN : Number(value);
    const profile = document.getElementById('profile').value;
    const valid = state.dates.length >= 1 && state.dates.length <= 7
      && Number.isInteger(legs) && legs >= 1 && legs <= 50
      && (profile === 'main' || profile === 'shadow');
    button.disabled = !canPreview || !valid || state.previewing;
    document.getElementById('active-profile').textContent = state.activeProfile || 'Not selected';
  }

  function updateStartReason(state) {
    const reason = document.getElementById('start-reason');
    const blockers = state.preview && Array.isArray(state.preview.blockers)
      ? state.preview.blockers : [];
    if (blockers.length) {
      reason.textContent = 'Start is unavailable because this preview contains ' + blockers.length
        + ' typed blocker' + (blockers.length === 1 ? '.' : 's.');
      return;
    }
    if (state.preview) {
      reason.textContent = 'This preview is read only and grants no execution authority. No qualified football-analysis execution is enabled here.';
      return;
    }
    reason.textContent = 'Run execution is not enabled in this preview. A request preview grants no execution authority.';
  }

  function invalidatePreview(state) {
    state.formRevision += 1;
    state.preview = null;
    const report = document.getElementById('preview-report');
    if (report) {
      report.replaceChildren();
      report.hidden = true;
    }
    updateStartReason(state);
  }

  function renderPreview(state, preview) {
    const panel = document.getElementById('preview-report');
    panel.replaceChildren();
    panel.hidden = false;
    panel.append(element('p', 'eyebrow', 'LOCAL PREVIEW'));
    panel.append(element('h3', '', 'Request previewed'));
    panel.append(element('p', 'preview-scope', 'Read-only preview. No provider acquisition, share-code delivery, or wager was performed.'));

    const summary = element('dl', 'preview-summary');
    const rows = [
      ['Dates', Array.isArray(preview.dates) ? preview.dates.join(', ') : 'Not available'],
      ['Maximum selections', preview.target_legs],
      ['Profile', typeof preview.profile === 'string' ? preview.profile.toUpperCase() : 'Not available'],
      ['Source acquisition requested', preview.acquire_sources === true ? 'Yes' : 'No'],
      ['Share-code delivery requested', preview.create_share_code === true ? 'Yes' : 'No'],
      ['Wager', preview.place_wager === false ? 'Not requested' : 'Not available'],
      ['Preview expires', typeof preview.expires_at === 'string' ? preview.expires_at : 'Not available'],
    ];
    for (const [label, value] of rows) {
      const row = element('div', 'preview-summary-row');
      row.append(element('dt', '', label), element('dd', '', String(value)));
      summary.append(row);
    }
    panel.append(summary);

    const operations = element('div', 'operation-summary');
    operations.append(element('p', '', 'Allowed operations: '
      + (Array.isArray(preview.allowed_operations) && preview.allowed_operations.length
        ? preview.allowed_operations.join(', ') : 'None')));
    operations.append(element('p', '', 'Denied operations: '
      + (Array.isArray(preview.denied_operations) && preview.denied_operations.length
        ? preview.denied_operations.join(', ') : 'None')));
    panel.append(operations);

    const blockers = Array.isArray(preview.blockers) ? preview.blockers : [];
    const blockerSection = element('section', 'preview-blockers');
    blockerSection.append(element('h4', '', blockers.length ? 'Preview blockers' : 'No typed blockers returned'));
    if (blockers.length) {
      const list = element('ul', 'blocker-list');
      for (const blocker of blockers) {
        const item = element('li', '');
        const label = [blocker.code, blocker.operation, blocker.capability]
          .filter((value) => typeof value === 'string').join(' · ');
        item.append(element('strong', '', label || 'Blocker'));
        if (typeof blocker.reason === 'string') item.append(element('p', '', blocker.reason));
        list.append(item);
      }
      blockerSection.append(list);
    } else {
      blockerSection.append(element('p', '', 'An empty blocker list does not grant execution authority.'));
    }
    panel.append(blockerSection);

    const details = element('details', 'preview-identities');
    details.append(element('summary', '', 'Preview evidence identities'));
    const ids = element('dl', 'preview-summary');
    for (const [label, key] of [
      ['Request SHA-256', 'request_sha256'],
      ['Execution envelope SHA-256', 'execution_envelope_sha256'],
      ['Preview SHA-256', 'preview_sha256'],
    ]) {
      const row = element('div', 'preview-summary-row');
      row.append(element('dt', '', label));
      row.append(element('dd', '', typeof preview[key] === 'string' ? preview[key] : 'Not available'));
      ids.append(row);
    }
    details.append(ids);
    panel.append(details);
    state.preview = preview;
    updateStartReason(state);
  }

  function displayDate(value) {
    if (typeof value !== 'string') return 'Not available';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return 'Not available';
    return new Intl.DateTimeFormat(undefined, {dateStyle: 'medium', timeStyle: 'short'}).format(date);
  }

  async function loadLatestRun(state, api) {
    const summary = document.getElementById('latest-run-summary');
    const openButton = document.getElementById('open-latest-run');
    const history = capability(state, 'run_history');
    openButton.hidden = true;
    if (!history || history.state !== 'available') {
      summary.textContent = history && typeof history.reason === 'string'
        ? history.reason : 'Retained run history is unavailable in this session.';
      return;
    }
    try {
      const page = await api.get('/api/v1/runs?limit=1');
      const first = Array.isArray(page.items) ? page.items[0] : null;
      if (!first || typeof first.run_id !== 'string') {
        state.latestRun = null;
        summary.textContent = 'No retained runs are available.';
        return;
      }
      state.latestRun = first;
      summary.replaceChildren(
        element('span', 'run-state-pill', typeof first.state === 'string' ? first.state : 'UNKNOWN'),
        element('span', 'run-id', first.run_id),
        element('span', 'run-time', displayDate(first.updated_at || first.created_at)),
      );
      openButton.hidden = false;
    } catch (error) {
      summary.textContent = error instanceof LocalRequestError
        ? error.safeMessage : 'Retained run history could not be read.';
    }
  }

  async function openLatestRun(state, api) {
    if (!state.latestRun || typeof state.latestRun.run_id !== 'string') return;
    const details = document.getElementById('latest-run-details');
    details.hidden = false;
    details.replaceChildren(element('p', '', 'Opening retained run…'));
    try {
      const run = await api.get('/api/v1/runs/' + encodeURIComponent(state.latestRun.run_id));
      details.replaceChildren();
      details.append(element('h4', '', 'Retained run details'));
      const list = element('dl', 'preview-summary');
      const rows = [
        ['Run ID', run.run_id], ['Execution state', run.state],
        ['Last proven stage', run.last_proven_stage], ['Business result', run.business_result],
        ['Delivery state', run.delivery_state], ['Receipt state', run.receipt_state],
        ['Updated', displayDate(run.updated_at)],
      ];
      for (const [label, value] of rows) {
        const row = element('div', 'preview-summary-row');
        row.append(element('dt', '', label), element('dd', '', value === null || value === undefined || value === ''
          ? 'Not available' : String(value)));
        list.append(row);
      }
      details.append(list);
    } catch (error) {
      details.replaceChildren(element('p', 'inline-error', error instanceof LocalRequestError
        ? error.safeMessage : 'Retained run details could not be read.'));
    }
  }

  function bindBuild(state, api) {
    const dateInput = document.getElementById('request-date');
    const today = lagosDate(0);
    const latest = lagosDate(6);
    if (today) dateInput.min = today;
    if (latest) dateInput.max = latest;

    document.getElementById('add-date').addEventListener('click', () => {
      const value = dateInput.value;
      if (!value) return;
      if (state.dates.includes(value)) {
        setNotice('That date is already selected.', 'info');
        return;
      }
      if (state.dates.length >= 7) {
        setNotice('Choose no more than seven dates.', 'info');
        return;
      }
      state.dates = [...state.dates, value];
      dateInput.value = '';
      invalidatePreview(state);
      renderDates(state);
    });
    dateInput.addEventListener('change', () => {
      document.getElementById('add-date').disabled = !dateInput.value || state.dates.length >= 7;
    });

    const profile = document.getElementById('profile');
    profile.addEventListener('change', () => {
      state.activeProfile = profile.value ? profile.value.toUpperCase() : null;
      invalidatePreview(state);
      updatePreviewButton(state);
    });
    document.getElementById('target-legs').addEventListener('input', () => {
      invalidatePreview(state);
      updatePreviewButton(state);
    });
    for (const id of ['acquire-sources', 'create-share-code']) {
      document.getElementById(id).addEventListener('change', () => invalidatePreview(state));
    }

    document.getElementById('build-form').addEventListener('submit', async (event) => {
      event.preventDefault();
      updatePreviewButton(state);
      if (document.getElementById('preview-button').disabled) return;
      state.previewing = true;
      const button = document.getElementById('preview-button');
      button.textContent = 'Creating local preview…';
      button.disabled = true;
      const report = document.getElementById('preview-report');
      report.replaceChildren();
      report.hidden = true;

      const request = {
        dates: [...state.dates],
        target_legs: Number(document.getElementById('target-legs').value),
        target_total_odds: null,
        bookie: 'sportybet',
        profile: profile.value,
        acquire_sources: document.getElementById('acquire-sources').checked,
        create_share_code: document.getElementById('create-share-code').checked,
      };
      const requestRevision = state.formRevision;
      try {
        const preview = await api.post('/api/v1/run-previews', request);
        if (requestRevision !== state.formRevision) {
          report.replaceChildren(element('p', '', 'The request changed while this preview was being prepared. The result was discarded; preview the updated request.'));
          report.hidden = false;
          updateStartReason(state);
        } else {
          renderPreview(state, preview);
          setNotice('Read-only preview completed. No provider acquisition, delivery, or wager was performed.', 'success');
        }
      } catch (error) {
        if (requestRevision !== state.formRevision) return;
        report.hidden = false;
        report.replaceChildren(element('h3', '', 'Preview unavailable'));
        if (error instanceof LocalRequestError) {
          report.append(element('p', 'inline-error-code', error.code));
          report.append(element('p', '', error.safeMessage));
        } else {
          report.append(element('p', '', 'The local preview could not be completed.'));
        }
        state.preview = null;
        updateStartReason(state);
      } finally {
        state.previewing = false;
        button.textContent = 'Preview request';
        updatePreviewButton(state);
      }
    });
  }

  function mountWorkspace(root, state, api) {
    root.querySelector('.workspace-boot').hidden = true;
    root.querySelector('.workspace-layout').hidden = false;
    root.setAttribute('aria-busy', 'false');
    document.body.dataset.theme = state.theme;
    renderCapabilities(state);
    renderRelease(state);
    renderDates(state);
    updateStartReason(state);

    for (const button of document.querySelectorAll('.nav-item[data-view]')) {
      button.addEventListener('click', () => setPage(state, button.dataset.view));
    }
    document.getElementById('theme-toggle').addEventListener('click', () => {
      state.theme = state.theme === 'dark' ? 'light' : 'dark';
      document.body.dataset.theme = state.theme;
      document.getElementById('theme-toggle').textContent = state.theme === 'dark'
        ? 'Switch to light theme' : 'Switch to dark theme';
    });
    document.getElementById('theme-toggle').textContent = state.theme === 'dark'
      ? 'Switch to light theme' : 'Switch to dark theme';
    document.getElementById('open-latest-run').addEventListener('click', () => openLatestRun(state, api));
    bindBuild(state, api);
    updatePreviewButton(state);
    loadLatestRun(state, api);
  }

  window.athenaBootstrap = async (session) => {
    if (bootstrapStarted) return;
    bootstrapStarted = true;
    delete window.athenaBootstrap;
    const root = document.getElementById('workspace-root');
    try {
      if (!session || typeof session.credential !== 'string'
          || typeof session.instance_id !== 'string' || typeof session.challenge !== 'string') {
        throw new LocalRequestError('LOCAL_SESSION_INVALID', 'The local session could not be verified.');
      }
      const api = createTransport(session.credential);
      const health = await api.get('/api/v1/health', {
        'X-Athena-Instance': session.instance_id,
        'X-Athena-Challenge': session.challenge,
      });
      if (health.instance_id !== session.instance_id || health.challenge !== session.challenge) {
        throw new LocalRequestError('LOCAL_SESSION_INVALID', 'The local session could not be verified.');
      }
      const capabilities = await api.get('/api/v1/capabilities');
      const state = createState(capabilities);
      mountWorkspace(root, state, api);
    } catch (_) {
      root.setAttribute('aria-busy', 'false');
      root.querySelector('.workspace-boot').hidden = true;
      root.querySelector('.workspace-layout').hidden = true;
      root.querySelector('.workspace-failure').hidden = false;
    }
  };
})();
