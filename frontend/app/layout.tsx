import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Header } from "@/components/layout/Header";
import { Footer } from "@/components/layout/Footer";
import { AnalysisProvider } from "@/context/AnalysisContext";
import { ThemeProvider } from "@/components/theme/ThemeProvider";
import { AuthProvider } from "@/contexts/auth-context";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "TradingAgentsX - 多代理 LLM 金融交易",
  description: "由 AI 驅動的多代理 LLM 金融交易框架",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={inter.className}>
        <ThemeProvider>
          <AuthProvider>
            <AnalysisProvider>
              <div className="flex flex-col min-h-screen gradient-page-bg">
                <Header />
                <main className="flex-1">{children}</main>
                <Footer />
              </div>
            </AnalysisProvider>
          </AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
