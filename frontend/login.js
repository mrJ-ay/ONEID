import { api, initOneID, safeNext, showMessage } from "./common.js";

const form = document.querySelector("#loginForm");
const message = document.querySelector("#message");
const username = document.querySelector("#username");
const password = document.querySelector("#password");
const next = safeNext(new URLSearchParams(location.search).get("next"));
const params = new URLSearchParams(location.search);
const oauth = {
  client_id: params.get("client_id"),
  redirect_uri: params.get("redirect_uri"),
  code_challenge: params.get("code_challenge"),
  state: params.get("state"),
};
const registerLink = document.querySelector("#registerLink");
if (registerLink && oauth.client_id) registerLink.href = `/register.html?${new URLSearchParams(oauth)}`;
username.value = params.get("username") || "";

async function continueToSite(accessToken) {
  if (!oauth.client_id) { location.assign(next); return; }
  const result = await api("/api/oauth/authorize", {
    method: "POST",
    token: accessToken,
    body: oauth,
  });
  location.assign(result.redirect_uri);
}

async function savedAccessToken(config, supabase) {
  if (config.auth_mode === "supabase") {
    const { data } = await supabase.auth.getSession();
    return data.session?.access_token || null;
  }
  return localStorage.getItem("oneid_local_access_token");
}

async function resumeSSO() {
  if (!oauth.client_id || !oauth.redirect_uri || !oauth.code_challenge || !oauth.state) return;
  const { config, supabase } = await initOneID();
  const token = await savedAccessToken(config, supabase);
  if (!token) return;
  try {
    await api("/api/auth/me", { token });
    await continueToSite(token);
  } catch {
    if (config.auth_mode === "supabase") await supabase.auth.signOut();
    else localStorage.removeItem("oneid_local_access_token");
  }
}

resumeSSO().catch(() => {});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = form.querySelector("button");
  button.disabled = true;
  showMessage(message, "로그인 중…");
  try {
    const result = await api("/api/auth/login", { method: "POST", body: { username: username.value, password: password.value } });
    if (result.auth_mode === "supabase") {
      const { supabase } = await initOneID();
      const { error } = await supabase.auth.setSession({ access_token: result.access_token, refresh_token: result.refresh_token });
      if (error) throw error;
    } else {
      localStorage.setItem("oneid_local_access_token", result.access_token);
    }
    await continueToSite(result.access_token);
  } catch (error) {
    showMessage(message, error.message || "로그인하지 못했습니다.", true);
  } finally {
    button.disabled = false;
  }
});
