function retryAfterMilliseconds(value) {
  if (!value) return 0;
  const seconds = Number(value);
  if (Number.isFinite(seconds)) return Math.max(0, seconds * 1000);
  const date = Date.parse(value);
  return Number.isFinite(date) ? Math.max(0, date - Date.now()) : 0;
}

export function isPrivateAssetUrl(source) {
  if (typeof source !== "string" || !source) return false;
  try {
    return new URL(source, "http://localhost").pathname.includes("/api/v1/assets/private/");
  } catch {
    return false;
  }
}

export async function fetchPrivateImage(source, {
  fetchImpl = fetch,
  refreshSource = async () => source,
  wait = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds)),
} = {}) {
  let response = await fetchImpl(source, { credentials: "include" });
  let activeSource = source;
  let refreshed = false;
  if (response.status === 429) {
    await wait(retryAfterMilliseconds(response.headers.get("Retry-After")));
    refreshed = true;
    let refreshedSource;
    try {
      refreshedSource = await refreshSource();
    } catch (failure) {
      if (failure instanceof Error) failure.refreshed = true;
      throw failure;
    }
    if (typeof refreshedSource === "string" && refreshedSource) activeSource = refreshedSource;
    response = await fetchImpl(activeSource, { credentials: "include" });
  }
  if (!response.ok) {
    const failure = new Error(response.status === 429
      ? "The image service is busy. Please try loading this page again."
      : "This private image could not be loaded.");
    failure.refreshed = refreshed;
    throw failure;
  }
  return { blob: await response.blob(), source: activeSource };
}
