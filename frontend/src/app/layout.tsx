import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";

const instrumentSans = localFont({
  src: [
    {
      path: "../../public/fonts/instrument-sans-latin.woff2",
      style: "normal",
    },
  ],
  variable: "--font-instrument-sans",
  display: "swap",
});

const jetbrainsMono = localFont({
  src: [
    {
      path: "../../public/fonts/jetbrains-mono-latin.woff2",
      style: "normal",
    },
  ],
  variable: "--font-jetbrains-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Kundali | कुण्डली",
  description: "Transparent Vedic Astrology, Computed Then Interpreted",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${instrumentSans.variable} ${jetbrainsMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
