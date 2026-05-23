import { getStayApiDetail, StayApiError } from "./stay-server";

export type LoginErrorKey =
  | "apiUnavailable"
  | "invalidCredentials"
  | "noStaffAccess"
  | "noTenantAccess"
  | "noReceptionAccess"
  | "selectTenant"
  | "loginFailed"
  | "loginFailedDetail";

export function mapLoginError(err: unknown): { errorKey: LoginErrorKey; status: number; detail?: string } {
  if (err instanceof StayApiError) {
    if (err.isNetworkError) {
      return { errorKey: "apiUnavailable", status: 503 };
    }

    const detail = getStayApiDetail(err.body);
    const detailLower = detail.toLowerCase();

    if (err.status === 401 || detailLower.includes("invalid credentials")) {
      return { errorKey: "invalidCredentials", status: 401 };
    }

    if (err.status === 403) {
      if (detailLower.includes("staff access")) {
        return { errorKey: "noStaffAccess", status: 403 };
      }
      if (detailLower.includes("tenant access")) {
        return { errorKey: "noTenantAccess", status: 403 };
      }
      return { errorKey: "noReceptionAccess", status: 403, detail };
    }

    if (err.status === 409) {
      return { errorKey: "selectTenant", status: 409 };
    }

    if (err.status >= 500) {
      return { errorKey: "apiUnavailable", status: 503 };
    }

    if (process.env.NODE_ENV !== "production") {
      return {
        errorKey: "loginFailedDetail",
        status: err.status || 400,
        detail: detail || err.message,
      };
    }

    return { errorKey: "loginFailed", status: err.status || 400 };
  }

  return { errorKey: "loginFailed", status: 500 };
}
