import { useEffect, useState } from "react";
import { useTickets } from "../hooks/useTickets";
import TicketCard from "../components/TicketCard";

const STATUS_OPTIONS = [
  { value: "", label: "ทุกสถานะ" },
  { value: "ai_answered", label: "AI ตอบแล้ว" },
  { value: "open", label: "เปิด" },
  { value: "pending_approval", label: "รออนุมัติ" },
  { value: "in_progress", label: "กำลังดำเนินการ" },
  { value: "resolved", label: "แก้ไขแล้ว" },
  { value: "closed", label: "ปิด" },
];

const PRIORITY_OPTIONS = [
  { value: "", label: "ทุก priority" },
  { value: "low", label: "ต่ำ" },
  { value: "medium", label: "กลาง" },
  { value: "high", label: "สูง" },
  { value: "critical", label: "วิกฤต" },
];

function Chip({ active, onClick, children }) {
  return (
    <button
      onClick={onClick}
      className={`px-3 py-1.5 rounded-full text-sm font-medium whitespace-nowrap transition-all duration-150 ${
        active
          ? "bg-gradient-to-br from-indigo-500 to-fuchsia-500 text-white shadow-[0_0_14px_rgba(129,140,248,0.5)]"
          : "bg-white/5 text-slate-300 ring-1 ring-white/10 hover:bg-white/10 hover:text-white"
      }`}
    >
      {children}
    </button>
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

export default function TicketList() {
  const [status, setStatus] = useState("");
  const [priority, setPriority] = useState("");
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");

  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search.trim()), 300);
    return () => clearTimeout(t);
  }, [search]);

  const { tickets, loading } = useTickets({
    status,
    priority,
    q: debouncedSearch,
  });

  const hasFilters = status || priority || debouncedSearch;

  function clearFilters() {
    setStatus("");
    setPriority("");
    setSearch("");
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-glow">Tickets ทั้งหมด</h1>
        {!loading && (
          <span className="text-sm text-slate-500">{tickets.length} รายการ</span>
        )}
      </div>

      <div className="glass-strong rounded-xl p-4 space-y-3 sticky top-2 z-10">
        <div className="relative">
          <svg
            className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M21 21l-4.35-4.35M17 11a6 6 0 11-12 0 6 6 0 0112 0z"
            />
          </svg>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="ค้นหา ticket, หัวข้อ, รายละเอียด หรือชื่อผู้แจ้ง..."
            className="w-full pl-9 pr-9 py-2.5 rounded-lg bg-white/5 text-slate-100 placeholder:text-slate-500 ring-1 ring-white/10 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400/70 focus:shadow-[0_0_16px_rgba(129,140,248,0.3)] transition-shadow"
          />
          {search && (
            <button
              onClick={() => setSearch("")}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-200"
              aria-label="ล้างคำค้นหา"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          )}
        </div>

        <div className="flex gap-2 overflow-x-auto pb-1">
          {STATUS_OPTIONS.map((o) => (
            <Chip key={o.value} active={status === o.value} onClick={() => setStatus(o.value)}>
              {o.label}
            </Chip>
          ))}
        </div>
        <div className="flex items-center gap-2 overflow-x-auto pb-1">
          {PRIORITY_OPTIONS.map((o) => (
            <Chip key={o.value} active={priority === o.value} onClick={() => setPriority(o.value)}>
              {o.label}
            </Chip>
          ))}
          {hasFilters && (
            <button
              onClick={clearFilters}
              className="ml-auto text-xs text-slate-500 hover:text-fuchsia-300 whitespace-nowrap transition-colors"
            >
              ล้างตัวกรองทั้งหมด
            </button>
          )}
        </div>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      ) : tickets.length === 0 ? (
        <div className="glass rounded-xl p-12 text-center">
          <p className="text-slate-400">ไม่พบ ticket ที่ตรงกับเงื่อนไข</p>
          {hasFilters && (
            <button
              onClick={clearFilters}
              className="mt-3 text-sm text-indigo-300 hover:text-fuchsia-300 font-medium"
            >
              ล้างตัวกรองทั้งหมด
            </button>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {tickets.map((t) => (
            <TicketCard key={t.id} ticket={t} />
          ))}
        </div>
      )}
    </div>
  );
}
