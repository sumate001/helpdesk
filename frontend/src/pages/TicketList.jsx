import { useState } from "react";
import { useTickets } from "../hooks/useTickets";
import TicketCard from "../components/TicketCard";

const STATUSES = ["", "ai_answered", "open", "pending_approval", "in_progress", "resolved", "closed"];
const PRIORITIES = ["", "low", "medium", "high", "critical"];

export default function TicketList() {
  const [status, setStatus] = useState("");
  const [priority, setPriority] = useState("");
  const { tickets, loading } = useTickets({ status, priority });

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Tickets ทั้งหมด</h1>
      <div className="flex gap-3">
        <select
          className="border border-slate-300 rounded-md p-2 text-sm"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        >
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {s || "ทุกสถานะ"}
            </option>
          ))}
        </select>
        <select
          className="border border-slate-300 rounded-md p-2 text-sm"
          value={priority}
          onChange={(e) => setPriority(e.target.value)}
        >
          {PRIORITIES.map((p) => (
            <option key={p} value={p}>
              {p || "ทุก priority"}
            </option>
          ))}
        </select>
      </div>

      {loading ? (
        <p className="text-slate-400">กำลังโหลด...</p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {tickets.map((t) => (
            <TicketCard key={t.id} ticket={t} />
          ))}
          {tickets.length === 0 && <p className="text-slate-400">ไม่พบ ticket</p>}
        </div>
      )}
    </div>
  );
}
