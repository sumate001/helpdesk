import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import { apiError } from "../api";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    try {
      await login(username, password);
      navigate("/");
    } catch (err) {
      setError(apiError(err, "เข้าสู่ระบบไม่สำเร็จ"));
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <form
        onSubmit={handleSubmit}
        className="glass-strong p-8 rounded-2xl shadow-[0_0_60px_rgba(129,140,248,0.15)] w-full max-w-sm space-y-4 animate-fadein"
      >
        <div className="text-center space-y-1">
          <h1 className="text-2xl font-bold text-glow tracking-wide">IT TICKET</h1>
          <p className="text-xs text-slate-500">Dashboard เข้าสู่ระบบ</p>
        </div>
        {error && (
          <div className="bg-red-400/10 text-red-300 ring-1 ring-red-400/30 text-sm p-2 rounded-lg">
            {error}
          </div>
        )}
        <input
          className="w-full bg-white/5 ring-1 ring-white/10 rounded-lg p-2.5 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-400/70 focus:shadow-[0_0_16px_rgba(129,140,248,0.3)] transition-shadow"
          placeholder="Username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
        />
        <input
          type="password"
          className="w-full bg-white/5 ring-1 ring-white/10 rounded-lg p-2.5 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-400/70 focus:shadow-[0_0_16px_rgba(129,140,248,0.3)] transition-shadow"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <button
          type="submit"
          className="w-full bg-gradient-to-br from-indigo-500 to-fuchsia-500 text-white py-2.5 rounded-lg font-medium shadow-[0_0_20px_rgba(129,140,248,0.4)] hover:shadow-[0_0_28px_rgba(129,140,248,0.6)] hover:-translate-y-0.5 transition-all duration-200"
        >
          เข้าสู่ระบบ
        </button>
      </form>
    </div>
  );
}
