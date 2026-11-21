"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "./AuthContext";

export function NavBar() {
  const { user, loading, logout } = useAuth();
  const router = useRouter();
  return <header className="topbar"><div className="shell topbar-inner">
    <Link href="/" className="logo">riverbet<span className="logo-dot">.</span></Link>
    <nav aria-label="Main navigation" className="nav-links">
      <Link href="/">Markets</Link>
      {user && <Link href="/portfolio">Portfolio</Link>}
      {user?.role === "ADMIN" && <Link href="/admin">Admin</Link>}
      {!loading && (user ? <button className="text-button" onClick={async () => { try { await logout(); router.push("/login"); } catch { router.push("/login"); } }}>Log out</button>
        : <><Link href="/login">Log in</Link><Link href="/register" className="btn tiny primary">Sign up</Link></>)}
    </nav>
  </div></header>;
}
