import Keycloak from "keycloak-js";
import type KeycloakInstance from "keycloak-js";
import { getConfig } from "../config";

// Lazy singleton (P0-2): the instance is created AFTER runtime config
// is loaded, so url/realm/clientId are never baked in at build time.
// keycloak-js keeps tokens in memory, never in localStorage.
let instance: KeycloakInstance | null = null;

export function ensureKeycloak(): KeycloakInstance {
  if (!instance) {
    const cfg = getConfig();
    instance = new Keycloak({
      url: cfg.keycloakUrl,
      realm: cfg.keycloakRealm,
      clientId: cfg.keycloakClientId,
    });
  }
  return instance;
}

/** Test seam: drop the singleton between tests. */
export function __resetKeycloakForTests(): void {
  instance = null;
}
