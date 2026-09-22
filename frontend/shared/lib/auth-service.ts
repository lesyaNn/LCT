export const authService = {
  mode(): 'mock' | 'keycloak' {
    return process.env.NEXT_PUBLIC_AUTH_MODE === 'mock' ? 'mock' : 'keycloak';
  },

  logout(): void {
    if (typeof window === 'undefined') return;

    window.localStorage.removeItem('mock-auth-user');
    // Keycloak logout is handled by the existing adapter; this service only
    // clears the local preview state used when auth mode is `mock`.
  },
};
