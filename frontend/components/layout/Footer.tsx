/**
 * Footer component
 */
"use client";

import { usePathname } from "next/navigation";

export function Footer() {
  const pathname = usePathname();
  
  if (pathname === "/history/chat") return null;

  return (
    <footer className="border-t bg-gradient-to-r from-blue-50/50 via-purple-50/50 to-pink-50/50 dark:from-gray-900/50 dark:via-purple-900/20 dark:to-blue-900/20 backdrop-blur-sm">
      <div className="container mx-auto px-4 py-6">
        <div className="flex items-center justify-center">
          <div className="text-sm text-gray-600 dark:text-gray-400">
            © 2025 TradingAgentsX. All rights reserved.
          </div>
        </div>
      </div>
    </footer>
  );
}
