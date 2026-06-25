import { Link } from "react-router-dom";
import StatusBadge from "./StatusBadge";
import PriorityBadge from "./PriorityBadge";
import SLATimer from "./SLATimer";

export default function TicketCard({ ticket }) {
  return (
    <Link
      to={`/tickets/${ticket.id}`}
      className="block bg-white rounded-lg shadow-sm hover:shadow-md transition p-4 border border-slate-200"
    >
      <div className="flex items-center justify-between">
        <span className="font-mono text-xs text-slate-500">{ticket.ticket_no}</span>
        <span className="text-xs px-1.5 py-0.5 rounded bg-slate-100 text-slate-600">
          {ticket.type}
        </span>
      </div>
      <h3 className="font-medium mt-1 truncate">{ticket.title}</h3>
      <p className="text-sm text-slate-500 mt-1">
        {ticket.line_user?.display_name || "ไม่ระบุผู้แจ้ง"} · {ticket.category}
      </p>
      <div className="flex items-center gap-2 mt-3">
        <StatusBadge status={ticket.status} />
        <PriorityBadge priority={ticket.priority} />
        <span className="ml-auto">
          <SLATimer dueAt={ticket.sla_resolve_due_at} breached={ticket.sla_breached} />
        </span>
      </div>
    </Link>
  );
}
