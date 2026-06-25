import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import api from "../api";

const COLORS = ["#6366f1", "#22c55e", "#f59e0b", "#ef4444", "#0ea5e9", "#8b5cf6"];

function toData(obj = {}) {
  return Object.entries(obj).map(([name, value]) => ({ name, value }));
}

export default function Reports() {
  const [summary, setSummary] = useState(null);
  const [sla, setSla] = useState(null);
  const [resolution, setResolution] = useState(null);

  useEffect(() => {
    api.get("/reports/summary").then(({ data }) => setSummary(data));
    api.get("/reports/sla").then(({ data }) => setSla(data));
    api.get("/reports/resolution-time").then(({ data }) => setResolution(data));
  }, []);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">รายงาน & สถิติ</h1>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-white rounded-lg shadow-sm p-4 border border-slate-200">
          <p className="text-sm text-slate-500">SLA Breach Rate</p>
          <p className="text-2xl font-bold text-red-600">
            {sla ? `${sla.breach_rate_pct}%` : "-"}
          </p>
          <p className="text-xs text-slate-400">
            {sla ? `${sla.breached}/${sla.total} tickets` : ""}
          </p>
        </div>
        <div className="bg-white rounded-lg shadow-sm p-4 border border-slate-200">
          <p className="text-sm text-slate-500">เวลาแก้เฉลี่ย</p>
          <p className="text-2xl font-bold text-indigo-600">
            {resolution ? `${resolution.avg_resolution_minutes} นาที` : "-"}
          </p>
        </div>
        <div className="bg-white rounded-lg shadow-sm p-4 border border-slate-200">
          <p className="text-sm text-slate-500">Ticket ทั้งหมด</p>
          <p className="text-2xl font-bold">{summary?.total ?? "-"}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-white rounded-lg shadow-sm p-4 border border-slate-200">
          <h2 className="font-semibold mb-3">ตามหมวดหมู่</h2>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={toData(summary?.by_category)}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" />
              <YAxis allowDecimals={false} />
              <Tooltip />
              <Bar dataKey="value" fill="#6366f1" />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="bg-white rounded-lg shadow-sm p-4 border border-slate-200">
          <h2 className="font-semibold mb-3">ตามสถานะ</h2>
          <ResponsiveContainer width="100%" height={260}>
            <PieChart>
              <Pie
                data={toData(summary?.by_status)}
                dataKey="value"
                nameKey="name"
                outerRadius={90}
                label
              >
                {toData(summary?.by_status).map((_, i) => (
                  <Cell key={i} fill={COLORS[i % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
