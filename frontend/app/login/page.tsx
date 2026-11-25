"use client";
import { FormEvent, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { post } from "@/lib/api";
import { useAuth } from "@/components/AuthContext";

export default function Login() {
  const [email,setEmail]=useState(""); const [password,setPassword]=useState("");
  const [error,setError]=useState(""); const [working,setWorking]=useState(false);
  const {refresh}=useAuth(); const router=useRouter();
  async function submit(event:FormEvent) {
    event.preventDefault();setError("");setWorking(true);
    try { await post("/api/auth/login", {email,password}); await refresh();router.push("/"); }
    catch(err){setError(err instanceof Error?err.message:"Login failed");}
    finally{setWorking(false);}
  }
  return <main className="shell"><section className="panel auth-page">
    <div className="eyebrow">Welcome back</div><h1>Log in</h1>
    <p className="muted">Use your Workbet account. Jira credentials are managed separately by the backend.</p>
    <form onSubmit={submit}>
      <div className="field"><label htmlFor="email">Email</label><input id="email" type="email" required value={email} onChange={e=>setEmail(e.target.value)} autoComplete="email"/></div>
      <div className="field"><label htmlFor="password">Password</label><input id="password" type="password" required value={password} onChange={e=>setPassword(e.target.value)} autoComplete="current-password"/></div>
      {error&&<p role="alert" className="notice error">{error}</p>}
      <button className="btn primary full" disabled={working}>{working?"Logging in...":"Log in"}</button>
    </form><p style={{marginTop:16}} className="muted">No account? <Link href="/register" style={{color:"var(--aqua)"}}>Sign up</Link></p>
  </section></main>;
}
