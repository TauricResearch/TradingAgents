import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Sidebar } from "@/components/sidebar";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "TradingAgents — Multi-Agent LLM Trading Dashboard",
  description: "Web dashboard for TradingAgents multi-agent LLM financial trading framework",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className={inter.className}>
        <div className="flex min-h-screen">
          <Sidebar />
          <main className="flex-1 pl-64">
            <div className="min-h-screen p-6">{children}</div>
          </main>
        </div>
      </body>
    </html>
  );
}
