import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import Sidebar from "../components/Sidebar";
import JsonLd from "../components/JsonLd";
import { AuthProvider } from "../context/AuthContext";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const viewport: Viewport = {
  themeColor: "#09090b",
  width: "device-width",
  initialScale: 1,
};

export const metadata: Metadata = {
  metadataBase: new URL("https://nimbusagent.vercel.app"),
  title: {
    default: "Nimbus | Autonomous Cloud Software Engineer",
    template: "%s | Nimbus",
  },
  description: "Cloud-native autonomous software engineering agent with zero-trust sandboxing, 3-tier multi-LLM resilient routing, and automated GitHub Pull Request generation.",
  keywords: [
    "Nimbus",
    "Autonomous AI Agent",
    "AI Software Engineer",
    "Cloud Software Engineering",
    "GitHub Agent",
    "Automated Pull Requests",
    "Zero-Trust Sandbox",
    "Gemini 3.6 Flash",
    "Groq",
    "OpenRouter",
    "Anmol Sharma"
  ],
  authors: [{ name: "Anmol Sharma", url: "https://anmolsharma152.vercel.app" }],
  creator: "Anmol Sharma",
  publisher: "Nimbus Agent",
  icons: {
    icon: [
      { url: "/icon.svg", type: "image/svg+xml" },
      { url: "/favicon.svg", type: "image/svg+xml" }
    ],
    apple: [
      { url: "/icon.svg", type: "image/svg+xml" }
    ]
  },
  openGraph: {
    type: "website",
    locale: "en_US",
    url: "https://nimbusagent.vercel.app",
    siteName: "Nimbus",
    title: "Nimbus | Autonomous Cloud Software Engineer",
    description: "Turn natural language prompts into tested git pull requests with zero-trust cloud sandboxing and multi-tier LLM routing.",
    images: [
      {
        url: "/icon.svg",
        width: 512,
        height: 512,
        alt: "Nimbus Autonomous Cloud Agent Logo",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "Nimbus | Autonomous Cloud Software Engineer",
    description: "Cloud-native autonomous software engineer for repository development and PR generation.",
    creator: "@anmolsharma152",
    images: ["/icon.svg"],
  },
  robots: {
    index: true,
    follow: true,
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable}`}>
      <head>
        <JsonLd />
      </head>
      <body style={{ display: "flex", width: "100vw", height: "100vh", overflow: "hidden", margin: 0 }}>
        <AuthProvider>
          <Sidebar />
          <div style={{ flex: 1, height: "100vh", overflowY: "auto", display: "flex", flexDirection: "column", position: "relative" }}>
            {children}
          </div>
        </AuthProvider>
      </body>
    </html>
  );
}
