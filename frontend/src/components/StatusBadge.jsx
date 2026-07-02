const MAP = {
  ai_answered: ["AI ตอบแล้ว", "bg-teal-400/10 text-teal-300 ring-teal-400/30", "bg-teal-400", "shadow-[0_0_8px_rgba(45,212,191,0.7)]"],
  open: ["เปิด", "bg-blue-400/10 text-blue-300 ring-blue-400/30", "bg-blue-400", "shadow-[0_0_8px_rgba(96,165,250,0.7)]"],
  pending_approval: ["รออนุมัติ", "bg-amber-400/10 text-amber-300 ring-amber-400/30", "bg-amber-400", "shadow-[0_0_8px_rgba(251,191,36,0.7)]"],
  in_progress: ["กำลังดำเนินการ", "bg-indigo-400/10 text-indigo-300 ring-indigo-400/30", "bg-indigo-400", "shadow-[0_0_8px_rgba(129,140,248,0.7)]"],
  resolved: ["แก้ไขแล้ว", "bg-green-400/10 text-green-300 ring-green-400/30", "bg-green-400", "shadow-[0_0_8px_rgba(74,222,128,0.7)]"],
  closed: ["ปิด", "bg-slate-400/10 text-slate-300 ring-slate-400/30", "bg-slate-400", ""],
};

export default function StatusBadge({ status }) {
  const [label, cls, dot, glow] = MAP[status] || [status, "bg-slate-400/10 text-slate-300 ring-slate-400/30", "bg-slate-400", ""];
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ring-1 ring-inset ${cls}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${dot} ${glow}`} />
      {label}
    </span>
  );
}
