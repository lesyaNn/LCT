export const authService = {
  mode(): 'mock' | 'keycloak' {
    // Mock data never opts the user out of OIDC. Mock auth remains a dev-only
    // preview override unless it is separately enabled for a production demo.
    const mockRequested = process.env.NEXT_PUBLIC_AUTH_MODE === 'mock';
    const mockAllowed = process.env.NODE_ENV !== 'production'
      || process.env.NEXT_PUBLIC_ALLOW_MOCK_AUTH_IN_PRODUCTION === 'true';
    return mockRequested && mockAllowed ? 'mock' : 'keycloak';
  },

  logout(): void {
    if (typeof window === 'undefined') return;

    window.localStorage.removeItem('mock-auth-user');
    // Keycloak logout is handled by the existing adapter; this service only
    // clears the local preview state used when auth mode is `mock`.
  },
};
