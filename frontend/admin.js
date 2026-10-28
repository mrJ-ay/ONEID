import { api, initOneID, showMessage } from "./common.js";

const message = document.querySelector("#message");
const consoleBody = document.querySelector("#consoleBody");
const statsEl = document.querySelector("#stats");
const userList = document.querySelector("#userList");
const searchInput = document.querySelector("#searchInput");
const refreshBtn = document.querySelector("#refreshBtn");
const filterButtons = document.querySelectorAll(".filter-tabs .chip");

let token = localStorage.getItem("oneid_local_access_token");
let currentAdmin = null;
let allUsers = [];
let allSites = ["pigsty", "fakepress", "nova", "inkvoid", "neonstrip"];
let currentFilter = "all";

const SITE_LABELS = {
  pigsty: "PIGSTY",
  fakepress: "FAKEPRESS",
  nova: "NOVA",
  inkvoid: "INKVOID",
  neonstrip: "NEON STRIP",
};

function formatDate(iso) {
  if (!iso) return "-";
  const d = new Date(iso);
  return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, "0")}.${String(d.getDate()).padStart(2, "0")}`;
}

function updateStats() {
  document.querySelector("#statTotal").textContent = allUsers.length;
  document.querySelector("#statAdmins").textContent = allUsers.filter((u) => u.is_admin).length;
  document.querySelector("#statSuspended").textContent = allUsers.filter((u) => u.global_suspended).length;
  document.querySelector("#statSiteBans").textContent = allUsers.reduce((acc, u) => acc + (u.site_suspensions?.length || 0), 0);
  statsEl.hidden = false;
}

function renderUsers() {
  const q = searchInput.value.trim().toLowerCase();
  const filtered = allUsers.filter((u) => {
    if (currentFilter === "admin" && !u.is_admin) return false;
    if (currentFilter === "suspended" && !u.global_suspended && !(u.site_suspensions?.length > 0)) return false;
    if (!q) return true;
    return u.username.toLowerCase().includes(q) || u.nickname.toLowerCase().includes(q);
  });

  userList.replaceChildren();
  if (!filtered.length) {
    const empty = document.createElement("div");
    empty.className = "admin-empty";
    empty.textContent = "조건에 맞는 계정이 없습니다.";
    userList.appendChild(empty);
    return;
  }

  for (const user of filtered) {
    const isSelf = currentAdmin && user.id === currentAdmin.id;
    const card = document.createElement("article");
    card.className = `user-card${user.global_suspended ? " is-suspended" : ""}`;

    const siteMap = new Map((user.site_suspensions || []).map((s) => [s.client_id, s]));

    card.innerHTML = `
      <div class="user-main">
        <div class="user-id-block">
          <div class="user-title-row">
            <strong>${escapeHtml(user.nickname)}</strong>
            <span class="user-handle">@${escapeHtml(user.username)}</span>
            <span class="badge ${user.is_admin ? "badge-admin" : "badge-user"}">${user.is_admin ? "관리자" : "일반"}</span>
            ${isSelf ? '<span class="badge badge-self">내 계정</span>' : ""}
            ${user.global_suspended ? '<span class="badge badge-danger">전체 정지됨</span>' : ""}
          </div>
          <p class="user-meta">가입일 ${formatDate(user.created_at)} · ID ${user.id.slice(0, 8)}${user.suspension_reason ? ` · 정지 사유: ${escapeHtml(user.suspension_reason)}` : ""}</p>
        </div>

        <div class="user-actions">
          <button type="button" class="button secondary small-btn" data-action="role" ${isSelf ? "disabled" : ""}>
            ${user.is_admin ? "일반으로 변경" : "관리자 지정"}
          </button>
          <button type="button" class="button ${user.global_suspended ? "secondary" : "warn-btn"} small-btn" data-action="suspend" ${isSelf ? "disabled" : ""}>
            ${user.global_suspended ? "전체 정지 해제" : "전체 정지"}
          </button>
          <button type="button" class="button danger-btn small-btn" data-action="delete" ${isSelf ? "disabled" : ""}>
            삭제
          </button>
        </div>
      </div>

      <div class="site-ban-row">
        <span class="site-ban-label">사이트별 이용 제한 (클릭하여 차단/해제):</span>
        <div class="site-chips"></div>
      </div>
    `;

    const chipsWrap = card.querySelector(".site-chips");
    for (const site of allSites) {
      const ban = siteMap.get(site);
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = `site-chip${ban ? " banned" : ""}`;
      btn.title = ban?.reason ? `차단 사유: ${ban.reason}` : `${SITE_LABELS[site] || site} 이용 ${ban ? "차단됨 (클릭 시 해제)" : "허용됨 (클릭 시 차단)"}`;
      btn.textContent = `${SITE_LABELS[site] || site.toUpperCase()} ${ban ? "✕ 차단됨" : "✓ 허용"}`;
      btn.addEventListener("click", () => toggleSiteSuspension(user, site, !ban));
      chipsWrap.appendChild(btn);
    }

    card.querySelector('[data-action="role"]').addEventListener("click", () => toggleRole(user));
    card.querySelector('[data-action="suspend"]').addEventListener("click", () => toggleGlobalSuspension(user));
    card.querySelector('[data-action="delete"]').addEventListener("click", () => removeUser(user));

    userList.appendChild(card);
  }
}

function escapeHtml(str) {
  return String(str ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

async function loadAll() {
  try {
    const [users, sites] = await Promise.all([
      api("/api/admin/users", { token }),
      api("/api/admin/sites", { token }).catch(() => allSites),
    ]);
    allUsers = users;
    if (Array.isArray(sites) && sites.length) allSites = sites;
    updateStats();
    renderUsers();
    showMessage(message, `총 ${allUsers.length}개의 계정을 불러왔습니다.`);
  } catch (error) {
    showMessage(message, error.message || "목록을 불러오지 못했습니다.", true);
  }
}

async function toggleRole(user) {
  const nextRole = user.is_admin ? "user" : "admin";
  if (!confirm(`@${user.username} 계정의 권한을 '${nextRole === "admin" ? "관리자" : "일반 사용자"}'로 변경할까요?`)) return;
  try {
    await api(`/api/admin/users/${encodeURIComponent(user.id)}/role`, {
      method: "PATCH",
      token,
      body: { role: nextRole },
    });
    await loadAll();
  } catch (error) {
    showMessage(message, error.message, true);
  }
}

async function toggleGlobalSuspension(user) {
  const nextSuspended = !user.global_suspended;
  let reason = null;
  if (nextSuspended) {
    reason = prompt(`@${user.username} 계정을 전체 사이트에서 정지합니다.\n정지 사유를 입력하세요 (선택):`, "운영 정책 위반");
    if (reason === null) return;
  }
  try {
    await api(`/api/admin/users/${encodeURIComponent(user.id)}/suspension`, {
      method: "PATCH",
      token,
      body: { suspended: nextSuspended, reason: reason || null },
    });
    await loadAll();
  } catch (error) {
    showMessage(message, error.message, true);
  }
}

async function toggleSiteSuspension(user, clientId, nextSuspended) {
  const label = SITE_LABELS[clientId] || clientId;
  let reason = null;
  if (nextSuspended) {
    reason = prompt(`@${user.username} 계정의 [${label}] 이용을 차단합니다.\n사유를 입력하세요 (선택):`, `${label} 이용 제한`);
    if (reason === null) return;
  }
  try {
    await api(`/api/admin/users/${encodeURIComponent(user.id)}/site-suspensions/${encodeURIComponent(clientId)}`, {
      method: "PATCH",
      token,
      body: { suspended: nextSuspended, reason: reason || null },
    });
    await loadAll();
  } catch (error) {
    showMessage(message, error.message, true);
  }
}

async function removeUser(user) {
  if (!confirm(`정말 @${user.username} (${user.nickname}) 계정을 영구 삭제할까요?\n이 작업은 되돌릴 수 없습니다.`)) return;
  try {
    await api(`/api/admin/users/${encodeURIComponent(user.id)}`, {
      method: "DELETE",
      token,
    });
    await loadAll();
  } catch (error) {
    showMessage(message, error.message, true);
  }
}

try {
  await initOneID();
  if (!token) throw new Error("로그인이 필요합니다.");
  currentAdmin = await api("/api/auth/me", { token });
  if (!currentAdmin.is_admin) {
    throw new Error("관리자 권한이 없는 계정입니다.");
  }
  consoleBody.hidden = false;
  await loadAll();
} catch (error) {
  showMessage(message, error.message || "접근 권한이 없습니다.", true);
  if (error.message === "로그인이 필요합니다.") {
    setTimeout(() => location.assign("/login.html?next=%2Fadmin.html"), 700);
  }
}

searchInput.addEventListener("input", renderUsers);
refreshBtn.addEventListener("click", loadAll);
filterButtons.forEach((btn) => {
  btn.addEventListener("click", () => {
    filterButtons.forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    currentFilter = btn.dataset.filter;
    renderUsers();
  });
});

document.querySelector("#logout").addEventListener("click", () => {
  localStorage.removeItem("oneid_local_access_token");
  location.assign("/");
});
