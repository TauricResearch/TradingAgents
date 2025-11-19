import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import { Providers } from "./providers";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "TradingAgents - Multi-Agents LLM Financial Trading Framework",
  description: "Web interface for TradingAgents trading analysis framework",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        <nav className="bg-white shadow-sm border-b">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="flex justify-between h-16">
              <div className="flex">
                <Link href="/" className="flex items-center px-2 py-2 text-xl font-bold text-gray-900">
                  TradingAgents
                </Link>
              </div>
              <div className="flex items-center space-x-4">
                <Link href="/" className="px-3 py-2 text-sm font-medium text-gray-700 hover:text-gray-900">
                  Home
                </Link>
                <Link href="/analysis/new" className="px-3 py-2 text-sm font-medium text-gray-700 hover:text-gray-900">
                  New Analysis
                </Link>
                <Link href="/history" className="px-3 py-2 text-sm font-medium text-gray-700 hover:text-gray-900">
                  History
                </Link>
              </div>
            </div>
          </div>
        </nav>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
