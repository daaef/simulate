import "./globals.css";
import type { ReactNode } from "react";

export const metadata = {
  title: "Fainzy Simulator",
  description: "Web control plane for simulator runs"
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

