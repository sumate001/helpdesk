import { useEffect, useState } from "react";
import api, { apiError } from "../api";

const CATEGORIES = [
  "service_request",
  "equipment_request",
  "software",
  "account",
  "other",
];
const FIELD_TYPES = ["text", "textarea", "select", "number"];
const EMPTY = {
  name: "",
  slug: "",
  description: "",
  category: "service_request",
  priority: "low",
  is_active: true,
  fields: [],
};

// เทมเพลตตั้งต้น — กด "ใช้เทมเพลตนี้" เพื่อสำเนามาแก้ชื่อ/slug/field ต่อได้ทันที
// (ฟอร์มอื่นที่สร้างไว้แล้วก็ใช้เป็นเทมเพลตได้เหมือนกัน ผ่านปุ่ม "ทำสำเนา" ในรายการด้านล่าง)
const TEMPLATES = [
  {
    label: "ขอใช้งาน VPN",
    icon: "🔒",
    data: {
      name: "ขอใช้งาน VPN",
      slug: "vpn",
      description: "ยื่นขอใช้งาน VPN สำหรับเข้าระบบจากภายนอก",
      category: "service_request",
      priority: "medium",
      is_active: true,
      fields: [
        { key: "full_name", label: "ชื่อ-นามสกุล", type: "text", required: true, options: null },
        { key: "building", label: "อาคาร", type: "text", required: true, options: null },
        { key: "floor", label: "ชั้น", type: "text", required: true, options: null },
        { key: "reason", label: "เหตุผลที่ขอใช้งาน", type: "textarea", required: true, options: null },
      ],
    },
  },
];

const toFormState = (data) => ({
  ...data,
  description: data.description || "",
  category: data.category || "",
  fields: data.fields.map((x) => ({ ...x, optionsText: (x.options || []).join(", ") })),
});

// จัดการแบบฟอร์ม LIFF — สร้าง/แก้ฟอร์ม + กำหนด field เอง. onChange แจ้ง parent ให้ refresh dropdown
export default function FormsManager({ onChange }) {
  const [forms, setForms] = useState([]);
  const [form, setForm] = useState(EMPTY);
  const [editingId, setEditingId] = useState(null);
  const [error, setError] = useState("");
  const [open, setOpen] = useState(false);
  const [dragIndex, setDragIndex] = useState(null);

  const load = () =>
    api.get("/forms").then(({ data }) => {
      setForms(data);
      onChange?.(data);
    });
  useEffect(() => {
    load();
  }, []);

  const reset = () => {
    setForm(EMPTY);
    setEditingId(null);
    setError("");
  };

  const addField = () =>
    setForm({
      ...form,
      fields: [...form.fields, { key: "", label: "", type: "text", required: true, options: null }],
    });
  const updField = (i, patch) => {
    const fields = form.fields.map((f, idx) => (idx === i ? { ...f, ...patch } : f));
    setForm({ ...form, fields });
  };
  const rmField = (i) => setForm({ ...form, fields: form.fields.filter((_, idx) => idx !== i) });

  // ลากสลับลำดับ field — ย้าย field จาก dragIndex ไปวางที่ตำแหน่ง target
  const moveField = (from, to) => {
    if (from === to || from == null || to == null) return;
    const fields = [...form.fields];
    const [moved] = fields.splice(from, 1);
    fields.splice(to, 0, moved);
    setForm({ ...form, fields });
  };

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    try {
      const payload = {
        ...form,
        description: form.description || null,
        category: form.category || null,
        fields: form.fields.map((f) => ({
          key: f.key,
          label: f.label,
          type: f.type,
          required: !!f.required,
          options:
            f.type === "select"
              ? (f.optionsText || (f.options || []).join(",") || "")
                  .split(",")
                  .map((s) => s.trim())
                  .filter(Boolean)
              : null,
        })),
      };
      if (editingId) await api.patch(`/forms/${editingId}`, payload);
      else await api.post("/forms", payload);
      reset();
      load();
    } catch (err) {
      setError(apiError(err, "บันทึกไม่สำเร็จ"));
    }
  };

  const startEdit = (f) => {
    setEditingId(f.id);
    setForm(toFormState(f));
    setOpen(true);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  // ใช้เทมเพลตตั้งต้น — เติมฟอร์มสร้างใหม่ด้วยข้อมูลเทมเพลต ให้ไปแก้ชื่อ/slug ต่อก่อนบันทึก
  const useTemplate = (t) => {
    setEditingId(null);
    setForm(toFormState(t.data));
    setError("");
    setOpen(true);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  // ทำสำเนาฟอร์มที่มีอยู่ — เติมชื่อ/slug ใหม่ให้แก้ก่อนบันทึกเป็นฟอร์มใหม่ (ไม่ใช่แก้ของเดิม)
  const duplicate = (f) => {
    setEditingId(null);
    setForm(
      toFormState({
        ...f,
        name: `${f.name} (สำเนา)`,
        slug: `${f.slug}-copy`,
      })
    );
    setError("");
    setOpen(true);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const remove = async (f) => {
    if (!window.confirm(`ลบฟอร์ม "${f.name}" ?`)) return;
    await api.delete(`/forms/${f.id}`);
    if (editingId === f.id) reset();
    load();
  };

  return (
    <div className="glass rounded-xl">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-4 py-3 text-left"
      >
        <span className="font-semibold text-slate-100">
          แบบฟอร์มขอใช้บริการ (LIFF) — {forms.length} ฟอร์ม
        </span>
        <span className="text-slate-500">{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className="px-4 pb-4 space-y-5 border-t border-white/10 pt-4">
          {/* ── ส่วนที่ 1: รายการฟอร์มที่มีอยู่ ── */}
          <section>
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-bold text-slate-200">📋 ฟอร์มที่มีอยู่</h3>
              {editingId === null && (
                <span className="text-xs text-slate-500">กด “แก้ไข” เพื่อนำมาแก้ด้านล่าง</span>
              )}
            </div>
            <div className="ring-1 ring-white/10 rounded-lg divide-y divide-white/10 overflow-hidden">
              {forms.length === 0 && (
                <p className="p-4 text-center text-sm text-slate-500">
                  ยังไม่มีฟอร์ม — สร้างใหม่ได้ที่ด้านล่าง
                </p>
              )}
              {forms.map((f) => (
                <div
                  key={f.id}
                  className={`px-3 py-2 flex items-center gap-2 ${
                    editingId === f.id ? "bg-indigo-400/10" : ""
                  }`}
                >
                  <div className="flex-1 min-w-0">
                    <span className="font-medium text-slate-100">{f.name}</span>
                    <span className="text-xs text-slate-500 ml-2">/{f.slug}</span>
                    {editingId === f.id && (
                      <span className="text-xs bg-indigo-400/10 text-indigo-300 ring-1 ring-indigo-400/30 px-2 py-0.5 rounded-full ml-2">
                        กำลังแก้ไข
                      </span>
                    )}
                    {!f.is_active && (
                      <span className="text-xs bg-amber-400/10 text-amber-300 ring-1 ring-amber-400/30 px-2 py-0.5 rounded-full ml-2">
                        ปิดใช้งาน
                      </span>
                    )}
                    <span className="text-xs text-slate-500 ml-2">{f.fields.length} field</span>
                  </div>
                  <button onClick={() => startEdit(f)} className="text-indigo-300 text-sm hover:underline">
                    แก้ไข
                  </button>
                  <button onClick={() => duplicate(f)} className="text-teal-300 text-sm hover:underline">
                    ทำสำเนา
                  </button>
                  <button onClick={() => remove(f)} className="text-red-400 text-sm hover:underline">
                    ลบ
                  </button>
                </div>
              ))}
            </div>
          </section>

          {/* ── เทมเพลตตั้งต้น ── */}
          <section>
            <h3 className="text-sm font-bold text-slate-200 mb-2">✨ เทมเพลตตั้งต้น</h3>
            <p className="text-xs text-slate-500 mb-2">
              กด "ใช้เทมเพลตนี้" เพื่อนำมาแก้ชื่อ/slug/field ต่อด้านล่าง แล้วบันทึกเป็นฟอร์มใหม่
              — หรือกด "ทำสำเนา" จากฟอร์มที่มีอยู่แล้วด้านบน (เช่น VPN) มาปรับเป็นฟอร์มใหม่ก็ได้เช่นกัน
            </p>
            <div className="flex flex-wrap gap-2">
              {TEMPLATES.map((t) => (
                <button
                  key={t.label}
                  type="button"
                  onClick={() => useTemplate(t)}
                  className="text-sm px-3 py-1.5 rounded-lg ring-1 ring-white/10 text-slate-200 hover:bg-white/5 hover:ring-indigo-400/40 transition-colors"
                >
                  {t.icon} {t.label}
                </button>
              ))}
            </div>
          </section>

          {/* ── ส่วนที่ 2: สร้าง/แก้ฟอร์ม ── */}
          <form onSubmit={submit} className="ring-1 ring-indigo-400/30 rounded-xl overflow-hidden">
            <div className="bg-indigo-400/10 px-3 py-2 flex items-center justify-between">
              <h3 className="text-sm font-bold text-indigo-200">
                {editingId ? `✏️ กำลังแก้ฟอร์ม: ${form.name || `#${editingId}`}` : "➕ สร้างฟอร์มใหม่"}
              </h3>
              {editingId && (
                <button
                  type="button"
                  onClick={reset}
                  className="text-xs text-indigo-300 hover:underline"
                >
                  + สร้างใหม่แทน
                </button>
              )}
            </div>
            <div className="p-3 space-y-3">
            <div className="grid grid-cols-2 gap-2">
              <input
                className="input-dark rounded-lg px-2 py-1.5 text-sm"
                placeholder="ชื่อฟอร์ม เช่น ขอใช้งาน VPN"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                required
              />
              <input
                className="input-dark rounded-lg px-2 py-1.5 text-sm"
                placeholder="slug (a-z, เช่น vpn)"
                value={form.slug}
                onChange={(e) => setForm({ ...form, slug: e.target.value })}
                required
              />
              <select
                className="input-dark rounded-lg px-2 py-1.5 text-sm"
                value={form.category}
                onChange={(e) => setForm({ ...form, category: e.target.value })}
              >
                {CATEGORIES.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
              <select
                className="input-dark rounded-lg px-2 py-1.5 text-sm"
                value={form.priority}
                onChange={(e) => setForm({ ...form, priority: e.target.value })}
              >
                {["low", "medium", "high", "critical"].map((p) => (
                  <option key={p} value={p}>{p}</option>
                ))}
              </select>
            </div>
            <input
              className="input-dark w-full rounded-lg px-2 py-1.5 text-sm"
              placeholder="คำอธิบาย (แสดงบนหัวฟอร์ม)"
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
            />

            {/* field editor */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-slate-200">ช่องกรอก (fields)</span>
                <button type="button" onClick={addField} className="text-indigo-300 text-sm hover:underline">
                  + เพิ่ม field
                </button>
              </div>
              {form.fields.map((f, i) => (
                <div
                  key={i}
                  className={`grid grid-cols-12 gap-1 items-center rounded-lg ${
                    dragIndex === i ? "opacity-50 bg-indigo-400/10" : ""
                  }`}
                  onDragOver={(e) => {
                    e.preventDefault();
                    if (dragIndex !== null && dragIndex !== i) {
                      moveField(dragIndex, i);
                      setDragIndex(i);
                    }
                  }}
                  onDrop={() => setDragIndex(null)}
                >
                  <span
                    draggable
                    onDragStart={() => setDragIndex(i)}
                    onDragEnd={() => setDragIndex(null)}
                    className="col-span-1 cursor-grab active:cursor-grabbing text-slate-500 text-center select-none"
                    title="ลากเพื่อจัดลำดับ"
                  >
                    ⠿
                  </span>
                  <input
                    className="input-dark col-span-2 rounded px-2 py-1 text-xs"
                    placeholder="key"
                    value={f.key}
                    onChange={(e) => updField(i, { key: e.target.value })}
                    required
                  />
                  <input
                    className="input-dark col-span-3 rounded px-2 py-1 text-xs"
                    placeholder="label"
                    value={f.label}
                    onChange={(e) => updField(i, { label: e.target.value })}
                    required
                  />
                  <select
                    className="input-dark col-span-2 rounded px-1 py-1 text-xs"
                    value={f.type}
                    onChange={(e) => updField(i, { type: e.target.value })}
                  >
                    {FIELD_TYPES.map((t) => (
                      <option key={t} value={t}>{t}</option>
                    ))}
                  </select>
                  {f.type === "select" ? (
                    <input
                      className="input-dark col-span-3 rounded px-2 py-1 text-xs"
                      placeholder="ตัวเลือก,คั่นด้วย,comma"
                      value={f.optionsText ?? (f.options || []).join(", ")}
                      onChange={(e) => updField(i, { optionsText: e.target.value })}
                    />
                  ) : (
                    <label className="col-span-3 flex items-center gap-1 text-xs text-slate-400">
                      <input
                        type="checkbox"
                        checked={!!f.required}
                        onChange={(e) => updField(i, { required: e.target.checked })}
                      />
                      บังคับ
                    </label>
                  )}
                  <button
                    type="button"
                    onClick={() => rmField(i)}
                    className="col-span-1 text-red-400 text-sm"
                  >
                    ✕
                  </button>
                </div>
              ))}
              <p className="text-xs text-slate-500">
                key พิเศษ: <code>full_name</code> / <code>building</code> / <code>floor</code>{" "}
                จะอัปเดตเข้าโปรไฟล์ผู้แจ้งอัตโนมัติ
              </p>
            </div>

            <label className="flex items-center gap-2 text-sm text-slate-300">
              <input
                type="checkbox"
                checked={form.is_active}
                onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
              />
              เปิดใช้งาน
            </label>
            {error && <p className="text-sm text-red-400">{error}</p>}
            <div className="flex gap-2">
              <button className="btn-primary text-sm px-4 py-1.5 rounded-lg font-medium">
                {editingId ? "บันทึก" : "สร้างฟอร์ม"}
              </button>
              {editingId && (
                <button type="button" onClick={reset} className="text-sm px-4 py-1.5 text-slate-400 hover:text-slate-200">
                  ยกเลิก
                </button>
              )}
            </div>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
