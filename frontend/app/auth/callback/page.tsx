/**
 * OAuth Callback Handler Page
 * Handles the redirect from Google OAuth and exchanges code for token
 */
"use client";

import { useEffect, useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/contexts/auth-context";

function AuthCallbackContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { setAuthFromCallback } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const [isProcessing, setIsProcessing] = useState(true);

  useEffect(() => {
    const handleCallback = async () => {
      // Check if we have a token directly (backend-handled flow)
      const token = searchParams.get("token");
      if (token) {
        setAuthFromCallback(token);
        router.replace("/");
        return;
      }

      // Check if we have a code (frontend-handled flow)
      const code = searchParams.get("code");
      if (!code) {
        const errorParam = searchParams.get("error");
        setError(errorParam || "No authorization code received");
        setIsProcessing(false);
        return;
      }

      try {
        // Exchange code for token via backend
        const redirectUri = `${window.location.origin}/api/auth/callback/google`;
        
        const response = await fetch("/api/auth/google/token", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            code,
            redirect_uri: redirectUri,
          }),
        });

        if (!response.ok) {
          const errorData = await response.json();
          // Handle various error response formats
          const errorMessage = 
            typeof errorData.detail === 'string' ? errorData.detail :
            typeof errorData.error === 'string' ? errorData.error :
            errorData.message || 
            JSON.stringify(errorData) || 
            "Failed to exchange token";
          throw new Error(errorMessage);
        }

        const data = await response.json();
        setAuthFromCallback(data.access_token);
        router.replace("/");
      } catch (err: any) {
        console.error("Auth callback error:", err);
        const msg = err.message || "Authentication failed";
        setError(typeof msg === 'string' ? msg : "Authentication failed");
        setIsProcessing(false);
      }
    };

    handleCallback();
  }, [searchParams, setAuthFromCallback, router]);

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center p-8 max-w-md">
          <div className="text-red-500 text-5xl mb-4">⚠️</div>
          <h1 className="text-2xl font-bold mb-2">登入失敗</h1>
          <p className="text-muted-foreground mb-4">{error}</p>
          <button
            onClick={() => router.replace("/")}
            className="px-4 py-2 bg-primary text-primary-foreground rounded-md hover:opacity-90"
          >
            返回首頁
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="text-center">
        <div className="w-12 h-12 border-4 border-primary border-t-transparent rounded-full animate-spin mx-auto mb-4" />
        <p className="text-lg font-medium">正在登入...</p>
        <p className="text-sm text-muted-foreground">請稍候</p>
      </div>
    </div>
  );
}

function LoadingFallback() {
  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="text-center">
        <div className="w-12 h-12 border-4 border-primary border-t-transparent rounded-full animate-spin mx-auto mb-4" />
        <p className="text-lg font-medium">載入中...</p>
      </div>
    </div>
  );
}

export default function AuthCallbackPage() {
  return (
    <Suspense fallback={<LoadingFallback />}>
      <AuthCallbackContent />
    </Suspense>
  );
}

