import { useEffect, useState } from "react";
import api, { apiError } from "../api";

const EMPTY = {
  username: "",
  email: "",
  display_name: "",
  role: "staff",
  line_user_id: "",
  itamtv_token: "",
  itamtv_emp_code: "",
  password: "",
};

export default function Users() {
  const [users, setUsers] = useState([]);
  const [form, setForm] = useState(EMPTY);
  const [editingId, setEditingId] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const load = () => api.get("/users").then(({ data }) => setUsers(data));
  useEffect(() => {
    load().catch((err) => setError(apiError(err, "โหลดรายชื่อไม่ได้")));
  }, []);

  const resetForm = () => {
    setForm(EMPTY);
    setEditingId(null);
    setError("");
  };

  const edit = (u) => {
    setEditingId(u.id);
    setForm({
      username: u.username,
      email: u.email,
      display_name: u.display_name || "",
      role: u.role,
      line_user_id: u.line_user_id || "",
      itamtv_token: u.itamtv_token || "",
      itamtv_emp_code: u.itamtv_emp_code || "",
      password: "",
    });
    setError("");
  };

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      if (editingId) {
        const payload = {
          email: form.email,
          display_name: form.display_name || null,
          role: form.role,
          line_user_id: form.line_user_id || null,
          itamtv_token: form.itamtv_token || null,
          itamtv_emp_code: form.itamtv_emp_code || null,
        };
        if (form.password) payload.password = form.password;
        await api.patch(`/users/${editingId}`, payload);
      } else {
        await api.post("/users", {
          ...form,
          display_name: form.display_name || null,
          line_user_id: form.line_user_id || null,
          itamtv_token: form.itamtv_token || null,
          itamtv_emp_code: form.itamtv_emp_code || null,
        });
      }
      resetForm();
      await load();
    } catch (err) {
      setError(apiError(err, "บันทึกไม่สำเร็จ"));
    } finally {
      setLoading(false);
    }
  };

  const deactivate = async (id) => {
    if (!confirm("ปิดใช้งานบัญชีนี้?")) return;
    try {
      await api.delete(`/users/${id}`);
      await load();
    } catch (err) {
      setError(apiError(err, "ปิดใช้งานไม่สำเร็จ"));
    }
  };

  const input =
    "w-full px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-sm text-slate-100 focus:outline-none focus:border-indigo-400";

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold text-glow">จัดการเจ้าหน้าที่ IT</h1>

      <form onSubmit={submit} className="glass rounded-xl p-4 space-y-3">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-slate-400">Username</label>
            <input
              className={input}
              value={form.username}
              disabled={!!editingId}
              onChange={(e) => setForm({ ...form, username: e.target.value })}
              required
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
            <label className="text-xs text-slate-400">ชื่อที่แสดง</label>
            <input
              className={input}
              value={form.display_name}
              onChange={(e) => setForm({ ...form, display_name: e.target.value })}
            />
          </div>
          <div>
            <label className="text-xs text-slate-400">สิทธิ์</label>
            <select
              className={input}
              value={form.role}
              onChange={(e) => setForm({ ...form, role: e.target.value })}
            >
              <option value="staff">staff</option>
              <option value="admin">admin</option>
            </select>
          </div>
          <div className="sm:col-span-2">
            <label className="text-xs text-slate-400">
              LINE userId (สำหรับส่งการ์ดปิดเคสหาช่างคนนี้)
            </label>
            <input
              className={input}
              value={form.line_user_id}
              placeholder="U xxxxxxxxxxxxxxxx"
              onChange={(e) => setForm({ ...form, line_user_id: e.target.value })}
            />
            <p className="text-[11px] text-slate-500 mt-1">
              ดู userId ได้จาก log ตอนช่างพิมพ์ทักบอท (📌 userId = ...) แล้วนำมากรอกที่นี่
            </p>
          </div>
          <div>
            <label className="text-xs text-slate-400">itamtv token (ช่าง)</label>
            <input
              className={input}
              value={form.itamtv_token}
              placeholder="เช่น okeXahyKb3eu"
              onChange={(e) => setForm({ ...form, itamtv_token: e.target.value })}
            />
            <p className="text-[11px] text-slate-500 mt-1">
              token ท้าย URL ที่ช่างเปิด itamtv (ใช้สั่งปิดงานแทนช่าง)
            </p>
          </div>
          <div>
            <label className="text-xs text-slate-400">itamtv emp code (ผู้รับผิดชอบ)</label>
            <input
              className={input}
              value={form.itamtv_emp_code}
              placeholder="เช่น 19044"
              onChange={(e) => setForm({ ...form, itamtv_emp_code: e.target.value })}
            />
          </div>
          <div className="sm:col-span-2">
            <label className="text-xs text-slate-400">
              รหัสผ่าน {editingId && "(เว้นว่างถ้าไม่เปลี่ยน)"}
            </label>
            <input
              className={input}
              type="password"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              required={!editingId}
            />
          </div>
        </div>

        {error && <p className="text-sm text-rose-400">{error}</p>}

        <div className="flex gap-2">
          <button
            type="submit"
            disabled={loading}
            className="px-4 py-2 rounded-lg bg-gradient-to-br from-indigo-500 to-fuchsia-500 text-white text-sm font-medium disabled:opacity-50"
          >
            {editingId ? "บันทึกการแก้ไข" : "เพิ่มเจ้าหน้าที่"}
          </button>
          {editingId && (
            <button
              type="button"
              onClick={resetForm}
              className="px-4 py-2 rounded-lg bg-white/5 text-slate-300 text-sm"
            >
              ยกเลิก
            </button>
          )}
        </div>
      </form>

      <div className="glass rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead className="text-slate-400 text-xs">
            <tr className="border-b border-white/10">
              <th className="text-left px-4 py-2">ชื่อ</th>
              <th className="text-left px-4 py-2">Email</th>
              <th className="text-left px-4 py-2">สิทธิ์</th>
              <th className="text-left px-4 py-2">LINE</th>
              <th className="text-left px-4 py-2">สถานะ</th>
              <th className="px-4 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id} className="border-b border-white/5">
                <td className="px-4 py-2">
                  {u.display_name || u.username}
                  <span className="text-slate-500 text-xs"> @{u.username}</span>
                </td>
                <td className="px-4 py-2 text-slate-300">{u.email}</td>
                <td className="px-4 py-2">{u.role}</td>
                <td className="px-4 py-2">
                  {u.line_user_id ? (
                    <span className="text-emerald-400" title={u.line_user_id}>
                      ✓ ผูกแล้ว
                    </span>
                  ) : (
                    <span className="text-slate-500">—</span>
                  )}
                </td>
                <td className="px-4 py-2">
                  {u.is_active ? (
                    <span className="text-emerald-400">active</span>
                  ) : (
                    <span className="text-slate-500">ปิดใช้งาน</span>
                  )}
                </td>
                <td className="px-4 py-2 text-right whitespace-nowrap">
                  <button
                    onClick={() => edit(u)}
                    className="text-indigo-300 hover:text-indigo-200 text-xs mr-3"
                  >
                    แก้ไข
                  </button>
                  {u.is_active && (
                    <button
                      onClick={() => deactivate(u.id)}
                      className="text-rose-400 hover:text-rose-300 text-xs"
                    >
                      ปิดใช้งาน
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
