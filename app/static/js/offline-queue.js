/*
 * ArogyaMaa ASHA — Offline assessment queue
 *
 * Field workers in low/no-connectivity villages submit assessments that must not be lost.
 * This module persists submissions in IndexedDB and replays them to /asha/assessment when
 * connectivity returns. Each item carries a client-generated `client_uuid`; the server
 * ingest is idempotent on it, so replays after flaky connectivity never duplicate rows.
 *
 * Public API (window.OfflineQueue):
 *   enqueue(payload)   -> Promise<number>  add an item; resolves with the new pending count
 *   flushQueue()       -> Promise<{synced, remaining}>  POST pending items; delete on success
 *   pendingCount()     -> Promise<number>
 *   onChange(cb)       -> subscribe to pending-count changes (cb receives the count)
 *   isSupported()      -> boolean
 */
(function (window) {
  'use strict';

  const DB_NAME = 'arogyamaa-offline';
  const STORE = 'pending_assessments';
  const ENDPOINT = '/asha/assessment';

  const supported = 'indexedDB' in window;
  const listeners = [];
  let flushing = false;

  function notify(count) {
    listeners.forEach((cb) => {
      try { cb(count); } catch (e) { /* listener errors must not break the queue */ }
    });
  }

  function openDB() {
    return new Promise((resolve, reject) => {
      const req = window.indexedDB.open(DB_NAME, 1);
      req.onupgradeneeded = () => {
        const db = req.result;
        if (!db.objectStoreNames.contains(STORE)) {
          db.createObjectStore(STORE, { keyPath: 'client_uuid' });
        }
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }

  function tx(mode, fn) {
    return openDB().then((db) => new Promise((resolve, reject) => {
      const t = db.transaction(STORE, mode);
      const store = t.objectStore(STORE);
      let result;
      Promise.resolve(fn(store)).then((r) => { result = r; });
      t.oncomplete = () => { db.close(); resolve(result); };
      t.onerror = () => { db.close(); reject(t.error); };
      t.onabort = () => { db.close(); reject(t.error); };
    }));
  }

  function reqAsPromise(request) {
    return new Promise((resolve, reject) => {
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  }

  async function pendingCount() {
    if (!supported) return 0;
    return tx('readonly', (store) => reqAsPromise(store.count()));
  }

  async function getAll() {
    if (!supported) return [];
    return tx('readonly', (store) => reqAsPromise(store.getAll()));
  }

  async function enqueue(payload) {
    if (!supported) throw new Error('IndexedDB unavailable');
    if (!payload.client_uuid) {
      payload.client_uuid = (window.crypto && window.crypto.randomUUID)
        ? window.crypto.randomUUID()
        : 'cu-' + Date.now() + '-' + Math.round(Math.random() * 1e9);
    }
    const record = { client_uuid: payload.client_uuid, payload: payload, queued_at: new Date().toISOString() };
    await tx('readwrite', (store) => reqAsPromise(store.put(record)));
    const count = await pendingCount();
    notify(count);
    // Ask the browser to sync when it can (best-effort; the 'online' listener is the fallback).
    if ('serviceWorker' in navigator && 'SyncManager' in window) {
      try {
        const reg = await navigator.serviceWorker.ready;
        await reg.sync.register('sync-assessments');
      } catch (e) { /* Background Sync unsupported/denied — 'online' event still flushes */ }
    }
    return count;
  }

  async function remove(clientUuid) {
    await tx('readwrite', (store) => reqAsPromise(store.delete(clientUuid)));
  }

  async function flushQueue() {
    if (!supported || flushing || !navigator.onLine) {
      return { synced: 0, remaining: await pendingCount() };
    }
    flushing = true;
    let synced = 0;
    try {
      const items = await getAll();
      for (const item of items) {
        let response;
        try {
          response = await fetch(ENDPOINT, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(item.payload),
          });
        } catch (networkErr) {
          break; // lost connectivity again — keep this and remaining items queued
        }
        if (response.ok) {
          await remove(item.client_uuid); // idempotent server: duplicates also return 2xx
          synced += 1;
          notify(await pendingCount());
        } else if (response.status === 400) {
          // Malformed payload would fail forever — drop it so it can't block the queue.
          console.warn('[offline-queue] dropping rejected assessment', item.client_uuid);
          await remove(item.client_uuid);
          notify(await pendingCount());
        } else {
          // 401/403 (session expired) or 5xx (server) — transient; stop and retry later.
          break;
        }
      }
    } finally {
      flushing = false;
    }
    return { synced: synced, remaining: await pendingCount() };
  }

  function onChange(cb) {
    if (typeof cb === 'function') listeners.push(cb);
  }

  // Auto-flush triggers.
  window.addEventListener('online', () => { flushQueue(); });
  window.addEventListener('load', () => {
    pendingCount().then(notify);
    if (navigator.onLine) flushQueue();
  });
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.addEventListener('message', (event) => {
      if (event.data && event.data.type === 'flush-queue') flushQueue();
    });
  }

  window.OfflineQueue = {
    enqueue: enqueue,
    flushQueue: flushQueue,
    pendingCount: pendingCount,
    onChange: onChange,
    isSupported: function () { return supported; },
  };
})(window);
