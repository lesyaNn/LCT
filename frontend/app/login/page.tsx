import LoginClient from './login-client';

// Read at request time so one build can serve regular and demo environments.
export const dynamic = 'force-dynamic';

export default function LoginPage() {
  return <LoginClient demoEnabled={process.env.DEMO_MODE === 'true'} />;
}
