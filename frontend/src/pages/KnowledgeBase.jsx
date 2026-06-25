import { useEffect, useState } from "react";
import api from "../api";

const CATEGORIES = [
  "hardware",
  "software",
  "network",
  "account",
  "service_request",
  "equipment_request",
  "other",
];

const EMPTY_FORM = { title: "", category: "", source: "", content: "" };

export default function KnowledgeBase() {
  const [chunks, setChunks] = useState([]);
  const [form, setForm] = useState(EMPTY_FORM);
  const [editingId, setEditingId] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const load = () => {
    api.get("/kb").then(({ data }) => setChunks(data));
  };

  useEffect(load, []);

  const resetForm = () => {
    setForm(EMPTY_FORM);
    setEditingId(null);
    setError("");
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!form.content.trim()) {
      setError("กรุณากรอกเนื้อหา");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const payload = {
        title: form.title || null,
        category: form.category || null,
        source: form.source || null,
        content: form.content,
      };
      if (editingId) {
        await api.patch(`/kb/${editingId}`, payload);
      } else {
        await api.post("/kb", payload);
      }
      resetForm();
      load();
    } catch (err) {
      setError(
        err.response?.data?.detail ||
          "บันทึกไม่สำเร็จ (ตรวจว่า Ollama embed model พร้อมใช้งาน)"
      );
    } finally {
      setLoading(false);
    }
  };

  const startEdit = (c) => {
    setEditingId(c.id);
    setForm({
      title: c.title || "",
      category: c.category || "",
      source: c.source || "",
      content: c.content,
    });
    setError("");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const toggleActive = async (c) => {
    await api.patch(`/kb/${c.id}`, { is_active: !c.is_active });
    load();
  };

  const remove = async (c) => {
    if (!window.confirm(`ลบความรู้ "${c.title || c.content.slice(0, 30)}" ?`)) return;
    await api.delete(`/kb/${c.id}`);
    if (editingId === c.id) resetForm();
    load();
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">คลังความรู้ (KB) สำหรับ AI</h1>
        <span className="text-sm text-slate-400">{chunks.length} รายการ</span>
      </div>
      <p className="text-sm text-slate-500">
        ความรู้ระบบ/นโยบาย IT ที่ AI ใช้ตอบและตัดสินว่าต้องเปิดเคสไหม — แนะนำ 1 หัวข้อ/1 รายการ
        เขียนให้ชัดว่าเรื่องไหน "ตอบได้เลย" หรือ "ต้องขออนุมัติ/ให้ IT ดำเนินการ"
      </p>

      {/* ฟอร์มเพิ่ม/แก้ */}
      <form
        onSubmit={submit}
        className="bg-white rounded-lg shadow-sm p-4 border border-slate-200 space-y-3"
      >
        <h2 className="font-semibold">
          {editingId ? `แก้ไขรายการ #${editingId}` : "เพิ่มความรู้ใหม่"}
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <input
            className="border border-slate-300 rounded-md px-3 py-2 text-sm"
            placeholder="หัวข้อ เช่น การขอใช้ VPN"
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
          />
          <select
            className="border border-slate-300 rounded-md px-3 py-2 text-sm"
            value={form.category}
            onChange={(e) => setForm({ ...form, category: e.target.value })}
          >
            <option value="">— หมวด (ไม่ระบุ) —</option>
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
          <input
            className="border border-slate-300 rounded-md px-3 py-2 text-sm"
            placeholder="ที่มา (ไม่บังคับ) เช่น IT Policy 2026"
            value={form.source}
            onChange={(e) => setForm({ ...form, source: e.target.value })}
          />
        </div>
        <textarea
          className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm"
          rows={4}
          placeholder="เนื้อหา เช่น การขอใช้งาน VPN ต้องยื่นขออนุมัติจากหัวหน้าแผนกและ IT ก่อนทุกครั้ง"
          value={form.content}
          onChange={(e) => setForm({ ...form, content: e.target.value })}
        />
        {error && <p className="text-sm text-red-600">{error}</p>}
        <div className="flex gap-2">
          <button
            type="submit"
            disabled={loading}
            className="bg-indigo-600 text-white text-sm px-4 py-2 rounded-md hover:bg-indigo-700 disabled:opacity-50"
          >
            {loading ? "กำลังบันทึก..." : editingId ? "บันทึกการแก้ไข" : "เพิ่ม"}
          </button>
          {editingId && (
            <button
              type="button"
              onClick={resetForm}
              className="text-sm px-4 py-2 rounded-md text-slate-600 hover:bg-slate-100"
            >
              ยกเลิก
            </button>
          )}
        </div>
      </form>

      {/* รายการ */}
      <div className="bg-white rounded-lg shadow-sm border border-slate-200 divide-y divide-slate-100">
        {chunks.length === 0 && (
          <p className="p-6 text-center text-sm text-slate-400">ยังไม่มีความรู้ในระบบ</p>
        )}
        {chunks.map((c) => (
          <div key={c.id} className="p-4 flex items-start gap-3">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-medium">{c.title || "(ไม่มีหัวข้อ)"}</span>
                {c.category && (
                  <span className="text-xs bg-slate-100 text-slate-600 px-2 py-0.5 rounded">
                    {c.category}
                  </span>
                )}
                {!c.is_active && (
                  <span className="text-xs bg-amber-100 text-amber-700 px-2 py-0.5 rounded">
                    ปิดใช้งาน
                  </span>
                )}
              </div>
              <p className="text-sm text-slate-600 mt-1 whitespace-pre-wrap">{c.content}</p>
              {c.source && (
                <p className="text-xs text-slate-400 mt-1">ที่มา: {c.source}</p>
              )}
            </div>
            <div className="flex flex-col gap-1 text-sm shrink-0">
              <button
                onClick={() => startEdit(c)}
                className="text-indigo-600 hover:underline"
              >
                แก้ไข
              </button>
              <button
                onClick={() => toggleActive(c)}
                className="text-slate-500 hover:underline"
              >
                {c.is_active ? "ปิดใช้" : "เปิดใช้"}
              </button>
              <button
                onClick={() => remove(c)}
                className="text-red-600 hover:underline"
              >
                ลบ
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
