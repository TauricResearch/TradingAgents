/**
 * Header component
 */
"use client";

import Link from "next/link";
import { ThemeToggle } from "@/components/theme/ThemeToggle";
import { ApiSettingsDialog } from "@/components/settings/ApiSettingsDialog";
import { LoginButton } from "@/components/auth/login-button";

export function Header() {
  return (
    <header className="border-b bg-gradient-to-r from-blue-500 to-pink-500 dark:from-blue-600 dark:to-purple-600 text-white">
      <div className="container mx-auto px-4 py-6">
        <div className="flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2">
            <div className="text-3xl font-bold">TradingAgentsX</div>
            <div className="hidden md:block text-sm font-light opacity-90">
              多代理 LLM 金融交易框架
            </div>
          </Link>
          <nav className="flex gap-6 items-center">
            <Link
              href="/"
              className="hover:opacity-80 transition-opacity font-medium"
            >
              首頁
            </Link>
            <Link
              href="/analysis"
              className="hover:opacity-80 transition-opacity font-medium"
            >
              分析
            </Link>
            <Link
              href="/history"
              className="hover:opacity-80 transition-opacity font-medium"
            >
              歷史報告
            </Link>
            <ApiSettingsDialog />
            <ThemeToggle />
            <LoginButton />
          </nav>
        </div>
      </div>
    </header>
  );
}
