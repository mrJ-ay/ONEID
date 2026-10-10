export async function initOneID() {
  const response = await fetch("/api/public-config", { cache: "no-store" });
  const config = await response.json();
  let supabase = null;
  if (config.auth_mode === "supabase") {
    const { createClient } = await import("https://esm.sh/@supabase/supabase-js@2");
    supabase = createClient(config.supabase_url, config.supabase_anon_key);
  }
  return { config, supabase };
}

export function safeNext(value) {
  if (!value) return "/account.html";
  try {
    const target = new URL(value, window.location.origin);
    if (target.origin !== window.location.origin) return "/account.html";
    return `${target.pathname}${target.search}${target.hash}`;
  } catch {
    return "/account.html";
  }
}

export async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (options.token) headers.set("Authorization", `Bearer ${options.token}`);
  const response = await fetch(path, { ...options, headers, body: options.body ? JSON.stringify(options.body) : undefined });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || "요청을 처리하지 못했습니다.");
  return payload;
}

export function showMessage(element, text, isError = false) {
  element.textContent = text;
  element.classList.toggle("error", isError);
  element.classList.toggle("success", !isError);
}
