/**
 * Authentication Context
 * Manages user login state and provides auth utilities
 */
"use client";

import React, { createContext, useContext, useState, useEffect, useCallback, ReactNode } from "react";
import { clearApiSettings, saveApiSettingsAsync } from "@/lib/storage";
import { clearAllReports, saveReport } from "@/lib/reports-db";
import { getCloudSettings, getCloudReports } from "@/lib/user-api";

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
  logout: () => Promise<void>;
  setAuthFromCallback: (token: string) => Promise<void>;
}

// Create context
const AuthContext = createContext<AuthContextType | undefined>(undefined);

// Token storage key
const TOKEN_KEY = "tradingagents_auth_token";

/**
 * Auth Provider Component
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [googleClientId, setGoogleClientId] = useState<string>("");

  // Fetch Google Client ID from API (runtime)
  useEffect(() => {
    fetch("/api/config")
      .then(res => res.json())
      .then(data => {
        setGoogleClientId(data.googleClientId || "");
      })
      .catch(err => {
        console.error("Failed to fetch config:", err);
      });
  }, []);

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

  // Auto-clear local data when unauthenticated user leaves the page
  // Only applies in production environment (not localhost)
  useEffect(() => {
    if (typeof window === "undefined") return;

    // Check if running in local development mode
    const isLocalDevelopment = 
      window.location.hostname === "localhost" || 
      window.location.hostname === "127.0.0.1" ||
      window.location.hostname.startsWith("192.168.") ||
      window.location.hostname.startsWith("10.");
    
    // Skip auto-clear in local development to preserve data
    if (isLocalDevelopment) {
      console.log("Local development mode: data will be preserved on page leave");
      return;
    }

    const handleBeforeUnload = () => {
      // Only clear data if user is not authenticated (production only)
      const currentToken = localStorage.getItem(TOKEN_KEY);
      if (!currentToken) {
        // Clear API settings (synchronous)
        clearApiSettings();
        
        // Clear reports - use synchronous approach for beforeunload
        // IndexedDB operations are async, but we can at least attempt it
        clearAllReports().catch(() => {
          // Ignore errors during unload
        });
        
        console.log("Cleared local data for unauthenticated user on page leave");
      }
    };

    // Use both beforeunload and pagehide for better browser compatibility
    window.addEventListener("beforeunload", handleBeforeUnload);
    window.addEventListener("pagehide", handleBeforeUnload);

    return () => {
      window.removeEventListener("beforeunload", handleBeforeUnload);
      window.removeEventListener("pagehide", handleBeforeUnload);
    };
  }, []); // No dependencies - we check localStorage directly

  // Login - redirect to Google OAuth
  const login = useCallback(() => {
    if (!googleClientId) {
      console.error("Google Client ID not configured");
      alert("Google 登入尚未設定。請聯繫管理員。");
      return;
    }

    // Build Google OAuth URL
    const redirectUri = `${window.location.origin}/api/auth/callback/google`;
    const scope = "openid email profile";
    
    const params = new URLSearchParams({
      client_id: googleClientId,
      redirect_uri: redirectUri,
      response_type: "code",
      scope: scope,
      access_type: "offline",
      prompt: "consent",
    });

    window.location.href = `https://accounts.google.com/o/oauth2/v2/auth?${params.toString()}`;
  }, [googleClientId]);

  // Logout - clear auth and all local data
  const logout = useCallback(async () => {
    // Clear auth token
    localStorage.removeItem(TOKEN_KEY);
    setToken(null);
    setUser(null);
    
    // Clear all local data
    clearApiSettings();
    await clearAllReports();
    
    console.log("Logged out and cleared all local data");
  }, []);

  // Restore cloud data to local storage
  const restoreCloudData = useCallback(async (authToken: string) => {
    try {
      // Temporarily set token for API calls
      localStorage.setItem(TOKEN_KEY, authToken);
      
      // Fetch and restore cloud settings
      const cloudSettings = await getCloudSettings();
      if (cloudSettings) {
        await saveApiSettingsAsync(cloudSettings);
        console.log("Restored API settings from cloud");
      }
      
      // Fetch and restore cloud reports
      const cloudReports = await getCloudReports();
      if (cloudReports && cloudReports.length > 0) {
        // Clear existing local reports first
        await clearAllReports();
        
        // Save each cloud report to local IndexedDB
        for (const report of cloudReports) {
          await saveReport(
            report.ticker,
            report.market_type,
            report.analysis_date,
            report.result,
            (report as any).task_id,
            report.language  // Preserve language from cloud
          );
        }
        console.log(`Restored ${cloudReports.length} reports from cloud`);
      }
    } catch (error) {
      console.error("Failed to restore cloud data:", error);
    }
  }, []);

  // Set auth from callback (after OAuth redirect)
  const setAuthFromCallback = useCallback(async (newToken: string) => {
    const userData = parseToken(newToken);
    if (userData) {
      // First restore cloud data, then set the auth state
      await restoreCloudData(newToken);
      
      localStorage.setItem(TOKEN_KEY, newToken);
      setToken(newToken);
      setUser(userData);
      
      console.log("Login complete, cloud data restored");
    }
  }, [parseToken, restoreCloudData]);

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
