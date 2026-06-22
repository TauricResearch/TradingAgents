import { useEffect, type ReactNode } from 'react';
import { useAuthStore } from '../stores/authStore';
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
        <div className="w-12 h-12 rounded-full border-2 border-sky-500/30 border-t-sky-400 animate-spin" />
      </div>
    );
  }

  if (!user) {
    return <LoginPage />;
  }

  return <>{children}</>;
}
