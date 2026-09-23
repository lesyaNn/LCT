import { useEffect, useState } from "react";

export type Route = "home" | "catalog" | "analytics";

export function parseHash(hash: string): Route {
  if (hash.startsWith("#/catalog")) return "catalog";
  // P4-11-01: страница графиков на мок-данных (PNG-экспорт без бэка).
  if (hash.startsWith("#/analytics")) return "analytics";
  return "home";
}

export function routeHref(route: Route): string {
  if (route === "catalog") return "#/catalog";
  if (route === "analytics") return "#/analytics";
  return "#/";
}

/** Minimal hash router (P1): deep links without adding react-router (yet). */
export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseHash(window.location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parseHash(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}
