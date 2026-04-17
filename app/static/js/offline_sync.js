(function () {
  const DB_NAME = 'airside_ops_offline';
  const STORE = 'draft_forms';

  function openDb() {
    return new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, 1);
      req.onupgradeneeded = () => req.result.createObjectStore(STORE, { keyPath: 'id' });
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }

  async function saveDraft(form) {
    const data = Object.fromEntries(new FormData(form).entries());
    data.id = form.getAttribute('id') || `draft-${Date.now()}`;
    data.savedAt = new Date().toISOString();

    const db = await openDb();
    const tx = db.transaction(STORE, 'readwrite');
    tx.objectStore(STORE).put(data);
  }

  document.querySelectorAll('form').forEach((form) => {
    setInterval(() => saveDraft(form).catch(console.warn), 30000);

    form.querySelectorAll('.btn-save-draft').forEach((btn) => {
      btn.addEventListener('click', async () => {
        await saveDraft(form);
        alert('Draft saved offline.');
      });
    });
  });

  window.addEventListener('online', function () {
    console.info('Back online: queued drafts can be synced.');
  });
})();
