import { useEffect, useState } from "react";

export type Route = "home" | "catalog";

export function parseHash(hash: string): Route {
  return hash.startsWith("#/catalog") ? "catalog" : "home";
}

export function routeHref(route: Route): string {
  return route === "catalog" ? "#/catalog" : "#/";
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
