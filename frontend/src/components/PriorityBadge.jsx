const MAP = {
  low: ["ต่ำ", "bg-slate-400/10 text-slate-300 ring-slate-400/30"],
  medium: ["กลาง", "bg-sky-400/10 text-sky-300 ring-sky-400/30"],
  high: ["สูง", "bg-orange-400/10 text-orange-300 ring-orange-400/30"],
  critical: ["วิกฤต", "bg-red-400/10 text-red-300 ring-red-400/30 animate-pulse-glow"],
};

export default function PriorityBadge({ priority }) {
  const [label, cls] = MAP[priority] || [priority, "bg-slate-400/10 text-slate-300 ring-slate-400/30"];
  return (
    <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium ring-1 ring-inset ${cls}`}>
      {label}
    </span>
  );
}
