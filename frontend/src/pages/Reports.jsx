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

const COLORS = ["#818cf8", "#4ade80", "#fbbf24", "#f87171", "#38bdf8", "#c084fc"];

function toData(obj = {}) {
  return Object.entries(obj).map(([name, value]) => ({ name, value }));
}

function AxisTick({ x, y, payload }) {
  return (
    <text
      x={x}
      y={y}
      dy={12}
      textAnchor="end"
      fill="#cbd5e1"
      fontSize={12}
      transform={`rotate(-35, ${x}, ${y})`}
    >
      {payload.value}
    </text>
  );
}

function YTick({ x, y, payload }) {
  return (
    <text x={x} y={y} dy={4} textAnchor="end" fill="#cbd5e1" fontSize={12}>
      {payload.value}
    </text>
  );
}

function PieLabel({ cx, cy, midAngle, outerRadius, name, percent }) {
  const RADIAN = Math.PI / 180;
  const radius = outerRadius + 18;
  const x = cx + radius * Math.cos(-midAngle * RADIAN);
  const y = cy + radius * Math.sin(-midAngle * RADIAN);
  return (
    <text
      x={x}
      y={y}
      fill="#e2e8f0"
      fontSize={12}
      textAnchor={x > cx ? "start" : "end"}
      dominantBaseline="central"
    >
      {`${name} ${(percent * 100).toFixed(0)}%`}
    </text>
  );
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
      <h1 className="text-2xl font-bold text-glow">รายงาน & สถิติ</h1>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="glass rounded-xl p-4 hover:-translate-y-0.5 hover:shadow-[0_0_24px_rgba(248,113,113,0.2)] transition-all duration-200">
          <p className="text-sm text-slate-400">SLA Breach Rate</p>
          <p className="text-2xl font-bold text-red-400">
            {sla ? `${sla.breach_rate_pct}%` : "-"}
          </p>
          <p className="text-xs text-slate-500">
            {sla ? `${sla.breached}/${sla.total} tickets` : ""}
          </p>
        </div>
        <div className="glass rounded-xl p-4 hover:-translate-y-0.5 hover:shadow-[0_0_24px_rgba(129,140,248,0.25)] transition-all duration-200">
          <p className="text-sm text-slate-400">เวลาแก้เฉลี่ย</p>
          <p className="text-2xl font-bold text-indigo-300">
            {resolution ? `${resolution.avg_resolution_minutes} นาที` : "-"}
          </p>
        </div>
        <div className="glass rounded-xl p-4 hover:-translate-y-0.5 transition-all duration-200">
          <p className="text-sm text-slate-400">Ticket ทั้งหมด</p>
          <p className="text-2xl font-bold text-slate-100">{summary?.total ?? "-"}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="glass rounded-xl p-4">
          <h2 className="font-semibold mb-3 text-slate-100">ตามหมวดหมู่</h2>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={toData(summary?.by_category)} margin={{ bottom: 24 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" />
              <XAxis
                dataKey="name"
                stroke="rgba(226,232,240,0.4)"
                tick={<AxisTick />}
                interval={0}
                height={60}
              />
              <YAxis allowDecimals={false} stroke="rgba(226,232,240,0.4)" tick={<YTick />} />
              <Tooltip
                cursor={{ fill: "rgba(255,255,255,0.06)" }}
                contentStyle={{
                  background: "rgba(15,23,42,0.95)",
                  border: "1px solid rgba(255,255,255,0.1)",
                  borderRadius: 8,
                }}
                labelStyle={{ color: "#e2e8f0" }}
                itemStyle={{ color: "#e2e8f0" }}
              />
              <Bar dataKey="value" fill="#818cf8" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="glass rounded-xl p-4">
          <h2 className="font-semibold mb-3 text-slate-100">ตามสถานะ</h2>
          <ResponsiveContainer width="100%" height={260}>
            <PieChart>
              <Pie
                data={toData(summary?.by_status)}
                dataKey="value"
                nameKey="name"
                outerRadius={90}
                label={<PieLabel />}
              >
                {toData(summary?.by_status).map((_, i) => (
                  <Cell key={i} fill={COLORS[i % COLORS.length]} stroke="rgba(5,8,20,0.6)" />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{
                  background: "rgba(15,23,42,0.95)",
                  border: "1px solid rgba(255,255,255,0.1)",
                  borderRadius: 8,
                }}
                labelStyle={{ color: "#e2e8f0" }}
                itemStyle={{ color: "#e2e8f0" }}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
