import type { Metadata } from "next";
import { DM_Sans, IBM_Plex_Mono, Manrope } from "next/font/google";

import { ToastProvider } from "@/components/Toast";
import { LanguageProvider } from "@/lib/i18n";
import "./globals.css";

/*
 * DM Sans carries the interface and Manrope the headings, as the StatFlow
 * design system specifies. They are close enough in x-height that the pairing
 * reads as one family at body sizes, and Manrope's tighter tracking is what
 * makes the large numerals in a metric card look deliberate rather than large.
 */
const dmSans = DM_Sans({
  subsets: ["latin"],
  variable: "--font-dm-sans",
  display: "swap",
});

const manrope = Manrope({
  subsets: ["latin"],
  weight: ["600", "700"],
  variable: "--font-manrope",
  display: "swap",
});

// Kept for tabular figures: a column of numbers must not jitter between rows.
const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-ibm-plex-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Data Analysis Platform",
  description:
    "Upload CSV/Excel data, clean it, run statistics, build charts and export reports no code required.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      className={`${dmSans.variable} ${manrope.variable} ${plexMono.variable}`}
    >
      <body className="font-sans antialiased">
        <LanguageProvider>
          <ToastProvider>{children}</ToastProvider>
        </LanguageProvider>
      </body>
    </html>
  );
}
