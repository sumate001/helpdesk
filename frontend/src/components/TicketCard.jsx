import { Link } from "react-router-dom";
import StatusBadge from "./StatusBadge";
import PriorityBadge from "./PriorityBadge";
import SLATimer from "./SLATimer";

const ACCENT_BY_STATUS = {
  ai_answered: {
    line: "#2dd4bf",
    ring: "ring-teal-400/40",
    shadow: "shadow-[0_0_18px_rgba(45,212,191,0.18)] hover:shadow-[0_0_28px_rgba(45,212,191,0.35)]",
  },
  open: {
    line: "#60a5fa",
    ring: "ring-blue-400/40",
    shadow: "shadow-[0_0_18px_rgba(96,165,250,0.18)] hover:shadow-[0_0_28px_rgba(96,165,250,0.35)]",
  },
  pending_approval: {
    line: "#fbbf24",
    ring: "ring-amber-400/40",
    shadow: "shadow-[0_0_18px_rgba(251,191,36,0.18)] hover:shadow-[0_0_28px_rgba(251,191,36,0.35)]",
  },
  in_progress: {
    line: "#818cf8",
    ring: "ring-indigo-400/40",
    shadow: "shadow-[0_0_18px_rgba(129,140,248,0.22)] hover:shadow-[0_0_30px_rgba(129,140,248,0.4)]",
  },
  resolved: {
    line: "#4ade80",
    ring: "ring-green-400/40",
    shadow: "shadow-[0_0_18px_rgba(74,222,128,0.18)] hover:shadow-[0_0_28px_rgba(74,222,128,0.35)]",
  },
  closed: {
    line: "#94a3b8",
    ring: "ring-slate-400/30",
    shadow: "shadow-[0_0_12px_rgba(148,163,184,0.1)] hover:shadow-[0_0_20px_rgba(148,163,184,0.2)]",
  },
};

export default function TicketCard({ ticket }) {
  const accent = ACCENT_BY_STATUS[ticket.status] || ACCENT_BY_STATUS.closed;

  return (
    <Link
      to={`/tickets/${ticket.id}`}
      style={{ borderLeftColor: accent.line, borderLeftWidth: "5px" }}
      className={`group block glass rounded-xl p-4 ring-1 ${accent.ring} ${accent.shadow} hover:-translate-y-0.5 hover:ring-2 transition-all duration-200`}
    >
      <div className="flex items-center justify-between">
        <span className="font-mono text-xs text-slate-400 group-hover:text-cyan-300 transition-colors">
          {ticket.ticket_no}
        </span>
        <span className="text-xs px-2 py-0.5 rounded-md bg-white/5 text-slate-300 font-medium ring-1 ring-white/10">
          {ticket.type}
        </span>
      </div>
      <h3 className="font-semibold mt-2 truncate text-slate-100 group-hover:text-glow transition-colors">
        {ticket.title}
      </h3>
      <p className="text-sm text-slate-400 mt-1 truncate">
        {ticket.line_user?.known_name || ticket.reporter_name || "ไม่ระบุผู้แจ้ง"} · {ticket.category || "ไม่ระบุหมวด"}
      </p>
      <div className="flex items-center gap-2 mt-3 flex-wrap">
        <StatusBadge status={ticket.status} />
        <PriorityBadge priority={ticket.priority} />
        <span className="ml-auto">
          <SLATimer dueAt={ticket.sla_resolve_due_at} breached={ticket.sla_breached} />
        </span>
      </div>
    </Link>
  );
}
