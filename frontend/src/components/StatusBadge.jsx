const MAP = {
  ai_answered: ["AI ตอบแล้ว", "bg-teal-100 text-teal-700"],
  open: ["เปิด", "bg-blue-100 text-blue-700"],
  pending_approval: ["รออนุมัติ", "bg-amber-100 text-amber-700"],
  in_progress: ["กำลังดำเนินการ", "bg-indigo-100 text-indigo-700"],
  resolved: ["แก้ไขแล้ว", "bg-green-100 text-green-700"],
  closed: ["ปิด", "bg-slate-200 text-slate-600"],
};

export default function StatusBadge({ status }) {
  const [label, cls] = MAP[status] || [status, "bg-slate-100 text-slate-600"];
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${cls}`}>
      {label}
    </span>
  );
}
