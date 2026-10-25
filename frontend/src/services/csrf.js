function readCookie(name) {
  if (typeof document === "undefined") return "";
  const prefix = `${name}=`;
  const cookie = document.cookie.split("; ").find((value) => value.startsWith(prefix));
  return cookie ? decodeURIComponent(cookie.slice(prefix.length)) : "";
}

export function hasCsrfToken(tokenType = "access") {
  return Boolean(readCookie(tokenType === "refresh" ? "csrf_refresh_token" : "csrf_access_token"));
}

export function csrfHeaders(tokenType = "access", headers = {}) {
  const csrf = readCookie(tokenType === "refresh" ? "csrf_refresh_token" : "csrf_access_token");
  return csrf ? { ...headers, "X-CSRF-TOKEN": csrf } : headers;
}
