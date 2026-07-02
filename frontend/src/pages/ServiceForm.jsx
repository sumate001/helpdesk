import { useEffect, useState } from "react";
import liff from "@line/liff";

const LIFF_ID = import.meta.env.VITE_LIFF_ID;

// อ่าน slug จาก ?form=... ตรงๆ หรือจาก liff.state (LIFF ห่อ query เดิมไว้ตรงนี้ตอน redirect)
// liff.state บางครั้งมี "/" หรือ "?" นำหน้าไม่แน่นอน (ขึ้นกับว่า LIFF URL มี path ต่อท้ายหรือไม่)
// เลยลอกอักขระที่ไม่ใช่ query จริงออกก่อน parse แทนที่จะเช็คแค่ startsWith("?")
function stripToQuery(str) {
  const idx = str.indexOf("?");
  return idx >= 0 ? str.slice(idx + 1) : str.replace(/^\/+/, "");
}

function readSlug() {
  const p = new URLSearchParams(window.location.search);
  let slug = p.get("form");
  if (!slug) {
    const state = p.get("liff.state");
    if (state) {
      slug = new URLSearchParams(stripToQuery(state)).get("form");
    }
  }
  // ทางสำรองสุดท้าย — เผื่อ liff.state ถูก encode ซ้อนหรือรูปแบบไม่ตรงที่คาดไว้
  if (!slug) {
    const match = decodeURIComponent(window.location.href).match(/[?&]form=([^&]+)/);
    if (match) slug = decodeURIComponent(match[1]);
  }
  return slug;
}

// Generic LIFF form renderer — อ่าน ?form=<slug> แล้วดึงนิยามฟอร์มมา render + submit
export default function ServiceForm() {
  const [def, setDef] = useState(null); // { name, description, fields }
  const [values, setValues] = useState({});
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(null);
  const [slug, setSlug] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        await liff.init({ liffId: LIFF_ID });
        if (!liff.isLoggedIn()) {
          liff.login();
          return;
        }
        // อ่าน slug หลัง init — ตอนนี้ liff.state ถูกคลายเข้า URL แล้ว
        const s = readSlug();
        if (!s) {
          console.warn("ServiceForm: ไม่พบ form slug, href=", window.location.href);
          throw new Error("ไม่พบรหัสฟอร์ม (form)");
        }
        setSlug(s);
        const resp = await fetch(`/api/liff/forms/${s}`);
        if (!resp.ok) throw new Error("ไม่พบฟอร์มนี้ หรือถูกปิดใช้งาน");
        const data = await resp.json();
        // ค่าเริ่มต้น: เติมชื่อจากโปรไฟล์ LINE ถ้ามี field full_name
        const profile = await liff.getProfile().catch(() => ({}));
        const init = {};
        for (const f of data.fields) {
          if (f.type === "select" && f.options?.length) init[f.key] = f.options[0];
          else init[f.key] = "";
        }
        if ("full_name" in init && profile.displayName) init.full_name = profile.displayName;
        setValues(init);
        setDef(data);
        setReady(true);
      } catch (e) {
        setError(e?.message || String(e));
      }
    })();
  }, []);

  const set = (k) => (e) => setValues({ ...values, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      const idToken = liff.getIDToken();
      if (!idToken) throw new Error("ไม่พบ ID token — กรุณาเข้าผ่านแอป LINE");
      const resp = await fetch(`/api/liff/forms/${slug}/submit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id_token: idToken, values }),
      });
      if (!resp.ok) {
        const d = await resp.json().catch(() => ({}));
        throw new Error(d.detail || "ส่งคำขอไม่สำเร็จ");
      }
      setDone(await resp.json());
    } catch (e) {
      setError(e?.message || "เกิดข้อผิดพลาด");
    } finally {
      setSubmitting(false);
    }
  };

  if (error && !ready && !done) return <Centered><p className="text-red-600">{error}</p></Centered>;
  if (!ready && !done) return <Centered><p className="text-slate-500">กำลังโหลด…</p></Centered>;
  if (done) {
    return (
      <Centered>
        <div className="text-center">
          <div className="text-4xl mb-3">✅</div>
          <p className="font-semibold text-slate-800">ส่งคำขอเรียบร้อย</p>
          <p className="text-slate-600 mt-1">หมายเลข Ticket: {done.ticket_no}</p>
          <p className="text-sm text-slate-500 mt-2">ทีม IT จะตรวจสอบและแจ้งผลกลับทาง LINE ครับ</p>
          <button
            onClick={() => liff.closeWindow()}
            className="mt-5 px-4 py-2 rounded-md bg-indigo-600 text-white text-sm"
          >
            ปิดหน้าต่าง
          </button>
        </div>
      </Centered>
    );
  }

  return (
    <div className="min-h-screen bg-white max-w-md mx-auto p-5">
      <h1 className="text-lg font-bold text-slate-800 mb-1">{def.name}</h1>
      {def.description && <p className="text-sm text-slate-500 mb-4">{def.description}</p>}
      <form onSubmit={submit} className="space-y-3">
        {def.fields.map((f) => (
          <FieldInput key={f.key} field={f} value={values[f.key] ?? ""} onChange={set(f.key)} />
        ))}
        {error && <p className="text-sm text-red-600">{error}</p>}
        <button
          type="submit"
          disabled={submitting}
          className="w-full py-2.5 rounded-md bg-indigo-600 text-white text-sm font-medium disabled:opacity-50"
        >
          {submitting ? "กำลังส่ง…" : "ส่งคำขอ"}
        </button>
      </form>
    </div>
  );
}

function FieldInput({ field, value, onChange }) {
  const base =
    "w-full border border-slate-300 rounded-md px-3 py-2 text-sm bg-slate-50 text-slate-900 placeholder:text-slate-400";
  return (
    <div>
      <label className="block text-sm font-medium text-slate-700 mb-1">{field.label}</label>
      {field.type === "textarea" ? (
        <textarea rows={3} className={base} value={value} onChange={onChange} required={field.required} />
      ) : field.type === "select" ? (
        <select className={base} value={value} onChange={onChange} required={field.required}>
          {(field.options || []).map((o) => (
            <option key={o} value={o}>{o}</option>
          ))}
        </select>
      ) : (
        <input
          type={field.type === "number" ? "number" : "text"}
          className={base}
          value={value}
          onChange={onChange}
          required={field.required}
        />
      )}
    </div>
  );
}

function Centered({ children }) {
  return (
    <div className="min-h-screen bg-white flex items-center justify-center p-6">{children}</div>
  );
}
