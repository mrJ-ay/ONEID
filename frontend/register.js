import { api, safeNext, showMessage } from "./common.js";

const form = document.querySelector("#registerForm");
const message = document.querySelector("#message");
const params = new URLSearchParams(location.search);
const next = safeNext(params.get("next"));

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = form.querySelector("button");
  button.disabled = true;
  showMessage(message, "계정을 만드는 중…");
  try {
    const result = await api("/api/auth/register", {
      method: "POST",
      body: {
        username: form.username.value,
        nickname: form.nickname.value,
        password: form.password.value,
      },
    });
    showMessage(message, result.message);
    const returnParams = new URLSearchParams(params);
    returnParams.set("username", form.username.value);
    if (!returnParams.has("client_id")) returnParams.set("next", next);
    setTimeout(() => location.assign(`/login.html?${returnParams}`), 700);
  } catch (error) {
    showMessage(message, error.message || "계정을 만들지 못했습니다.", true);
  } finally {
    button.disabled = false;
  }
});
