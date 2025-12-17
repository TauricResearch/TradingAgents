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
  icons: {
    icon: [
      { url: "/favicon-v5.ico?t=20241217", sizes: "32x32" },
      { url: "/icon-192-v5.png?t=20241217", sizes: "192x192", type: "image/png" },
      { url: "/icon-512-v5.png?t=20241217", sizes: "512x512", type: "image/png" },
      { url: "/icon-v5.png?t=20241217", sizes: "1024x1024", type: "image/png" },
    ],
    apple: [
      { url: "/apple-touch-icon-v5.png?t=20241217", sizes: "180x180", type: "image/png" },
    ],
    shortcut: "/favicon-v5.ico?t=20241217",
  },
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "TAgentsX",
  },
  openGraph: {
    title: "TradingAgentsX - 多代理 LLM 金融交易",
    description: "由 AI 驅動的多代理 LLM 金融交易框架",
    siteName: "TradingAgentsX",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
        <link rel="manifest" href="/manifest.json?v=20241217" />
        <meta name="theme-color" content="#6B21A8" />
        <meta name="apple-mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
        <meta name="apple-mobile-web-app-title" content="TAgentsX" />
        {/* Timestamp forces iOS Safari to reload new icons */}
        <link rel="apple-touch-icon" href="/apple-touch-icon-v5.png?t=20241217" />
        <link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon-v5.png?t=20241217" />
        <link rel="apple-touch-icon" sizes="152x152" href="/apple-touch-icon-v5.png?t=20241217" />
        <link rel="apple-touch-icon" sizes="120x120" href="/apple-touch-icon-v5.png?t=20241217" />
        <link rel="icon" type="image/png" sizes="32x32" href="/favicon-v5.png?t=20241217" />
        <link rel="icon" type="image/png" sizes="192x192" href="/icon-192-v5.png?t=20241217" />
        <link rel="icon" type="image/png" sizes="512x512" href="/icon-512-v5.png?t=20241217" />
      </head>
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
