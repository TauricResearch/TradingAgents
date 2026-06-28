import { useEffect, type ReactNode } from 'react';
import { useAuthStore } from '../stores/authStore';
import { Spinner } from '../ui';
import { LoginPage } from './LoginPage';

interface AuthGateProps {
  children: ReactNode;
}

export function AuthGate({ children }: AuthGateProps) {
  const { user, loading, check } = useAuthStore();

  useEffect(() => {
    check();
  }, [check]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-market-DEFAULT">
        <Spinner size="lg" />
      </div>
    );
  }

  if (!user) {
    return <LoginPage />;
  }

  return <>{children}</>;
}
