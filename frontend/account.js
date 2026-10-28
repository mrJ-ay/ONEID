import { api, initOneID, showMessage } from "./common.js";

const message = document.querySelector("#message");
const profile = document.querySelector("#profile");
const nicknameForm = document.querySelector("#nicknameForm");
const newNicknameInput = document.querySelector("#newNickname");
const nicknameSubmit = document.querySelector("#nicknameSubmit");
const nicknameCooldownNote = document.querySelector("#nicknameCooldownNote");
const adminBox = document.querySelector("#adminBox");
const logoutBox = document.querySelector("#logoutBox");
const adminNavLink = document.querySelector("#adminNavLink");
let supabase = null;
let authMode = "local";
let token = localStorage.getItem("oneid_local_access_token");

function renderUser(user) {
  document.querySelector("#username").textContent = user.username;
  document.querySelector("#nickname").textContent = user.nickname;
  document.querySelector("#role").textContent = user.is_admin ? "관리자" : "사용자";
  newNicknameInput.value = user.nickname;
  profile.hidden = false;
  nicknameForm.hidden = false;
  logoutBox.hidden = false;

  if (user.is_admin) {
    adminBox.hidden = false;
    adminNavLink.hidden = false;
  }

  const nextIso = user.nickname_next_change_at;
  if (nextIso && new Date(nextIso) > new Date()) {
    const nextDate = new Date(nextIso);
    const diffSec = Math.max(0, Math.floor((nextDate - new Date()) / 1000));
    const days = Math.floor(diffSec / 86400);
    const hours = Math.floor((diffSec % 86400) / 3600);
    const mins = Math.max(1, Math.floor((diffSec % 3600) / 60));
    const remText = days > 0 ? `${days}일 ${hours}시간` : hours > 0 ? `${hours}시간 ${mins}분` : `${mins}분`;
    newNicknameInput.disabled = true;
    nicknameSubmit.disabled = true;
    nicknameCooldownNote.textContent = `쿨타임 적용 중 · ${remText} 후 다시 변경할 수 있습니다.`;
  } else {
    newNicknameInput.disabled = false;
    nicknameSubmit.disabled = false;
    nicknameCooldownNote.textContent = "닉네임은 변경 후 3일 동안 다시 바꿀 수 없습니다.";
  }
}

try {
  const initialized = await initOneID();
  supabase = initialized.supabase;
  authMode = initialized.config.auth_mode;
  if (authMode === "supabase") {
    const { data } = await supabase.auth.getSession();
    token = data.session?.access_token;
  }
  if (!token) throw new Error("로그인이 필요합니다.");
  const user = await api("/api/auth/me", { token });
  renderUser(user);
  message.textContent = "ONEID에 로그인되어 있습니다.";
} catch (error) {
  showMessage(message, error.message || "계정 정보를 불러오지 못했습니다.", true);
  if (error.message === "로그인이 필요합니다.") setTimeout(() => location.assign("/login.html"), 700);
}

nicknameForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  nicknameSubmit.disabled = true;
  try {
    const res = await api("/api/auth/nickname", {
      method: "PATCH",
      token,
      body: { nickname: newNicknameInput.value },
    });
    renderUser(res.user);
    showMessage(message, res.message || "닉네임이 변경되었습니다.");
  } catch (error) {
    nicknameSubmit.disabled = false;
    showMessage(message, error.message || "닉네임을 변경하지 못했습니다.", true);
  }
});

async function handleLogout() {
  if (authMode === "supabase" && supabase) await supabase.auth.signOut();
  localStorage.removeItem("oneid_local_access_token");
  location.assign("/");
}

document.querySelector("#logout").addEventListener("click", handleLogout);
document.querySelector("#cardLogout")?.addEventListener("click", handleLogout);
