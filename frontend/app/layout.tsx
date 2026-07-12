import type { Metadata } from "next";
import { DM_Mono } from "next/font/google";
import "./globals.css";
import { EditorialShell } from "@/components/editorial-shell";
import { I18nProvider } from "@/lib/i18n";

// Font di sistema: DM Mono (peso massimo 500; il grassetto 600 viene
// sintetizzato dal browser). Il nome della variabile resta neutro.
const monoUi = DM_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-mono-ui",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Sortory",
  description: "Organizza i file musicali e preparali per Rekordbox",
};

const NO_FOUC = `(function(){try{var t=localStorage.getItem('djorganizer-theme');if(t==='paper'){document.documentElement.setAttribute('data-theme','paper');}var l=localStorage.getItem('sortory-lang');if(l==='it'){document.documentElement.lang='it';}}catch(e){}})();`;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`h-full ${monoUi.variable}`} suppressHydrationWarning>
      <body className="h-full">
        <script dangerouslySetInnerHTML={{ __html: NO_FOUC }} />
        <I18nProvider>
          <EditorialShell>{children}</EditorialShell>
        </I18nProvider>
      </body>
    </html>
  );
}
