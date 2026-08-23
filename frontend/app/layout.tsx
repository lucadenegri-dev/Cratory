import type { Metadata } from "next";
import { DM_Mono } from "next/font/google";
import "./globals.css";
import { ShellSwitch } from "@/components/shell-switch";
import { SetupGate } from "@/components/setup/setup-gate";
import { I18nProvider } from "@/lib/i18n";
import { DockedPlayer } from "@/components/docked-player";
import { PlayerProvider } from "@/lib/player";
import { ExternalLinkBridge } from "@/components/external-link-bridge";

// Font di sistema: DM Mono (peso massimo 500; il grassetto 600 viene
// sintetizzato dal browser). Il nome della variabile resta neutro.
const monoUi = DM_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-mono-ui",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Cratory",
  description: "AI DJ set builder, discovery and library analysis",
};

const NO_FOUC = `(function(){try{var t=localStorage.getItem('cratory-theme');if(t==='paper'){document.documentElement.setAttribute('data-theme','paper');}var l=localStorage.getItem('cratory-lang');if(l==='en'){document.documentElement.lang='en';}}catch(e){}})();`;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="it" className={`h-full ${monoUi.variable}`} suppressHydrationWarning>
      <body className="h-full">
        <script dangerouslySetInnerHTML={{ __html: NO_FOUC }} />
        {/* Nel guscio desktop i link esterni sono inerti: il webview non
            apre nessuna scheda. Il ponte li consegna al browser di sistema,
            una volta per tutta l'app. Nel browser non fa nulla. */}
        <ExternalLinkBridge />
        <I18nProvider>
          <PlayerProvider>
            <SetupGate />
            <ShellSwitch>{children}</ShellSwitch>
            <DockedPlayer />
          </PlayerProvider>
        </I18nProvider>
      </body>
    </html>
  );
}
