import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export interface User {
  email: string;
  name: string;
  picture: string;
}

interface AuthState {
  user: User | null;
  loading: boolean;
  setUser: (user: User | null) => void;
  setLoading: (loading: boolean) => void;
  check: () => Promise<void>;
  logout: () => Promise<void>;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      loading: true,
      setUser: (user) => set({ user }),
      setLoading: (loading) => set({ loading }),
      check: async () => {
        set({ loading: true });
        try {
          const res = await fetch('/api/auth/me');
          if (res.ok) {
            const user = await res.json();
            set({ user, loading: false });
          } else {
            set({ user: null, loading: false });
          }
        } catch {
          set({ user: null, loading: false });
        }
      },
      logout: async () => {
        await fetch('/api/auth/logout', { method: 'POST' });
        set({ user: null });
      },
    }),
    { name: 'auth-storage' }
  )
);
