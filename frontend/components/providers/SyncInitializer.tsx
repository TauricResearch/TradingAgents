/**
 * Sync Initializer - Starts cloud sync retry loop on app startup
 * This client component ensures that failed cloud syncs are automatically retried
 */
"use client";

import { useEffect } from "react";
import { startRetryLoop, stopRetryLoop } from "@/lib/sync-retry";
import { isCloudSyncEnabled } from "@/lib/user-api";

export function SyncInitializer() {
  useEffect(() => {
    // Only start retry loop if user is authenticated
    if (isCloudSyncEnabled()) {
      console.log("🔄 Starting cloud sync retry service");
      startRetryLoop();

      // Cleanup on unmount
      return () => {
        console.log("⏹️  Stopping cloud sync retry service");
        stopRetryLoop();
      };
    }
  }, []);

  return null; // This component doesn't render anything
}
