import { api, initOneID, showMessage } from "./common.js";

const message = document.querySelector("#message");
const profile = document.querySelector("#profile");
let supabase = null;
let authMode = "local";
let localToken = localStorage.getItem("oneid_local_access_token");

try {
  const initialized = await initOneID();
  supabase = initialized.supabase;
  authMode = initialized.config.auth_mode;
  let token = localToken;
  if (authMode === "supabase") {
    const { data } = await supabase.auth.getSession();
    token = data.session?.access_token;
  }
  if (!token) throw new Error("로그인이 필요합니다.");
  const user = await api("/api/auth/me", { token });
  document.querySelector("#username").textContent = user.username;
  document.querySelector("#nickname").textContent = user.nickname;
  document.querySelector("#role").textContent = user.is_admin ? "관리자" : "사용자";
  profile.hidden = false;
  message.textContent = "ONEID에 로그인되어 있습니다.";
} catch (error) {
  showMessage(message, error.message || "계정 정보를 불러오지 못했습니다.", true);
  if (error.message === "로그인이 필요합니다.") setTimeout(() => location.assign("/login.html"), 700);
}

document.querySelector("#logout").addEventListener("click", async () => {
  if (authMode === "supabase" && supabase) await supabase.auth.signOut();
  localStorage.removeItem("oneid_local_access_token");
  location.assign("/");
});
