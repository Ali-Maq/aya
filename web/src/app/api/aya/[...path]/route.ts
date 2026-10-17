import { NextRequest, NextResponse } from "next/server";
import { getCurrentUserSS } from "@/lib/users/svcSS";
import { Permission } from "@/lib/types";
import { hasPermission } from "@/lib/permissions/utils";

export const dynamic = "force-dynamic";

interface RouteContext {
  params: Promise<{ path: string[] }>;
}

async function forward(request: NextRequest, context: RouteContext) {
  const user = await getCurrentUserSS();
  if (
    !user ||
    !hasPermission(
      user.effective_permissions ?? [],
      Permission.FULL_ADMIN_PANEL_ACCESS
    )
  ) {
    return NextResponse.json(
      { error: "Factory access requires an administrator session" },
      { status: 403 }
    );
  }
  const { path } = await context.params;
  const endpoint = path.join("/");
  const allowed =
    request.method === "GET"
      ? /^(requests|deployment|runs|runs\/[a-f0-9]{16})$/.test(endpoint)
      : request.method === "POST" && /^(run|requests|ask)$/.test(endpoint);
  if (!allowed)
    return NextResponse.json(
      { error: "Unknown factory operation" },
      { status: 404 }
    );
  if (
    request.method === "POST" &&
    (request.headers.get("origin") !== request.nextUrl.origin ||
      request.headers.get("x-aya-request") !== "1")
  ) {
    return NextResponse.json(
      { error: "Invalid request origin" },
      { status: 403 }
    );
  }
  const token = process.env.AYA_FACTORY_TOKEN;
  if (!token)
    return NextResponse.json(
      { error: "Factory connection is not configured" },
      { status: 503 }
    );
  const body = request.method === "POST" ? await request.text() : undefined;
  if (body && body.length > 12000)
    return NextResponse.json({ error: "Request too large" }, { status: 413 });
  try {
    const upstream = await fetch(
      `${process.env.AYA_FACTORY_URL || "http://127.0.0.1:8771"}/${endpoint}`,
      {
        method: request.method,
        body,
        cache: "no-store",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
          "X-AYA-User": user.id,
        },
        signal: AbortSignal.timeout(endpoint === "ask" ? 240000 : 45000),
      }
    );
    return new NextResponse(await upstream.text(), {
      status: upstream.status,
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": "no-store",
      },
    });
  } catch {
    return NextResponse.json(
      { error: "Factory service is unavailable" },
      { status: 503 }
    );
  }
}

export const GET = forward;
export const POST = forward;
