import { timingSafeEqual } from "node:crypto";
import { NextResponse } from "next/server";

function safeEqual(left: string, right: string) {
  const leftBuffer = Buffer.from(left);
  const rightBuffer = Buffer.from(right);
  return leftBuffer.length === rightBuffer.length && timingSafeEqual(leftBuffer, rightBuffer);
}

function configuredCredentials() {
  const username = process.env.WORKBENCH_ADMIN_USER?.trim() || "";
  const password = process.env.WORKBENCH_ADMIN_PASSWORD || "";
  return username && password ? { username, password } : null;
}

export function isWorkbenchAdminAuthorized(request: Request) {
  const credentials = configuredCredentials();
  if (!credentials) return process.env.NODE_ENV !== "production";

  const authorization = request.headers.get("authorization") || "";
  if (!authorization.startsWith("Basic ")) return false;

  try {
    const decoded = Buffer.from(authorization.slice(6), "base64").toString("utf8");
    const separator = decoded.indexOf(":");
    if (separator < 0) return false;
    return (
      safeEqual(decoded.slice(0, separator), credentials.username) &&
      safeEqual(decoded.slice(separator + 1), credentials.password)
    );
  } catch {
    return false;
  }
}

export function requireWorkbenchAdmin(request: Request) {
  if (isWorkbenchAdminAuthorized(request)) return null;

  const configured = Boolean(configuredCredentials());
  return NextResponse.json(
    {
      error: configured
        ? "需要工作台管理员身份认证"
        : "生产环境未配置 WORKBENCH_ADMIN_USER 和 WORKBENCH_ADMIN_PASSWORD",
    },
    {
      status: configured ? 401 : 503,
      headers: configured ? { "WWW-Authenticate": 'Basic realm="Football Predictor Workbench"' } : undefined,
    },
  );
}
