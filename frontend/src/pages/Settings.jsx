import { useEffect, useState } from "react";
import api, { apiError } from "../api";

// model fields เลือกจาก dropdown (หลังเชื่อมต่อ Ollama), ที่เหลือพิมพ์เอง
const MODEL_FIELDS = [
  {
    key: "OLLAMA_MODEL",
    label: "AI Model (gemma)",
    hint: "โมเดลหลักที่ใช้ classify L1/L2 + ตอบผู้ใช้ + อ่านรูป",
  },
  {
    key: "OLLAMA_EMBED_MODEL",
    label: "Embedding Model (RAG)",
    hint: "โมเดลฝัง embedding สำหรับคลังความรู้ — ต้องตรง dimension กับ DB",
  },
];

const NUM_FIELDS = [
  {
    key: "RAG_TOP_K",
    label: "RAG Top K",
    hint: "ดึง chunk ที่ใกล้สุดกี่อันมาเป็น context (1–20)",
    step: "1",
  },
  {
    key: "RAG_MIN_SIMILARITY",
    label: "RAG Min Similarity",
    hint: "cosine similarity ต่ำกว่านี้ตัดทิ้ง (0–1)",
    step: "0.05",
  },
];

export default function Settings() {
  const [data, setData] = useState(null); // ค่า effective จาก server
  const [form, setForm] = useState({});

  const [models, setModels] = useState([]); // รายชื่อ model หลังเชื่อมต่อสำเร็จ
  // conn: { status: 'idle'|'checking'|'ok'|'error', text }
  const [conn, setConn] = useState({ status: "idle", text: "" });

  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState(null);

  // ระบบภายนอกที่เชื่อมต่อ (itamtv / Employee DB) + สถานะสด
  const [integrations, setIntegrations] = useState(null);
  const [togglingKey, setTogglingKey] = useState(null);

  const loadIntegrations = () =>
    api
      .get("/settings/integrations")
      .then(({ data }) => setIntegrations(data.integrations))
      .catch(() => setIntegrations([]));

  // สวิตช์เปิด/ปิดระบบ — บันทึกทันที ไม่ต้องกดปุ่มบันทึกของฟอร์ม
  const toggleIntegration = async (item) => {
    setTogglingKey(item.key);
    try {
      const { data } = await api.patch("/settings", { [item.key]: !item.enabled });
      setData(data);
      setIntegrations((list) =>
        list.map((x) => (x.key === item.key ? { ...x, enabled: !item.enabled } : x))
      );
      setMsg({
        type: "ok",
        text: `${!item.enabled ? "เปิด" : "ปิด"}การเชื่อมต่อ ${item.name} แล้ว — มีผลทันที`,
      });
    } catch (err) {
      setMsg({ type: "err", text: apiError(err, "บันทึกไม่สำเร็จ") });
    } finally {
      setTogglingKey(null);
    }
  };

  // เชื่อมต่อ Ollama ด้วย base_url ที่พิมพ์อยู่ (ยังไม่ save) แล้วโหลด model
  const testConnection = async () => {
    setConn({ status: "checking", text: "กำลังเชื่อมต่อ..." });
    setModels([]);
    try {
      const { data } = await api.get("/settings/ollama-models", {
        params: { base_url: form.OLLAMA_BASE_URL },
      });
      setModels(data.models);
      setConn({
        status: "ok",
        text: `เชื่อมต่อสำเร็จ — พบ ${data.models.length} model`,
      });
    } catch (err) {
      setConn({
        status: "error",
        text: apiError(err, "เชื่อมต่อ Ollama ไม่ได้"),
      });
    }
  };

  // โหลดค่า + ลองเชื่อมต่อด้วยค่าปัจจุบันตอนเข้าหน้า
  useEffect(() => {
    api.get("/settings").then(({ data }) => {
      setData(data);
      const f = {};
      [...MODEL_FIELDS, ...NUM_FIELDS].forEach((x) => (f[x.key] = String(data[x.key])));
      f.OLLAMA_BASE_URL = data.OLLAMA_BASE_URL;
      f.FOLLOWUP_ENABLED = data.FOLLOWUP_ENABLED;
      f.STAFF_PROGRESS_ENABLED = data.STAFF_PROGRESS_ENABLED;
      f.TICKET_CONFIRM_REQUIRED = data.TICKET_CONFIRM_REQUIRED;
      setForm(f);
      loadIntegrations();
      // auto-connect ด้วยค่าที่บันทึกไว้
      setConn({ status: "checking", text: "กำลังเชื่อมต่อ..." });
      api
        .get("/settings/ollama-models", { params: { base_url: data.OLLAMA_BASE_URL } })
        .then(({ data }) => {
          setModels(data.models);
          setConn({ status: "ok", text: `เชื่อมต่อสำเร็จ — พบ ${data.models.length} model` });
        })
        .catch((err) =>
          setConn({
            status: "error",
            text: apiError(err, "เชื่อมต่อ Ollama ไม่ได้"),
          })
        );
    });
  }, []);

  const save = async (e) => {
    e.preventDefault();
    setSaving(true);
    setMsg(null);
    try {
      const payload = { OLLAMA_BASE_URL: form.OLLAMA_BASE_URL };
      MODEL_FIELDS.forEach((f) => (payload[f.key] = form[f.key]));
      NUM_FIELDS.forEach((f) => (payload[f.key] = Number(form[f.key])));
      payload.FOLLOWUP_ENABLED = !!form.FOLLOWUP_ENABLED;
      payload.STAFF_PROGRESS_ENABLED = !!form.STAFF_PROGRESS_ENABLED;
      payload.TICKET_CONFIRM_REQUIRED = !!form.TICKET_CONFIRM_REQUIRED;
      const { data } = await api.patch("/settings", payload);
      setData(data);
      setMsg({ type: "ok", text: "บันทึกแล้ว — มีผลทันที ไม่ต้อง restart" });
    } catch (err) {
      setMsg({ type: "err", text: apiError(err, "บันทึกไม่สำเร็จ") });
    } finally {
      setSaving(false);
    }
  };

  const resetField = (key) => {
    api.patch("/settings", { [key]: null }).then(({ data }) => {
      setData(data);
      setForm((f) => ({
        ...f,
        [key]:
          key === "FOLLOWUP_ENABLED" ||
          key === "STAFF_PROGRESS_ENABLED" ||
          key === "TICKET_CONFIRM_REQUIRED"
            ? data[key]
            : String(data[key]),
      }));
      setMsg({ type: "ok", text: `คืนค่า ${key} กลับเป็นค่าตั้งต้น (.env) แล้ว` });
    });
  };

  if (!data) return <p className="text-slate-500">กำลังโหลด...</p>;

  const overridden = new Set(data.overridden);
  const connected = conn.status === "ok";

  const OverrideTag = ({ k }) =>
    overridden.has(k) ? (
      <span className="text-xs bg-indigo-400/10 text-indigo-300 ring-1 ring-indigo-400/30 px-2 py-0.5 rounded-full">
        override
      </span>
    ) : (
      <span className="text-xs bg-white/5 text-slate-400 ring-1 ring-white/10 px-2 py-0.5 rounded-full">
        ค่าตั้งต้น (.env)
      </span>
    );

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-2xl font-bold text-glow">ตั้งค่า AI</h1>
        <p className="text-sm text-slate-400 mt-1">
          ปรับโมเดลและพารามิเตอร์ RAG ได้สดๆ — ค่าเก็บใน DB ทับค่าใน .env
          และมีผลทันทีกับทุกข้อความที่เข้ามาหลังบันทึก
        </p>
      </div>

      {msg && (
        <div
          className={`text-sm rounded-lg px-3 py-2 ring-1 ${
            msg.type === "ok"
              ? "bg-green-400/10 text-green-300 ring-green-400/30"
              : "bg-red-400/10 text-red-300 ring-red-400/30"
          }`}
        >
          {msg.text}
        </div>
      )}

      {/* ระบบที่เชื่อมต่อ — สวิตช์บันทึกทันที */}
      <div className="glass rounded-xl p-5 space-y-4">
        <div>
          <h2 className="font-semibold text-slate-100">ระบบที่เชื่อมต่อ</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            ระบบภายนอกที่บอทเรียกใช้ — ปิดสวิตช์เพื่อหยุดเรียกชั่วคราว (มีผลทันที)
          </p>
        </div>
        {integrations === null ? (
          <p className="text-sm text-slate-500">กำลังตรวจสอบการเชื่อมต่อ...</p>
        ) : integrations.length === 0 ? (
          <p className="text-sm text-red-400">โหลดสถานะการเชื่อมต่อไม่ได้</p>
        ) : (
          integrations.map((item) => (
            <div
              key={item.key}
              className="flex items-start justify-between gap-4 rounded-lg ring-1 ring-white/10 px-4 py-3"
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span
                    title={item.detail}
                    className={`w-2 h-2 rounded-full shrink-0 ${
                      item.reachable ? "bg-green-400" : "bg-red-400"
                    }`}
                  />
                  <span className="font-medium text-sm text-slate-100">{item.name}</span>
                  <OverrideTag k={item.key} />
                </div>
                <p className="text-xs text-slate-500 mt-1">{item.description}</p>
                <p className="text-xs text-slate-500 font-mono truncate">{item.url}</p>
                <p
                  className={`text-xs mt-0.5 ${
                    item.reachable ? "text-green-400" : "text-red-400"
                  }`}
                >
                  {item.reachable ? "✓ " : "✗ "}
                  {item.detail}
                </p>
              </div>
              {/* สวิตช์เปิด/ปิด */}
              <button
                type="button"
                disabled={togglingKey === item.key}
                onClick={() => toggleIntegration(item)}
                className={`shrink-0 mt-1 w-11 h-6 rounded-full transition-colors relative disabled:opacity-50 ${
                  item.enabled ? "bg-indigo-500" : "bg-white/15"
                }`}
                aria-label={`${item.enabled ? "ปิด" : "เปิด"} ${item.name}`}
              >
                <span
                  className={`absolute top-0.5 w-5 h-5 rounded-full bg-white transition-all ${
                    item.enabled ? "left-[22px]" : "left-0.5"
                  }`}
                />
              </button>
            </div>
          ))
        )}
      </div>

      <form onSubmit={save} className="glass rounded-xl p-5 space-y-5">
        {/* 1. การเชื่อมต่อ Ollama */}
        <div>
          <div className="flex items-center gap-2">
            <label className="font-medium text-sm text-slate-100">Ollama Base URL</label>
            <OverrideTag k="OLLAMA_BASE_URL" />
            {overridden.has("OLLAMA_BASE_URL") && (
              <button
                type="button"
                onClick={() => resetField("OLLAMA_BASE_URL")}
                className="text-xs text-slate-400 hover:text-slate-200 hover:underline ml-auto"
              >
                คืนค่าตั้งต้น
              </button>
            )}
          </div>
          <p className="text-xs text-slate-500 mt-0.5 mb-1.5">
            ที่อยู่เครื่อง Ollama เช่น http://100.94.37.18:11434 — กดทดสอบเพื่อโหลดรายชื่อ model
          </p>
          <div className="flex gap-2">
            <input
              className="input-dark flex-1 rounded-lg px-3 py-2 text-sm"
              value={form.OLLAMA_BASE_URL ?? ""}
              onChange={(e) => setForm({ ...form, OLLAMA_BASE_URL: e.target.value })}
            />
            <button
              type="button"
              onClick={testConnection}
              disabled={conn.status === "checking"}
              className="shrink-0 text-sm px-4 py-2 rounded-lg ring-1 ring-indigo-400/50 text-indigo-300 hover:bg-indigo-400/10 disabled:opacity-50 transition-colors"
            >
              {conn.status === "checking" ? "กำลังเชื่อมต่อ..." : "ทดสอบ & โหลด model"}
            </button>
          </div>
          {conn.status !== "idle" && (
            <p
              className={`text-xs mt-1.5 ${
                conn.status === "ok"
                  ? "text-green-400"
                  : conn.status === "error"
                  ? "text-red-400"
                  : "text-slate-500"
              }`}
            >
              {conn.status === "ok" ? "✓ " : conn.status === "error" ? "✗ " : ""}
              {conn.text}
            </p>
          )}
        </div>

        {/* 2. เลือก model จาก dropdown (เปิดเมื่อเชื่อมต่อสำเร็จ) */}
        {MODEL_FIELDS.map((f) => (
          <div key={f.key}>
            <div className="flex items-center gap-2">
              <label className="font-medium text-sm text-slate-100">{f.label}</label>
              <OverrideTag k={f.key} />
              {overridden.has(f.key) && (
                <button
                  type="button"
                  onClick={() => resetField(f.key)}
                  className="text-xs text-slate-400 hover:text-slate-200 hover:underline ml-auto"
                >
                  คืนค่าตั้งต้น
                </button>
              )}
            </div>
            <p className="text-xs text-slate-500 mt-0.5 mb-1.5">{f.hint}</p>
            {connected ? (
              <select
                className="input-dark w-full rounded-lg px-3 py-2 text-sm"
                value={form[f.key] ?? ""}
                onChange={(e) => setForm({ ...form, [f.key]: e.target.value })}
              >
                {/* เผื่อค่าปัจจุบันไม่อยู่ในรายการที่ pull ไว้ */}
                {!models.some((m) => m.name === form[f.key]) && form[f.key] && (
                  <option value={form[f.key]}>{form[f.key]} (ไม่พบบนเครื่อง)</option>
                )}
                {models.map((m) => (
                  <option key={m.name} value={m.name}>
                    {m.name}
                    {m.vision ? "  👁 รองรับรูป" : ""}
                  </option>
                ))}
              </select>
            ) : (
              <input
                className="input-dark w-full rounded-lg px-3 py-2 text-sm"
                value={form[f.key] ?? ""}
                onChange={(e) => setForm({ ...form, [f.key]: e.target.value })}
                placeholder="เชื่อมต่อ Ollama เพื่อเลือกจากรายการ (หรือพิมพ์เอง)"
              />
            )}
            {/* เตือนเมื่อเลือกโมเดลหลักที่อ่านรูปไม่ได้ — ฟีเจอร์ดูรูป screenshot จะใช้ไม่ได้ */}
            {f.key === "OLLAMA_MODEL" &&
              connected &&
              models.some((m) => m.name === form[f.key] && !m.vision) && (
                <p className="text-xs text-amber-300 mt-1.5">
                  ⚠ โมเดลนี้ไม่รองรับรูป — บอทจะอ่าน error screenshot ไม่ได้
                  (ยังตอบข้อความได้ปกติ) แนะนำเลือกโมเดลที่มี 👁 ถ้าต้องการให้ดูรูป
                </p>
              )}
          </div>
        ))}

        {/* 3. RAG params */}
        {NUM_FIELDS.map((f) => (
          <div key={f.key}>
            <div className="flex items-center gap-2">
              <label className="font-medium text-sm text-slate-100">{f.label}</label>
              <OverrideTag k={f.key} />
              {overridden.has(f.key) && (
                <button
                  type="button"
                  onClick={() => resetField(f.key)}
                  className="text-xs text-slate-400 hover:text-slate-200 hover:underline ml-auto"
                >
                  คืนค่าตั้งต้น
                </button>
              )}
            </div>
            <p className="text-xs text-slate-500 mt-0.5 mb-1.5">{f.hint}</p>
            <input
              type="number"
              step={f.step}
              className="input-dark w-full rounded-lg px-3 py-2 text-sm"
              value={form[f.key] ?? ""}
              onChange={(e) => setForm({ ...form, [f.key]: e.target.value })}
            />
          </div>
        ))}

        {/* 4. Follow-up flow toggle */}
        <div>
          <div className="flex items-center gap-2">
            <label className="font-medium text-sm text-slate-100">Follow-up อัตโนมัติ</label>
            <OverrideTag k="FOLLOWUP_ENABLED" />
            {overridden.has("FOLLOWUP_ENABLED") && (
              <button
                type="button"
                onClick={() => resetField("FOLLOWUP_ENABLED")}
                className="text-xs text-slate-400 hover:text-slate-200 hover:underline ml-auto"
              >
                คืนค่าตั้งต้น
              </button>
            )}
          </div>
          <p className="text-xs text-slate-500 mt-0.5 mb-1.5">
            ผู้ใช้เงียบกลางบทสนทนา → บอทถามซ้ำ (10 นาที) และเปิด Ticket ส่งทีม IT
            อัตโนมัติ (30 นาที) — ปิดสวิตช์นี้เพื่อหยุดทั้ง flow
          </p>
          <label className="flex items-center gap-2 text-sm text-slate-200 cursor-pointer w-fit">
            <input
              type="checkbox"
              className="accent-indigo-500 w-4 h-4"
              checked={!!form.FOLLOWUP_ENABLED}
              onChange={(e) => setForm({ ...form, FOLLOWUP_ENABLED: e.target.checked })}
            />
            {form.FOLLOWUP_ENABLED ? "เปิดใช้งาน" : "ปิดอยู่"}
          </label>
        </div>

        {/* 4b. Staff progress follow-up toggle */}
        <div>
          <div className="flex items-center gap-2">
            <label className="font-medium text-sm text-slate-100">
              ตามงานช่างอัตโนมัติ
            </label>
            <OverrideTag k="STAFF_PROGRESS_ENABLED" />
            {overridden.has("STAFF_PROGRESS_ENABLED") && (
              <button
                type="button"
                onClick={() => resetField("STAFF_PROGRESS_ENABLED")}
                className="text-xs text-slate-400 hover:text-slate-200 hover:underline ml-auto"
              >
                คืนค่าตั้งต้น
              </button>
            )}
          </div>
          <p className="text-xs text-slate-500 mt-0.5 mb-1.5">
            ช่างรับงานแล้ว (in_progress) → บอททักถามความคืบหน้าทาง LINE ทุก 15 นาที
            พร้อมปุ่มปิดเคส จนกว่าจะปิดงาน — ปิดสวิตช์นี้เพื่อหยุดการทัก
          </p>
          <label className="flex items-center gap-2 text-sm text-slate-200 cursor-pointer w-fit">
            <input
              type="checkbox"
              className="accent-indigo-500 w-4 h-4"
              checked={!!form.STAFF_PROGRESS_ENABLED}
              onChange={(e) =>
                setForm({ ...form, STAFF_PROGRESS_ENABLED: e.target.checked })
              }
            />
            {form.STAFF_PROGRESS_ENABLED ? "เปิดใช้งาน" : "ปิดอยู่"}
          </label>
        </div>

        {/* 5. Ticket confirm toggle */}
        <div>
          <div className="flex items-center gap-2">
            <label className="font-medium text-sm text-slate-100">
              ยืนยันก่อนเปิด Ticket
            </label>
            <OverrideTag k="TICKET_CONFIRM_REQUIRED" />
            {overridden.has("TICKET_CONFIRM_REQUIRED") && (
              <button
                type="button"
                onClick={() => resetField("TICKET_CONFIRM_REQUIRED")}
                className="text-xs text-slate-400 hover:text-slate-200 hover:underline ml-auto"
              >
                คืนค่าตั้งต้น
              </button>
            )}
          </div>
          <p className="text-xs text-slate-500 mt-0.5 mb-1.5">
            เปิด = บอทสรุปเรื่องแล้วขึ้นปุ่มให้ผู้ใช้กด "เปิด Ticket ✅" ก่อนถึงจะเปิดเคส —
            ปิด = เมื่อข้อมูลครบบอทเปิดเคสให้ทันทีโดยไม่ถามยืนยัน
          </p>
          <label className="flex items-center gap-2 text-sm text-slate-200 cursor-pointer w-fit">
            <input
              type="checkbox"
              className="accent-indigo-500 w-4 h-4"
              checked={!!form.TICKET_CONFIRM_REQUIRED}
              onChange={(e) =>
                setForm({ ...form, TICKET_CONFIRM_REQUIRED: e.target.checked })
              }
            />
            {form.TICKET_CONFIRM_REQUIRED ? "ต้องยืนยันก่อนเปิด" : "เปิดเคสทันทีเมื่อข้อมูลครบ"}
          </label>
        </div>

        <div className="pt-1 border-t border-white/10">
          <p className="text-xs text-slate-500 mt-3">
            EMBED_DIM = <span className="font-mono">{data.EMBED_DIM}</span> (อ่านอย่างเดียว —
            ผูกกับ vector column ใน DB เปลี่ยนต้องทำ migration + re-embed)
          </p>
        </div>

        <button
          type="submit"
          disabled={saving}
          className="btn-primary text-sm px-5 py-2 rounded-lg font-medium"
        >
          {saving ? "กำลังบันทึก..." : "บันทึก"}
        </button>
      </form>
    </div>
  );
}
