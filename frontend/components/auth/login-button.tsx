/**
 * Google Login Button Component
 */
"use client";

import React from "react";
import { useAuth } from "@/contexts/auth-context";
import { useLanguage } from "@/contexts/LanguageContext";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { LogOut, User, Cloud, CloudOff } from "lucide-react";

// Google Icon SVG
function GoogleIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" width="18" height="18">
      <path
        fill="#4285F4"
        d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
      />
      <path
        fill="#34A853"
        d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
      />
      <path
        fill="#FBBC05"
        d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
      />
      <path
        fill="#EA4335"
        d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
      />
    </svg>
  );
}

export function LoginButton() {
  const { user, isLoading, isAuthenticated, login, logout } = useAuth();
  const { t } = useLanguage();
  const [loggingOut, setLoggingOut] = React.useState(false);

  const handleLogout = async () => {
    setLoggingOut(true);
    try {
      await logout();
    } finally {
      setLoggingOut(false);
    }
  };

  if (isLoading || loggingOut) {
    return (
      <Button variant="outline" size="sm" disabled>
        <div className="w-4 h-4 border-2 border-gray-300 border-t-gray-600 rounded-full animate-spin" />
        {loggingOut && <span className="ml-2 hidden sm:inline">{t.auth.loggingOut}</span>}
      </Button>
    );
  }

  if (isAuthenticated && user) {
    return (
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button 
            variant="ghost" 
            size="sm" 
            className="gap-2 bg-white/20 hover:bg-white/30 text-white border-white/30 border"
          >
            {user.avatar_url ? (
              <img
                src={user.avatar_url}
                alt={user.name || "User"}
                className="w-5 h-5 rounded-full"
              />
            ) : (
              <User className="w-4 h-4" />
            )}
            <span className="hidden sm:inline max-w-[100px] truncate">
              {user.name || user.email}
            </span>
            <Cloud className="w-3 h-3 text-green-300" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-56">
          <div className="px-2 py-1.5">
            <p className="text-sm font-medium">{user.name}</p>
            <p className="text-xs text-muted-foreground">{user.email}</p>
          </div>
          <DropdownMenuSeparator />
          <DropdownMenuItem className="text-green-600">
            <Cloud className="w-4 h-4 mr-2" />
            {t.auth.cloudSyncEnabled}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={handleLogout} className="text-red-600">
            <LogOut className="w-4 h-4 mr-2" />
            {t.auth.logout}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    );
  }

  return (
    <Button 
      variant="ghost" 
      size="sm" 
      onClick={login} 
      className="gap-2 bg-white/20 hover:bg-white/30 text-white border-white/30 border"
    >
      <GoogleIcon />
      <span className="hidden sm:inline">{t.auth.login}</span>
      <CloudOff className="w-3 h-3 text-white/60 sm:hidden" />
    </Button>
  );
}

/**
 * Full-width login prompt for pages that benefit from login
 */
export function LoginPrompt() {
  const { login, isAuthenticated } = useAuth();
  const { t } = useLanguage();

  if (isAuthenticated) return null;

  return (
    <div className="bg-gradient-to-r from-blue-50 to-purple-50 dark:from-blue-950/30 dark:to-purple-950/30 border border-blue-200 dark:border-blue-800 rounded-lg p-4 mb-4">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <CloudOff className="w-5 h-5 text-gray-400" />
          <div>
            <p className="text-sm font-medium">{t.auth.usingLocalStorage}</p>
            <p className="text-xs text-muted-foreground">
              {t.auth.loginToSync}
            </p>
          </div>
        </div>
        <Button variant="outline" size="sm" onClick={login} className="gap-2 shrink-0">
          <GoogleIcon />
          {t.auth.loginSync}
        </Button>
      </div>
    </div>
  );
}
