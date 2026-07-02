export default function SLATimer({ dueAt, breached }) {
  if (breached) {
    return <span className="text-red-400 text-xs font-semibold">เกิน SLA</span>;
  }
  if (!dueAt) return <span className="text-slate-500 text-xs">-</span>;

  const diffMin = Math.round((new Date(dueAt) - new Date()) / 60000);
  if (diffMin < 0) {
    return <span className="text-red-400 text-xs font-semibold">เกินกำหนด</span>;
  }
  const cls = diffMin < 30 ? "text-orange-400" : "text-slate-400";
  const text =
    diffMin >= 60 ? `${Math.floor(diffMin / 60)} ชม. ${diffMin % 60} นาที` : `${diffMin} นาที`;
  return <span className={`text-xs ${cls}`}>เหลือ {text}</span>;
}
