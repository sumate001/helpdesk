import { useEffect, useState } from "react";
import api, { apiError } from "../api";
import FormsManager from "../components/FormsManager";

const CATEGORIES = [
  "hardware",
  "software",
  "network",
  "account",
  "service_request",
  "equipment_request",
  "other",
];

const EMPTY_FORM = { title: "", category: "", source: "", content: "", form_id: "" };

const TABS = [
  { key: "kb", label: "ความรู้ (KB)" },
  { key: "forms", label: "แบบฟอร์ม" },
];

export default function KnowledgeBase() {
  const [tab, setTab] = useState("kb");
  const [chunks, setChunks] = useState([]);
  const [forms, setForms] = useState([]);
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
        form_id: form.form_id ? Number(form.form_id) : null,
      };
      if (editingId) {
        await api.patch(`/kb/${editingId}`, payload);
      } else {
        await api.post("/kb", payload);
      }
      resetForm();
      load();
    } catch (err) {
      setError(apiError(err, "บันทึกไม่สำเร็จ (ตรวจว่า Ollama embed model พร้อมใช้งาน)"));
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
      form_id: c.form_id ? String(c.form_id) : "",
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
        <h1 className="text-2xl font-bold text-glow">คลังความรู้ (KB) สำหรับ AI</h1>
        <span className="text-sm text-slate-500">
          {tab === "kb" ? `${chunks.length} รายการ` : `${forms.length} ฟอร์ม`}
        </span>
      </div>

      {/* แท็บ: ความรู้ กับ แบบฟอร์ม เป็นคนละงาน ไม่ต้องเลื่อนผ่านกัน */}
      <div className="flex gap-1 border-b border-white/10">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 text-sm font-medium -mb-px border-b-2 transition-colors ${
              tab === t.key
                ? "border-indigo-400 text-indigo-300"
                : "border-transparent text-slate-400 hover:text-slate-200"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* แบบฟอร์ม — mount ไว้ตลอดแม้อยู่แท็บอื่น เพื่อให้ dropdown "ผูกแบบฟอร์ม" มีข้อมูล
          และงานที่แก้ค้างไว้ไม่หายเมื่อสลับแท็บ */}
      <div className={tab === "forms" ? "" : "hidden"}>
        <FormsManager onChange={setForms} embedded />
      </div>

      <div className={tab === "kb" ? "space-y-6" : "hidden"}>
      <p className="text-sm text-slate-400">
        ความรู้ระบบ/นโยบาย IT ที่ AI ใช้ตอบและตัดสินว่าต้องเปิดเคสไหม — แนะนำ 1 หัวข้อ/1 รายการ
        เขียนให้ชัดว่าเรื่องไหน "ตอบได้เลย" หรือ "ต้องขออนุมัติ/ให้ IT ดำเนินการ"
      </p>

      {/* ฟอร์มเพิ่ม/แก้ */}
      <form onSubmit={submit} className="glass rounded-xl p-4 space-y-3">
        <h2 className="font-semibold text-slate-100">
          {editingId ? `แก้ไขรายการ #${editingId}` : "เพิ่มความรู้ใหม่"}
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <input
            className="input-dark rounded-lg px-3 py-2 text-sm"
            placeholder="หัวข้อ เช่น การขอใช้ VPN"
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
          />
          <select
            className="input-dark rounded-lg px-3 py-2 text-sm"
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
            className="input-dark rounded-lg px-3 py-2 text-sm"
            placeholder="ที่มา (ไม่บังคับ) เช่น IT Policy 2026"
            value={form.source}
            onChange={(e) => setForm({ ...form, source: e.target.value })}
          />
        </div>
        <textarea
          className="input-dark w-full rounded-lg px-3 py-2 text-sm"
          rows={4}
          placeholder="เนื้อหา เช่น การขอใช้งาน VPN ต้องยื่นขออนุมัติจากหัวหน้าแผนกและ IT ก่อนทุกครั้ง"
          value={form.content}
          onChange={(e) => setForm({ ...form, content: e.target.value })}
        />
        <div>
          <label className="block text-sm text-slate-400 mb-1">
            ผูกแบบฟอร์ม (เมื่อ AI เจอความรู้นี้ จะยื่นปุ่มเปิดฟอร์มให้ user)
          </label>
          <select
            className="input-dark w-full md:w-1/2 rounded-lg px-3 py-2 text-sm"
            value={form.form_id}
            onChange={(e) => setForm({ ...form, form_id: e.target.value })}
          >
            <option value="">— ไม่ผูกฟอร์ม —</option>
            {forms.map((f) => (
              <option key={f.id} value={f.id}>
                {f.name} (/{f.slug})
              </option>
            ))}
          </select>
        </div>
        {error && <p className="text-sm text-red-400">{error}</p>}
        <div className="flex gap-2">
          <button
            type="submit"
            disabled={loading}
            className="btn-primary text-sm px-4 py-2 rounded-lg font-medium"
          >
            {loading ? "กำลังบันทึก..." : editingId ? "บันทึกการแก้ไข" : "เพิ่ม"}
          </button>
          {editingId && (
            <button
              type="button"
              onClick={resetForm}
              className="text-sm px-4 py-2 rounded-lg text-slate-400 hover:bg-white/5 hover:text-slate-200 transition-colors"
            >
              ยกเลิก
            </button>
          )}
        </div>
      </form>

      {/* รายการ */}
      <div className="glass rounded-xl divide-y divide-white/10">
        {chunks.length === 0 && (
          <p className="p-6 text-center text-sm text-slate-500">ยังไม่มีความรู้ในระบบ</p>
        )}
        {chunks.map((c) => (
          <div key={c.id} className="p-4 flex items-start gap-3">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-medium text-slate-100">{c.title || "(ไม่มีหัวข้อ)"}</span>
                {c.category && (
                  <span className="text-xs bg-white/5 text-slate-300 ring-1 ring-white/10 px-2 py-0.5 rounded-full">
                    {c.category}
                  </span>
                )}
                {!c.is_active && (
                  <span className="text-xs bg-amber-400/10 text-amber-300 ring-1 ring-amber-400/30 px-2 py-0.5 rounded-full">
                    ปิดใช้งาน
                  </span>
                )}
                {c.form_id && (
                  <span className="text-xs bg-indigo-400/10 text-indigo-300 ring-1 ring-indigo-400/30 px-2 py-0.5 rounded-full">
                    📋 {forms.find((f) => f.id === c.form_id)?.name || "ผูกฟอร์ม"}
                  </span>
                )}
              </div>
              <p className="text-sm text-slate-400 mt-1 whitespace-pre-wrap">{c.content}</p>
              {c.source && (
                <p className="text-xs text-slate-500 mt-1">ที่มา: {c.source}</p>
              )}
            </div>
            <div className="flex flex-col gap-1 text-sm shrink-0">
              <button
                onClick={() => startEdit(c)}
                className="text-indigo-300 hover:text-indigo-200 hover:underline"
              >
                แก้ไข
              </button>
              <button
                onClick={() => toggleActive(c)}
                className="text-slate-400 hover:text-slate-200 hover:underline"
              >
                {c.is_active ? "ปิดใช้" : "เปิดใช้"}
              </button>
              <button
                onClick={() => remove(c)}
                className="text-red-400 hover:text-red-300 hover:underline"
              >
                ลบ
              </button>
            </div>
          </div>
        ))}
      </div>
      </div>
    </div>
  );
}
