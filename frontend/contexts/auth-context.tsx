/**
 * Authentication Context
 * Manages user login state and provides auth utilities
 */
"use client";

import React, { createContext, useContext, useState, useEffect, useCallback, ReactNode } from "react";

// User interface
export interface User {
  id: string;
  email: string;
  name: string | null;
  avatar_url: string | null;
}

// Auth context interface
interface AuthContextType {
  user: User | null;
  token: string | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: () => void;
  logout: () => void;
  setAuthFromCallback: (token: string) => void;
}

// Create context
const AuthContext = createContext<AuthContextType | undefined>(undefined);

// Token storage key
const TOKEN_KEY = "tradingagents_auth_token";

// Google OAuth client ID from environment
const GOOGLE_CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || "";

// Backend URL
const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL || "";

/**
 * Auth Provider Component
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Parse JWT token to get user info
  const parseToken = useCallback((token: string): User | null => {
    try {
      const payload = JSON.parse(atob(token.split(".")[1]));
      return {
        id: payload.sub,
        email: payload.email,
        name: payload.name,
        avatar_url: payload.avatar_url,
      };
    } catch {
      return null;
    }
  }, []);

  // Check if token is expired
  const isTokenExpired = useCallback((token: string): boolean => {
    try {
      const payload = JSON.parse(atob(token.split(".")[1]));
      const exp = payload.exp * 1000; // Convert to milliseconds
      return Date.now() > exp;
    } catch {
      return true;
    }
  }, []);

  // Initialize auth state from localStorage
  useEffect(() => {
    const initAuth = () => {
      if (typeof window === "undefined") {
        setIsLoading(false);
        return;
      }

      const storedToken = localStorage.getItem(TOKEN_KEY);
      
      if (storedToken && !isTokenExpired(storedToken)) {
        const userData = parseToken(storedToken);
        if (userData) {
          setToken(storedToken);
          setUser(userData);
        } else {
          localStorage.removeItem(TOKEN_KEY);
        }
      } else if (storedToken) {
        // Token expired, remove it
        localStorage.removeItem(TOKEN_KEY);
      }
      
      setIsLoading(false);
    };

    initAuth();
  }, [parseToken, isTokenExpired]);

  // Login - redirect to Google OAuth
  const login = useCallback(() => {
    if (!GOOGLE_CLIENT_ID) {
      console.error("Google Client ID not configured");
      alert("Google 登入尚未設定。請聯繫管理員。");
      return;
    }

    // Build Google OAuth URL
    const redirectUri = `${window.location.origin}/api/auth/callback/google`;
    const scope = "openid email profile";
    
    const params = new URLSearchParams({
      client_id: GOOGLE_CLIENT_ID,
      redirect_uri: redirectUri,
      response_type: "code",
      scope: scope,
      access_type: "offline",
      prompt: "consent",
    });

    window.location.href = `https://accounts.google.com/o/oauth2/v2/auth?${params.toString()}`;
  }, []);

  // Logout
  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    setToken(null);
    setUser(null);
  }, []);

  // Set auth from callback (after OAuth redirect)
  const setAuthFromCallback = useCallback((newToken: string) => {
    const userData = parseToken(newToken);
    if (userData) {
      localStorage.setItem(TOKEN_KEY, newToken);
      setToken(newToken);
      setUser(userData);
    }
  }, [parseToken]);

  const value: AuthContextType = {
    user,
    token,
    isLoading,
    isAuthenticated: !!user,
    login,
    logout,
    setAuthFromCallback,
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

/**
 * Hook to use auth context
 */
export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}

/**
 * Get auth token for API requests
 */
export function getAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

/**
 * Get auth headers for API requests
 */
export function getAuthHeaders(): Record<string, string> {
  const token = getAuthToken();
  if (token) {
    return { Authorization: `Bearer ${token}` };
  }
  return {};
}
