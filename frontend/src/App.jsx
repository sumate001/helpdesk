import { Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./hooks/useAuth";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import TicketList from "./pages/TicketList";
import TicketDetail from "./pages/TicketDetail";
import Reports from "./pages/Reports";

function NavLink({ to, children }) {
  const { pathname } = useLocation();
  const active = pathname === to;
  return (
    <Link
      to={to}
      className={`px-3 py-2 rounded-md text-sm font-medium ${
        active ? "bg-indigo-600 text-white" : "text-slate-600 hover:bg-slate-200"
      }`}
    >
      {children}
    </Link>
  );
}

function Layout({ children }) {
  const { logout } = useAuth();
  return (
    <div className="min-h-screen">
      <header className="bg-white border-b border-slate-200">
        <div className="max-w-6xl mx-auto px-4 h-14 flex items-center gap-2">
          <span className="font-bold text-indigo-600 mr-4">IT Ticket</span>
          <NavLink to="/">ภาพรวม</NavLink>
          <NavLink to="/tickets">Tickets</NavLink>
          <NavLink to="/reports">รายงาน</NavLink>
          <button
            onClick={logout}
            className="ml-auto text-sm text-slate-500 hover:text-slate-800"
          >
            ออกจากระบบ
          </button>
        </div>
      </header>
      <main className="max-w-6xl mx-auto px-4 py-6">{children}</main>
    </div>
  );
}

function Protected({ children }) {
  const { isAuthenticated } = useAuth();
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return <Layout>{children}</Layout>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/" element={<Protected><Dashboard /></Protected>} />
      <Route path="/tickets" element={<Protected><TicketList /></Protected>} />
      <Route path="/tickets/:id" element={<Protected><TicketDetail /></Protected>} />
      <Route path="/reports" element={<Protected><Reports /></Protected>} />
    </Routes>
  );
}
