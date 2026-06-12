import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Nexus — The knowledge layer for company AI",
  description:
    "Connect Google Drive, Notion, Slack, ClickUp, GitHub, Linear, Calendar, and Confluence. Query everything through one permission-aware API with fresh, cited answers.",
  openGraph: {
    title: "Nexus — Connect everything. Know everything.",
    description: "The MCP-native, permission-aware, self-hostable enterprise RAG platform.",
    type: "website"
  }
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <head>
        <link href="https://fonts.googleapis.com" rel="preconnect" />
        <link crossOrigin="" href="https://fonts.gstatic.com" rel="preconnect" />
        <link
          href="https://fonts.googleapis.com/css2?family=Geist:wght@300;400;500;600;700&family=Geist+Mono:wght@300;400;500&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
