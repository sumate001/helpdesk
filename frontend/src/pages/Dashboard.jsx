import { useEffect, useState } from "react";
import api from "../api";
import { useTickets } from "../hooks/useTickets";
import TicketCard from "../components/TicketCard";

function StatCard({ label, value, color }) {
  return (
    <div className="bg-white rounded-lg shadow-sm p-4 border border-slate-200">
      <p className="text-sm text-slate-500">{label}</p>
      <p className={`text-2xl font-bold ${color}`}>{value}</p>
    </div>
  );
}

export default function Dashboard() {
  const [summary, setSummary] = useState(null);
  const { tickets } = useTickets({ status: "open" });

  useEffect(() => {
    api.get("/reports/summary").then(({ data }) => setSummary(data));
  }, []);

  const s = summary?.by_status || {};

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">ภาพรวม</h1>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="ทั้งหมด" value={summary?.total ?? "-"} color="text-slate-800" />
        <StatCard label="เปิดอยู่" value={s.open ?? 0} color="text-blue-600" />
        <StatCard
          label="กำลังดำเนินการ"
          value={s.in_progress ?? 0}
          color="text-indigo-600"
        />
        <StatCard label="แก้ไขแล้ว" value={s.resolved ?? 0} color="text-green-600" />
      </div>

      <div>
        <h2 className="text-lg font-semibold mb-3">Ticket ที่เปิดอยู่</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {tickets.map((t) => (
            <TicketCard key={t.id} ticket={t} />
          ))}
          {tickets.length === 0 && (
            <p className="text-slate-400">ไม่มี ticket ที่เปิดอยู่</p>
          )}
        </div>
      </div>
    </div>
  );
}
