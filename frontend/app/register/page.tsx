"use client";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { post } from "@/lib/api";
import { useAuth } from "@/components/AuthContext";

export default function Register() {
  const [email,setEmail]=useState(""); const [password,setPassword]=useState("");
  const [error,setError]=useState(""); const [working,setWorking]=useState(false);
  const {refresh}=useAuth(); const router=useRouter();
  async function submit(e:FormEvent) {
    e.preventDefault();setError("");setWorking(true);
    try{await post("/api/auth/register",{email,password});await refresh();router.push("/");}
    catch(err){setError(err instanceof Error?err.message:"Could not register");}
    finally{setWorking(false);}
  }
  return <main className="shell"><section className="panel auth-page">
    <div className="eyebrow">Join a forecasting team</div><h1>Create an account</h1>
    <p className="muted">Every new member receives a fixed play-credit grant. No real-money transactions.</p>
    <form onSubmit={submit}>
      <div className="field"><label htmlFor="email">Email</label><input id="email" type="email" autoComplete="email" required value={email} onChange={e=>setEmail(e.target.value)}/></div>
      <div className="field"><label htmlFor="password">Password (12+ characters)</label><input id="password" type="password" minLength={12} autoComplete="new-password" required value={password} onChange={e=>setPassword(e.target.value)}/></div>
      {error&&<p role="alert" className="notice error">{error}</p>}
      <button className="btn primary full" disabled={working}>{working?"Creating account...":"Create account"}</button>
    </form><p className="muted" style={{marginTop:16}}>Already a member? <Link href="/login" style={{color:"var(--aqua)"}}>Log in</Link></p>
  </section></main>;
}
