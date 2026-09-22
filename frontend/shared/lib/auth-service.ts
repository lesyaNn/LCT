export const authService = {
  mode(): 'mock' | 'keycloak' {
    return process.env.NEXT_PUBLIC_AUTH_MODE === 'keycloak' ? 'keycloak' : 'mock';
  },

  logout(): void {
    if (typeof window === 'undefined') return;

    window.localStorage.removeItem('mock-auth-user');
    // TODO: replace mock logout with Keycloak logout during authentication integration
  },
};
