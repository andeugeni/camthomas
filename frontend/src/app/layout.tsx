import type { Metadata } from "next";
import "@/styles/globals.css";
import AboutButton from "@/components/AboutButton";

export const metadata: Metadata = {
  title: "CAMTHOMAS · Career Arc Model",
  description: "Fantasy basketball projections powered by CAMTHOMAS",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        {children}
        <AboutButton />
      </body>
    </html>
  );
}