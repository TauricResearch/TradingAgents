/**
 * Header component with mobile-responsive design and i18n support
 */
"use client";

import { useState } from "react";
import Link from "next/link";
import { Menu, X } from "lucide-react";
import { ThemeToggle } from "@/components/theme/ThemeToggle";
import { ApiSettingsDialog } from "@/components/settings/ApiSettingsDialog";
import { LanguageSwitcher } from "@/components/settings/LanguageSwitcher";
import { LoginButton } from "@/components/auth/login-button";
import { Button } from "@/components/ui/button";
import { useLanguage } from "@/contexts/LanguageContext";
import { usePathname } from "next/navigation";

export function Header() {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const { t } = useLanguage();
  const pathname = usePathname();

  if (pathname === "/history/chat") return null;

  return (
    <header className="border-b bg-gradient-to-r from-blue-500 to-pink-500 dark:from-blue-600 dark:to-purple-600 text-white pwa-safe-header">
      <div className="container mx-auto px-4 py-4 md:py-6">
        <div className="flex items-center justify-between">
          {/* Logo */}
          <Link href="/" className="flex items-center gap-2 shrink-0">
            <div className="text-xl md:text-3xl font-bold">TradingAgentsX</div>
            <div className="hidden lg:block text-sm font-light opacity-90">
              {t.nav.tagline}
            </div>
          </Link>

          {/* Desktop Navigation */}
          <nav className="hidden md:flex gap-4 lg:gap-6 items-center">
            <Link
              href="/"
              className="hover:opacity-80 transition-opacity font-medium text-sm lg:text-base"
            >
              {t.nav.home}
            </Link>
            <Link
              href="/analysis"
              className="hover:opacity-80 transition-opacity font-medium text-sm lg:text-base"
            >
              {t.nav.analysis}
            </Link>
            <Link
              href="/history"
              className="hover:opacity-80 transition-opacity font-medium text-sm lg:text-base"
            >
              {t.nav.history}
            </Link>
            <ApiSettingsDialog />
            <LanguageSwitcher />
            <ThemeToggle />
            <LoginButton />
          </nav>

          {/* Mobile Menu Button */}
          <div className="flex md:hidden items-center gap-2">
            <LanguageSwitcher />
            <ThemeToggle />
            <Button
              variant="ghost"
              size="icon"
              className="text-white hover:bg-white/20"
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            >
              {mobileMenuOpen ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
            </Button>
          </div>
        </div>

        {/* Mobile Navigation */}
        {mobileMenuOpen && (
          <nav className="md:hidden mt-4 pt-4 border-t border-white/20 space-y-3">
            <Link
              href="/"
              className="block py-2 hover:opacity-80 transition-opacity font-medium"
              onClick={() => setMobileMenuOpen(false)}
            >
              {t.nav.home}
            </Link>
            <Link
              href="/analysis"
              className="block py-2 hover:opacity-80 transition-opacity font-medium"
              onClick={() => setMobileMenuOpen(false)}
            >
              {t.nav.analysis}
            </Link>
            <Link
              href="/history"
              className="block py-2 hover:opacity-80 transition-opacity font-medium"
              onClick={() => setMobileMenuOpen(false)}
            >
              {t.nav.history}
            </Link>
            <div className="flex items-center gap-3 pt-2">
              <ApiSettingsDialog />
              <LoginButton />
            </div>
          </nav>
        )}
      </div>
    </header>
  );
}
