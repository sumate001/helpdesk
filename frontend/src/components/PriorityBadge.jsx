const MAP = {
  low: ["ต่ำ", "bg-slate-100 text-slate-600"],
  medium: ["กลาง", "bg-sky-100 text-sky-700"],
  high: ["สูง", "bg-orange-100 text-orange-700"],
  critical: ["วิกฤต", "bg-red-100 text-red-700"],
};

export default function PriorityBadge({ priority }) {
  const [label, cls] = MAP[priority] || [priority, "bg-slate-100 text-slate-600"];
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${cls}`}>
      {label}
    </span>
  );
}
