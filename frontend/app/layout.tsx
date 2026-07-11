import type { Metadata } from "next";
import { IBM_Plex_Mono } from "next/font/google";
import "./globals.css";
import { EditorialShell } from "@/components/editorial-shell";
import { I18nProvider } from "@/lib/i18n";

const ibmPlexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-ibm-plex-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Cratory",
  description: "AI DJ set builder, discovery and library analysis",
};

const NO_FOUC = `(function(){try{var t=localStorage.getItem('cratory-theme');if(t==='paper'){document.documentElement.setAttribute('data-theme','paper');}var l=localStorage.getItem('cratory-lang');if(l==='en'){document.documentElement.lang='en';}}catch(e){}})();`;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="it" className={`h-full ${ibmPlexMono.variable}`} suppressHydrationWarning>
      <body className="h-full">
        <script dangerouslySetInnerHTML={{ __html: NO_FOUC }} />
        <I18nProvider>
          <EditorialShell>{children}</EditorialShell>
        </I18nProvider>
      </body>
    </html>
  );
}
