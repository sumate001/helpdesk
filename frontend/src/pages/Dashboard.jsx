import { useEffect, useState } from "react";
import api from "../api";
import { useTickets } from "../hooks/useTickets";
import TicketCard from "../components/TicketCard";

function StatCard({ label, value, color, glow }) {
  return (
    <div className={`glass rounded-xl p-4 hover:-translate-y-0.5 transition-all duration-200 ${glow}`}>
      <p className="text-sm text-slate-400">{label}</p>
      <p className={`text-3xl font-bold mt-1 ${color}`}>{value}</p>
      <div className={`h-0.5 w-10 rounded-full mt-3 bg-gradient-to-r ${color === "text-slate-100" ? "from-slate-400 to-slate-600" : "opacity-0"}`} />
    </div>
  );
}

function SkeletonCard() {
  return (
    <div className="glass rounded-xl p-4 animate-pulse">
      <div className="flex justify-between">
        <div className="h-3 w-24 bg-white/10 rounded" />
        <div className="h-4 w-8 bg-white/10 rounded" />
      </div>
      <div className="h-4 w-3/4 bg-white/10 rounded mt-3" />
      <div className="h-3 w-1/2 bg-white/10 rounded mt-2" />
      <div className="flex gap-2 mt-4">
        <div className="h-5 w-16 bg-white/10 rounded-full" />
        <div className="h-5 w-12 bg-white/10 rounded-full" />
      </div>
    </div>
  );
}

export default function Dashboard() {
  const [summary, setSummary] = useState(null);
  const { tickets, loading } = useTickets({ status: "open" });

  useEffect(() => {
    api.get("/reports/summary").then(({ data }) => setSummary(data));
  }, []);

  const s = summary?.by_status || {};

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-glow">ภาพรวม</h1>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="ทั้งหมด" value={summary?.total ?? "-"} color="text-slate-100" glow="" />
        <StatCard
          label="เปิดอยู่"
          value={s.open ?? 0}
          color="text-blue-300"
          glow="hover:shadow-[0_0_24px_rgba(96,165,250,0.2)]"
        />
        <StatCard
          label="กำลังดำเนินการ"
          value={s.in_progress ?? 0}
          color="text-indigo-300"
          glow="hover:shadow-[0_0_24px_rgba(129,140,248,0.25)]"
        />
        <StatCard
          label="แก้ไขแล้ว"
          value={s.resolved ?? 0}
          color="text-green-300"
          glow="hover:shadow-[0_0_24px_rgba(74,222,128,0.2)]"
        />
      </div>

      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold text-slate-100">Ticket ที่เปิดอยู่</h2>
          {!loading && <span className="text-sm text-slate-500">{tickets.length} รายการ</span>}
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {loading ? (
            Array.from({ length: 3 }).map((_, i) => <SkeletonCard key={i} />)
          ) : (
            <>
              {tickets.map((t) => (
                <TicketCard key={t.id} ticket={t} />
              ))}
              {tickets.length === 0 && (
                <div className="col-span-full glass rounded-xl p-10 text-center text-slate-400">
                  ไม่มี ticket ที่เปิดอยู่ 🎉
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
