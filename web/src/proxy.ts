import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { isWorkbenchAdminAuthorized } from "@/lib/workbenchAuth";

export function proxy(request: NextRequest) {
  if (isWorkbenchAdminAuthorized(request)) return NextResponse.next();

  const configured = Boolean(
    process.env.WORKBENCH_ADMIN_USER?.trim() && process.env.WORKBENCH_ADMIN_PASSWORD,
  );
  return new NextResponse(
    configured ? "需要工作台管理员身份认证" : "生产环境未配置工作台管理员账号",
    {
      status: configured ? 401 : 503,
      headers: configured
        ? { "WWW-Authenticate": 'Basic realm="Football Predictor Workbench"' }
        : undefined,
    },
  );
}

export const config = {
  matcher: [
    "/controller/:path*",
    "/setup/:path*",
    "/chat/:path*",
    "/api/automation/:path*",
    "/api/controller/:path*",
    "/api/llm-config/:path*",
    "/api/chat/:path*",
    "/api/ingest/:path*",
    "/api/odds/:path*",
    "/api/backtest/:path*",
    "/api/predictions/snapshot/:path*",
    "/api/fixtures/:fixtureId/explain",
    "/api/fixtures/:fixtureId/explanations",
  ],
};
