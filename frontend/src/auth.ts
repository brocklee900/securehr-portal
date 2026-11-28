import Keycloak from "keycloak-js";

export type Role = "employee" | "manager" | "hr_admin";

/** Keycloak lives next to the portal: portal.<domain> -> auth.<domain> (works for localhost and the shared server). */
const authUrl = `https://${window.location.hostname.replace(/^portal\./, "auth.")}`;

export const keycloak = new Keycloak({
  url: authUrl,
  realm: "securehr",
  clientId: "securehr-portal",
});

export async function initAuth(): Promise<boolean> {
  return keycloak.init({ onLoad: "login-required", pkceMethod: "S256", checkLoginIframe: false });
}

export function currentRole(): Role {
  const roles: string[] = keycloak.tokenParsed?.realm_access?.roles ?? [];
  return (["hr_admin", "manager", "employee"] as Role[]).find((r) => roles.includes(r)) ?? "employee";
}

/** UI gating is convenience only; the API and Postgres RLS enforce access. */
export const canSeeSalary = (r: Role) => r === "manager" || r === "hr_admin";
