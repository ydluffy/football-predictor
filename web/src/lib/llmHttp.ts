export function normalizeBaseUrl(provider: string | undefined, baseUrl: string) {
  let b = (baseUrl || "").trim().replace(/\/+$/, "");
  const p = String(provider || "").trim().toLowerCase();

  // 通义千问（百炼/DashScope）的 OpenAI 兼容 Chat API 通常位于 /compatible-mode/v1
  if (p === "qwen" && b && !/\/compatible-mode\/v1$/i.test(b) && !/\/compatible-mode\/v1\//i.test(b)) {
    b = b + "/compatible-mode/v1";
    b = b.replace(/\/+$/, "");
  }

  return b;
}

const DEFAULT_ALLOWED_LLM_HOSTS = [
  "ark.cn-beijing.volces.com",
  "api.deepseek.com",
  "dashscope.aliyuncs.com",
];

export function validateLlmBaseUrl(provider: string | undefined, baseUrl: string) {
  const normalized = normalizeBaseUrl(provider, baseUrl);
  if (!normalized) return { ok: false as const, error: "base_url 不能为空" };

  let url: URL;
  try {
    url = new URL(normalized);
  } catch {
    return { ok: false as const, error: "base_url 不是有效网址" };
  }

  if (url.protocol !== "https:") {
    return { ok: false as const, error: "base_url 必须使用 HTTPS" };
  }
  if (url.username || url.password || (url.port && url.port !== "443")) {
    return { ok: false as const, error: "base_url 不允许包含凭据或自定义端口" };
  }

  const additionalHosts = (process.env.LLM_ALLOWED_HOSTS || "")
    .split(",")
    .map((host) => host.trim().toLowerCase())
    .filter(Boolean);
  const allowedHosts = new Set([...DEFAULT_ALLOWED_LLM_HOSTS, ...additionalHosts]);
  if (!allowedHosts.has(url.hostname.toLowerCase())) {
    return {
      ok: false as const,
      error: `不允许访问该模型主机：${url.hostname}。如确有需要，请在服务端 LLM_ALLOWED_HOSTS 中配置。`,
    };
  }

  return { ok: true as const, baseUrl: normalized };
}

export function buildChatCompletionsUrl(provider: string | undefined, baseUrl: string) {
  const validation = validateLlmBaseUrl(provider, baseUrl);
  return validation.ok ? `${validation.baseUrl}/chat/completions` : "";
}
