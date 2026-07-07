import type { Metadata } from "next";
import { IBM_Plex_Mono } from "next/font/google";
import "./globals.css";
import { EditorialShell } from "@/components/editorial-shell";

const ibmPlexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-ibm-plex-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Sortory",
  description: "Organizza i file musicali e preparali per Rekordbox",
};

const NO_FOUC = `(function(){try{var t=localStorage.getItem('djorganizer-theme');if(t==='paper'){document.documentElement.setAttribute('data-theme','paper');}}catch(e){}})();`;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="it" className={`h-full ${ibmPlexMono.variable}`} suppressHydrationWarning>
      <body className="h-full">
        <script dangerouslySetInnerHTML={{ __html: NO_FOUC }} />
        <EditorialShell>{children}</EditorialShell>
      </body>
    </html>
  );
}
