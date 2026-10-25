export function createSaveQueue() {
  let tail = Promise.resolve();
  const pending = new Map();

  return (key, save) => {
    const existing = pending.get(key);
    if (existing) return existing;

    const queued = tail.then(save);
    let tracked;
    tracked = queued.finally(() => {
      if (pending.get(key) === tracked) pending.delete(key);
    });
    pending.set(key, tracked);
    tail = tracked.catch(() => undefined);
    return tracked;
  };
}
