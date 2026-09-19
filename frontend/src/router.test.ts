import { describe, expect, it } from "vitest";
import { parseHash, routeHref } from "./router";

describe("hash router", () => {
  it("defaults to home", () => {
    expect(parseHash("")).toBe("home");
    expect(parseHash("#/")).toBe("home");
    expect(parseHash("#/unknown")).toBe("home");
  });

  it("resolves catalog", () => {
    expect(parseHash("#/catalog")).toBe("catalog");
  });

  it("round-trips hrefs", () => {
    expect(routeHref("home")).toBe("#/");
    expect(routeHref("catalog")).toBe("#/catalog");
    expect(parseHash(routeHref("catalog"))).toBe("catalog");
  });
});
