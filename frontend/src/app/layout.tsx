import type { Metadata } from "next";
import "./globals.css";
import Sidebar from "@/components/Sidebar";

export const metadata: Metadata = {
  title: "TAPIOD - Token Optimization",
  description: "Elite AI routing, token optimization, and cost saving tool",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`h-full overflow-hidden antialiased dark font-sans`}
    >
      <body className="h-full flex overflow-hidden">
        <Sidebar />
        <main className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden p-6 sm:p-10 relative">
          <div className="max-w-7xl mx-auto h-full">
            {children}
          </div>
        </main>
      </body>
    </html>
  );
}
