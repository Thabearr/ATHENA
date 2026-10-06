/* Launch credentials remain in this closure, never browser storage or URLs. */
(() => {
  let started = false;
  window.athenaBootstrap = async (session) => {
    if (started) return;
    started = true;
    delete window.athenaBootstrap;
    const status = document.getElementById('local-status');
    try {
      const headers = {'X-Athena-Session': session.credential,
        'X-Athena-Instance': session.instance_id, 'X-Athena-Challenge': session.challenge};
      const healthResponse = await fetch('/api/v1/health', {headers, cache: 'no-store', redirect: 'error'});
      if (!healthResponse.ok) throw new Error('local verification failed');
      const health = await healthResponse.json();
      if (health.instance_id !== session.instance_id || health.challenge !== session.challenge)
        throw new Error('local verification failed');
      const response = await fetch('/api/v1/capabilities', {headers, cache: 'no-store', redirect: 'error'});
      if (!response.ok) throw new Error('local evidence unavailable');
      const snapshot = await response.json();
      status.textContent = 'Verified local session. Model and market readiness remain unproven.';
      const list = document.getElementById('capabilities');
      for (const capability of snapshot.capabilities) {
        const item = document.createElement('li');
        item.textContent = `${capability.capability_id}: ${capability.state} — ${capability.reason}`;
        list.appendChild(item);
      }
    } catch (_) {
      status.textContent = 'Local verification failed. Close ATHENA and start a new session.';
    }
  };
})();
