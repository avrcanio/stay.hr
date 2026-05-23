import { NextResponse } from "next/server";
import { applyLocaleCookie, normalizePreferredLocale } from "@/lib/locale-cookie";
import { mapLoginError } from "@/lib/login-errors";
import { stayLoginFetch, StayApiError } from "@/lib/stay-server";
import { RECEPTION_SESSION_COOKIE } from "@/lib/types";

type LoginBody = {
  username?: string;
  password?: string;
  tenant_id?: number;
};

type LoginSuccess = {
  ok: boolean;
  user: { username: string; preferred_language: string };
  tenant: { id: number; name: string; slug: string };
};

type LoginTenantRequired = {
  requires_tenant: boolean;
  tenants: Array<{ id: number; name: string; slug: string }>;
};

export async function POST(request: Request) {
  let body: LoginBody;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const username = (body.username || "").trim();
  const password = body.password || "";
  if (!username || !password) {
    return NextResponse.json({ error: "Korisničko ime i lozinka su obavezni." }, { status: 400 });
  }

  try {
    const { data, sessionId } = await stayLoginFetch<LoginSuccess | LoginTenantRequired>(
      "/api/v1/auth/reception-login/",
      {
        username,
        password,
        tenant_id: body.tenant_id,
      },
    );

    if ("requires_tenant" in data && data.requires_tenant) {
      return NextResponse.json(
        {
          requires_tenant: true,
          tenants: data.tenants,
        },
        { status: 409 },
      );
    }

    const success = data as LoginSuccess;

    if (!sessionId) {
      return NextResponse.json({ error: "Prijava nije uspjela — session nije kreiran." }, { status: 500 });
    }

    const res = NextResponse.json({
      ok: true,
      tenant: success.tenant,
      user: success.user,
    });
    res.cookies.set(RECEPTION_SESSION_COOKIE, sessionId, {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax",
      path: "/",
      maxAge: 60 * 60 * 24 * 14,
    });
    applyLocaleCookie(res, normalizePreferredLocale(success.user.preferred_language));
    return res;
  } catch (err) {
    if (err instanceof StayApiError && err.status === 409) {
      const body = err.body as LoginTenantRequired | null;
      if (body?.requires_tenant && Array.isArray(body.tenants)) {
        return NextResponse.json(
          {
            requires_tenant: true,
            tenants: body.tenants,
          },
          { status: 409 },
        );
      }
    }
    const { errorKey, status, detail } = mapLoginError(err);
    return NextResponse.json({ errorKey, detail }, { status });
  }
}
