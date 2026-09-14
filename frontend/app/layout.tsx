import type { Metadata, Viewport } from "next";
import { IBM_Plex_Sans_Arabic } from "next/font/google";
import "react-simple-keyboard/build/css/index.css";
import "./globals.css";
import KioskLayout from "./kiosk-layout";

const plex = IBM_Plex_Sans_Arabic({
  subsets: ["arabic", "latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-plex-arabic",
  display: "swap",
});

export const metadata: Metadata = {
  title: "WathiqaDoc — وثيقة دوك",
  description: "Borne citoyenne : documents requis pour vos démarches administratives.",
  manifest: "/manifest.webmanifest",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1, maximumScale: 1, userScalable: false, themeColor: "#0D0D20" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr" className={plex.variable}>
      <body className="font-sans antialiased">
        <KioskLayout>{children}</KioskLayout>
      </body>
    </html>
  );
}
