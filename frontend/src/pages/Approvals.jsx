import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api, { apiError } from "../api";

const TABS = [
  { key: "requests", label: "คำขออนุมัติ" },
  { key: "approvers", label: "ผังผู้อนุมัติ" },
];

const STATUS = {
  pending: { label: "รออนุมัติ", cls: "bg-amber-400/10 text-amber-300 ring-amber-400/30" },
  approved: { label: "อนุมัติแล้ว", cls: "bg-emerald-400/10 text-emerald-300 ring-emerald-400/30" },
  rejected: { label: "ไม่อนุมัติ", cls: "bg-red-400/10 text-red-300 ring-red-400/30" },
  expired: { label: "หมดอายุ", cls: "bg-slate-400/10 text-slate-300 ring-slate-400/30" },
  no_approver: { label: "ไม่มีผู้อนุมัติ", cls: "bg-red-400/10 text-red-300 ring-red-400/30" },
};

const EMPTY_APPROVER = {
  department: "",
  approver_emp_code: "",
  approver_name: "",
  approver_email: "",
  backup_emp_code: "",
  backup_name: "",
  note: "",
};

const Badge = ({ status }) => {
  const s = STATUS[status] || { label: status, cls: "bg-white/5 text-slate-300 ring-white/10" };
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full ring-1 ${s.cls}`}>{s.label}</span>
  );
};

export default function Approvals() {
  const [tab, setTab] = useState("requests");
  const [requests, setRequests] = useState([]);
  const [approvers, setApprovers] = useState([]);
  const [onlyPending, setOnlyPending] = useState(true);
  const [form, setForm] = useState(EMPTY_APPROVER);
  const [editingId, setEditingId] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const loadRequests = () =>
    api
      .get("/approvals", { params: onlyPending ? { status: "pending" } : {} })
      .then(({ data }) => setRequests(data));
  const loadApprovers = () =>
    api.get("/approvals/approvers").then(({ data }) => setApprovers(data));

  useEffect(() => {
    loadRequests().catch((err) => setError(apiError(err, "โหลดคำขอไม่ได้")));
  }, [onlyPending]);
  useEffect(() => {
    loadApprovers().catch((err) => setError(apiError(err, "โหลดผังผู้อนุมัติไม่ได้")));
  }, []);

  const decide = async (r, approve) => {
    const what = approve ? "อนุมัติ" : "ไม่อนุมัติ";
    const comment = window.prompt(`${what} ${r.ticket_no} — บันทึกเหตุผล (ไม่บังคับ)`, "");
    if (comment === null) return;
    setBusy(true);
    try {
      await api.post(`/approvals/${r.id}/decide`, { approve, comment: comment || null });
      await loadRequests();
    } catch (err) {
      setError(apiError(err, "บันทึกผลไม่สำเร็จ"));
    } finally {
      setBusy(false);
    }
  };

  const resend = async (r) => {
    setBusy(true);
    try {
      await api.post(`/approvals/${r.id}/resend`);
      setError("");
      await loadRequests();
    } catch (err) {
      setError(apiError(err, "ส่งซ้ำไม่สำเร็จ"));
    } finally {
      setBusy(false);
    }
  };

  const submitApprover = async (e) => {
    e.preventDefault();
    if (!form.department.trim() || !form.approver_emp_code.trim()) {
      setError("กรอกแผนกและรหัสพนักงานผู้อนุมัติด้วยครับ");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const payload = { ...form, is_confirmed: true };
      if (editingId) await api.patch(`/approvals/approvers/${editingId}`, payload);
      else await api.post("/approvals/approvers", payload);
      setForm(EMPTY_APPROVER);
      setEditingId(null);
      await loadApprovers();
    } catch (err) {
      setError(apiError(err, "บันทึกไม่สำเร็จ"));
    } finally {
      setBusy(false);
    }
  };

  const editApprover = (a) => {
    setEditingId(a.id);
    setForm({
      department: a.department,
      approver_emp_code: a.approver_emp_code || "",
      approver_name: a.approver_name || "",
      approver_email: a.approver_email || "",
      backup_emp_code: a.backup_emp_code || "",
      backup_name: a.backup_name || "",
      note: a.note || "",
    });
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const invite = async (a) => {
    setBusy(true);
    try {
      await api.post(`/approvals/approvers/${a.id}/invite`);
      setError("");
      await loadApprovers();
    } catch (err) {
      setError(apiError(err, "ส่งการ์ดแจ้งไม่สำเร็จ"));
    } finally {
      setBusy(false);
    }
  };

  const confirmApprover = async (a) => {
    await api.patch(`/approvals/approvers/${a.id}`, { is_confirmed: true });
    loadApprovers();
  };

  const removeApprover = async (a) => {
    if (!window.confirm(`ลบผู้อนุมัติของแผนก "${a.department}" ?`)) return;
    await api.delete(`/approvals/approvers/${a.id}`);
    if (editingId === a.id) {
      setEditingId(null);
      setForm(EMPTY_APPROVER);
    }
    loadApprovers();
  };

  const pendingCount = requests.filter((r) => r.status === "pending").length;
  const unconfirmed = approvers.filter((a) => !a.is_confirmed).length;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-glow">การอนุมัติ</h1>
        <span className="text-sm text-slate-500">
          {tab === "requests" ? `รออนุมัติ ${pendingCount} รายการ` : `${approvers.length} แผนก`}
        </span>
      </div>

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
            {t.key === "approvers" && unconfirmed > 0 && (
              <span className="ml-2 text-xs bg-amber-400/10 text-amber-300 ring-1 ring-amber-400/30 px-1.5 py-0.5 rounded-full">
                {unconfirmed} รอยืนยัน
              </span>
            )}
          </button>
        ))}
      </div>

      {error && <p className="text-sm text-red-400">{error}</p>}

      {/* ── คำขออนุมัติ ── */}
      {tab === "requests" && (
        <div className="space-y-3">
          <label className="flex items-center gap-2 text-sm text-slate-400">
            <input
              type="checkbox"
              checked={onlyPending}
              onChange={(e) => setOnlyPending(e.target.checked)}
            />
            แสดงเฉพาะที่ยังรออนุมัติ
          </label>

          <div className="glass rounded-xl divide-y divide-white/10">
            {requests.length === 0 && (
              <p className="p-6 text-center text-sm text-slate-500">ไม่มีคำขอในหมวดนี้</p>
            )}
            {requests.map((r) => (
              <div key={r.id} className="p-4 flex items-start gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <Link
                      to={`/tickets/${r.ticket_id}`}
                      className="font-medium text-indigo-300 hover:underline"
                    >
                      {r.ticket_no}
                    </Link>
                    <Badge status={r.status} />
                    {!r.line_linked && r.status === "pending" && (
                      <span className="text-xs bg-red-400/10 text-red-300 ring-1 ring-red-400/30 px-2 py-0.5 rounded-full">
                        ผู้อนุมัติยังไม่ผูก LINE
                      </span>
                    )}
                    {r.approver_from_requester && (
                      <span className="text-xs bg-amber-400/10 text-amber-300 ring-1 ring-amber-400/30 px-2 py-0.5 rounded-full">
                        ผู้ขอเลือกเอง — ควรตรวจ
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-slate-200 mt-1">{r.title}</p>
                  <p className="text-xs text-slate-500 mt-1">
                    ผู้ขอ: {r.requester || "-"} · ผู้อนุมัติ:{" "}
                    {r.approver_name || r.approver_emp_code || "— ยังไม่มี —"} ·{" "}
                    {new Date(r.created_at).toLocaleString("th-TH")}
                  </p>
                  {r.comment && (
                    <p className="text-xs text-slate-400 mt-1">เหตุผล: {r.comment}</p>
                  )}
                </div>
                {(r.status === "pending" || r.status === "no_approver") && (
                  <div className="flex flex-col gap-1 text-sm shrink-0">
                    <button
                      disabled={busy}
                      onClick={() => decide(r, true)}
                      className="text-emerald-300 hover:text-emerald-200 hover:underline"
                    >
                      อนุมัติแทน
                    </button>
                    <button
                      disabled={busy}
                      onClick={() => decide(r, false)}
                      className="text-red-400 hover:text-red-300 hover:underline"
                    >
                      ไม่อนุมัติ
                    </button>
                    <button
                      disabled={busy}
                      onClick={() => resend(r)}
                      className="text-slate-400 hover:text-slate-200 hover:underline"
                    >
                      ส่งซ้ำ
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── ผังผู้อนุมัติ ── */}
      {tab === "approvers" && (
        <div className="space-y-4">
          <p className="text-sm text-slate-400">
            ระบบพนักงานไม่มีสายบังคับบัญชา จึงต้องกำหนดที่นี่ว่าแต่ละแผนกใครเป็นผู้อนุมัติ —
            เมื่อเพิ่ม/เปลี่ยนตัว ระบบจะส่งการ์ดทาง LINE ให้เจ้าตัวกด “ยอมรับ” เองก่อน
            (ผู้อนุมัติต้องผูก LINE กับระบบด้วยการทักบอทแล้วส่งรหัสพนักงาน)
          </p>

          <form onSubmit={submitApprover} className="glass rounded-xl p-4 space-y-3">
            <h2 className="font-semibold text-slate-100">
              {editingId ? "แก้ไขผู้อนุมัติ" : "เพิ่มผู้อนุมัติของแผนก"}
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <input
                className="input-dark rounded-lg px-3 py-2 text-sm"
                placeholder="แผนก (ตรงกับใน Employee DB)"
                value={form.department}
                disabled={!!editingId}
                onChange={(e) => setForm({ ...form, department: e.target.value })}
              />
              <input
                className="input-dark rounded-lg px-3 py-2 text-sm"
                placeholder="รหัสพนักงานผู้อนุมัติ"
                value={form.approver_emp_code}
                onChange={(e) => setForm({ ...form, approver_emp_code: e.target.value })}
              />
              <input
                className="input-dark rounded-lg px-3 py-2 text-sm"
                placeholder="ชื่อผู้อนุมัติ"
                value={form.approver_name}
                onChange={(e) => setForm({ ...form, approver_name: e.target.value })}
              />
              <input
                className="input-dark rounded-lg px-3 py-2 text-sm"
                placeholder="อีเมลผู้อนุมัติ (เผื่อใช้ในเฟสถัดไป)"
                value={form.approver_email}
                onChange={(e) => setForm({ ...form, approver_email: e.target.value })}
              />
              <input
                className="input-dark rounded-lg px-3 py-2 text-sm"
                placeholder="รหัสพนักงานผู้อนุมัติสำรอง"
                value={form.backup_emp_code}
                onChange={(e) => setForm({ ...form, backup_emp_code: e.target.value })}
              />
              <input
                className="input-dark rounded-lg px-3 py-2 text-sm"
                placeholder="ชื่อผู้อนุมัติสำรอง"
                value={form.backup_name}
                onChange={(e) => setForm({ ...form, backup_name: e.target.value })}
              />
            </div>
            <div className="flex gap-2">
              <button
                type="submit"
                disabled={busy}
                className="btn-primary text-sm px-4 py-2 rounded-lg font-medium"
              >
                {editingId ? "บันทึกการแก้ไข" : "เพิ่ม"}
              </button>
              {editingId && (
                <button
                  type="button"
                  onClick={() => {
                    setEditingId(null);
                    setForm(EMPTY_APPROVER);
                  }}
                  className="text-sm px-4 py-2 rounded-lg text-slate-400 hover:bg-white/5 hover:text-slate-200"
                >
                  ยกเลิก
                </button>
              )}
            </div>
          </form>

          <div className="glass rounded-xl divide-y divide-white/10">
            {approvers.length === 0 && (
              <p className="p-6 text-center text-sm text-slate-500">
                ยังไม่มีผังผู้อนุมัติ — คำขอที่ต้องอนุมัติจะเด้งให้ทีม IT ตามเอง
              </p>
            )}
            {approvers.map((a) => (
              <div key={a.id} className="p-4 flex items-start gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-medium text-slate-100">{a.department}</span>
                    {!a.is_confirmed && (
                      <span className="text-xs bg-amber-400/10 text-amber-300 ring-1 ring-amber-400/30 px-2 py-0.5 rounded-full">
                        รอ IT ยืนยัน
                      </span>
                    )}
                    <span
                      className={`text-xs px-2 py-0.5 rounded-full ring-1 ${
                        a.line_linked
                          ? "bg-emerald-400/10 text-emerald-300 ring-emerald-400/30"
                          : "bg-red-400/10 text-red-300 ring-red-400/30"
                      }`}
                    >
                      {a.line_linked ? "ผูก LINE แล้ว" : "ยังไม่ผูก LINE"}
                    </span>
                    <span
                      className={`text-xs px-2 py-0.5 rounded-full ring-1 ${
                        a.accepted
                          ? "bg-emerald-400/10 text-emerald-300 ring-emerald-400/30"
                          : "bg-slate-400/10 text-slate-300 ring-slate-400/30"
                      }`}
                    >
                      {a.accepted ? "เจ้าตัวยอมรับแล้ว" : "รอเจ้าตัวกดยอมรับ"}
                    </span>
                  </div>
                  <p className="text-sm text-slate-400 mt-1">
                    {a.approver_name || "-"} ({a.approver_emp_code})
                    {a.backup_emp_code && ` · สำรอง: ${a.backup_name || a.backup_emp_code}`}
                  </p>
                  {!a.line_linked && (
                    <p className="text-xs text-amber-300/80 mt-1">
                      เจ้าตัวยังไม่ได้ผูก LINE — ให้ทักบอทแล้วส่งรหัสพนักงาน ({a.approver_emp_code})
                      ครั้งเดียว จากนั้นกด “ส่งการ์ดให้ยอมรับ” ได้เลย
                    </p>
                  )}
                </div>
                <div className="flex flex-col gap-1 text-sm shrink-0">
                  {!a.accepted && (
                    <button
                      disabled={busy}
                      onClick={() => invite(a)}
                      className="text-sky-300 hover:text-sky-200 hover:underline"
                      title={
                        a.line_linked
                          ? "ส่งการ์ดให้เจ้าตัวกดยอมรับอีกครั้ง"
                          : "เจ้าตัวยังไม่ผูก LINE — กดแล้วจะขึ้นเหตุผล"
                      }
                    >
                      ส่งการ์ดให้ยอมรับ
                    </button>
                  )}
                  {!a.is_confirmed && (
                    <button
                      onClick={() => confirmApprover(a)}
                      className="text-emerald-300 hover:text-emerald-200 hover:underline"
                    >
                      ยืนยัน
                    </button>
                  )}
                  <button
                    onClick={() => editApprover(a)}
                    className="text-indigo-300 hover:text-indigo-200 hover:underline"
                  >
                    แก้ไข
                  </button>
                  <button
                    onClick={() => removeApprover(a)}
                    className="text-red-400 hover:text-red-300 hover:underline"
                  >
                    ลบ
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
