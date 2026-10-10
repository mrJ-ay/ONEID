import { initOneID, showMessage } from "./common.js";

const params = new URLSearchParams(location.search);
const authorizationId = params.get("authorization_id");
const message = document.querySelector("#message");
const approve = document.querySelector("#approve");
const deny = document.querySelector("#deny");
let supabase;

function labels(scopeText) {
  const names = { openid: "로그인 확인", profile: "사용자명과 닉네임", email: "이메일 주소", phone: "전화번호" };
  return scopeText.split(/\s+/).filter(Boolean).map((scope) => names[scope] || scope).join(" · ");
}

try {
  if (!authorizationId) throw new Error("인증 요청 정보가 없습니다.");
  const initialized = await initOneID();
  if (!initialized.supabase) throw new Error("사이트 로그인(OIDC)은 Supabase 설정 후 사용할 수 있습니다.");
  supabase = initialized.supabase;
  const { data: sessionData } = await supabase.auth.getSession();
  if (!sessionData.session) {
    const next = `${location.pathname}${location.search}`;
    location.assign(`/login.html?next=${encodeURIComponent(next)}`);
  } else {
    const { data, error } = await supabase.auth.oauth.getAuthorizationDetails(authorizationId);
    if (error) throw error;
    const scopes = String(data.scope || "openid").split(/\s+/).filter(Boolean);
    document.querySelector("#clientName").textContent = `${data.client?.name || data.client_name || "사이트"}에서 ONEID 로그인을 요청했습니다.`;
    document.querySelector("#scopes").textContent = `요청 정보: ${labels(scopes.join(" "))}`;
    if (scopes.includes("email") || scopes.includes("phone")) {
      throw new Error("이 ONEID 계정은 이메일·전화번호를 사이트에 제공하지 않습니다. 해당 정보 범위를 제외하도록 사이트 설정을 변경해야 합니다.");
    }
    approve.disabled = false;
    deny.disabled = false;
  }
} catch (error) {
  showMessage(message, error.message || "인증 요청을 불러오지 못했습니다.", true);
}

approve.addEventListener("click", async () => {
  approve.disabled = true;
  deny.disabled = true;
  try {
    const { data, error } = await supabase.auth.oauth.approveAuthorization(authorizationId);
    if (error) throw error;
    location.assign(data.redirect_url);
  } catch (error) {
    showMessage(message, error.message || "요청을 허용하지 못했습니다.", true);
    approve.disabled = false;
    deny.disabled = false;
  }
});

deny.addEventListener("click", async () => {
  approve.disabled = true;
  deny.disabled = true;
  try {
    const { data, error } = await supabase.auth.oauth.denyAuthorization(authorizationId);
    if (error) throw error;
    location.assign(data.redirect_url);
  } catch (error) {
    showMessage(message, error.message || "요청을 거부하지 못했습니다.", true);
    approve.disabled = false;
    deny.disabled = false;
  }
});
