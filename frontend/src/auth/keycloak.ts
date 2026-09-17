import Keycloak from "keycloak-js";

const url = import.meta.env.VITE_KEYCLOAK_URL ?? "http://localhost:8081";

// Singleton: keycloak-js keeps tokens in memory, never in localStorage.
export const keycloak = new Keycloak({
  url,
  realm: "rtk",
  clientId: "rtk-frontend",
});
