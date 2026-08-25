import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import Sidebar from "../components/Sidebar";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Nimbus | Autonomous Cloud Software Engineer",
  description: "Cloud-native autonomous software engineering agent for repository development and Pull Request generation.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable}`}>
      <body style={{ display: "flex", width: "100vw", height: "100vh", overflow: "hidden", margin: 0 }}>
        <Sidebar />
        <div style={{ flex: 1, height: "100vh", overflowY: "auto", display: "flex", flexDirection: "column", position: "relative" }}>
          {children}
        </div>
      </body>
    </html>
  );
}
