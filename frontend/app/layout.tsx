import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/components/AuthContext";
import { NavBar } from "@/components/NavBar";

export const metadata: Metadata = {
  title: "riverbet | Team prediction markets",
  description: "Forecast delivery of Jira work items with nonredeemable play credits."
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><AuthProvider><NavBar />{children}
    <footer className="footer"><div className="shell">riverbet · Team forecasting with play credits only · Market prices are not calibrated forecasts</div></footer>
  </AuthProvider></body></html>;
}
