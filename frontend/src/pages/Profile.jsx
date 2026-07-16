import { useEffect, useState } from "react";
import api, { apiError } from "../api";

export default function Profile() {
  const [form, setForm] = useState(null);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .get("/auth/me")
      .then(({ data }) =>
        setForm({
          username: data.username,
          role: data.role,
          email: data.email,
          display_name: data.display_name || "",
          line_user_id: data.line_user_id || "",
          itamtv_token: data.itamtv_token || "",
          itamtv_emp_code: data.itamtv_emp_code || "",
          password: "",
        })
      )
      .catch((err) => setError(apiError(err, "โหลดโปรไฟล์ไม่ได้")));
  }, []);

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError("");
    setMsg(null);
    try {
      const payload = {
        email: form.email,
        display_name: form.display_name || null,
        line_user_id: form.line_user_id || null,
        itamtv_token: form.itamtv_token || null,
        itamtv_emp_code: form.itamtv_emp_code || null,
      };
      if (form.password) payload.password = form.password;
      await api.patch("/auth/me", payload);
      setMsg("บันทึกโปรไฟล์แล้ว");
      setForm({ ...form, password: "" });
    } catch (err) {
      setError(apiError(err, "บันทึกไม่สำเร็จ"));
    } finally {
      setSaving(false);
    }
  };

  if (!form) return <p className="text-slate-500">กำลังโหลด...</p>;

  const input =
    "w-full px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-sm text-slate-100 focus:outline-none focus:border-indigo-400";

  return (
    <div className="max-w-xl space-y-6">
      <h1 className="text-xl font-bold text-glow">โปรไฟล์ของฉัน</h1>

      <form onSubmit={submit} className="glass rounded-xl p-4 space-y-3">
        <div className="text-sm text-slate-400">
          บัญชี: <span className="text-slate-200">@{form.username}</span>
          <span className="ml-2 text-xs px-2 py-0.5 rounded bg-white/5">{form.role}</span>
        </div>

        <div>
          <label className="text-xs text-slate-400">ชื่อที่แสดง</label>
          <input
            className={input}
            value={form.display_name}
            onChange={(e) => setForm({ ...form, display_name: e.target.value })}
          />
        </div>
        <div>
          <label className="text-xs text-slate-400">Email</label>
          <input
            className={input}
            type="email"
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
            required
          />
        </div>
        <div>
          <label className="text-xs text-slate-400">รหัสผ่านใหม่ (เว้นว่างถ้าไม่เปลี่ยน)</label>
          <input
            className={input}
            type="password"
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
          />
        </div>

        <div className="pt-2 border-t border-white/10">
          <p className="text-xs text-slate-400 mb-2">
            สำหรับช่าง — ผูกบัญชีเพื่อรับ/ปิดเคสผ่าน LINE
          </p>
          <label className="text-xs text-slate-400">LINE userId</label>
          <input
            className={input}
            value={form.line_user_id}
            placeholder="U xxxxxxxxxxxxxxxx"
            onChange={(e) => setForm({ ...form, line_user_id: e.target.value })}
          />
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3">
            <div>
              <label className="text-xs text-slate-400">itamtv token</label>
              <input
                className={input}
                value={form.itamtv_token}
                placeholder="เช่น okeXahyKb3eu"
                onChange={(e) => setForm({ ...form, itamtv_token: e.target.value })}
              />
            </div>
            <div>
              <label className="text-xs text-slate-400">itamtv emp code</label>
              <input
                className={input}
                value={form.itamtv_emp_code}
                placeholder="เช่น 19044"
                onChange={(e) => setForm({ ...form, itamtv_emp_code: e.target.value })}
              />
            </div>
          </div>
        </div>

        {error && <p className="text-sm text-rose-400">{error}</p>}
        {msg && <p className="text-sm text-emerald-400">{msg}</p>}

        <button
          type="submit"
          disabled={saving}
          className="px-4 py-2 rounded-lg bg-gradient-to-br from-indigo-500 to-fuchsia-500 text-white text-sm font-medium disabled:opacity-50"
        >
          บันทึก
        </button>
      </form>
    </div>
  );
}
