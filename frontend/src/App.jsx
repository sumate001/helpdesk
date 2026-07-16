import { Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./hooks/useAuth";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import TicketList from "./pages/TicketList";
import TicketDetail from "./pages/TicketDetail";
import Reports from "./pages/Reports";
import KnowledgeBase from "./pages/KnowledgeBase";
import Settings from "./pages/Settings";
import Users from "./pages/Users";
import Profile from "./pages/Profile";
import ServiceForm from "./pages/ServiceForm";

function NavLink({ to, children }) {
  const { pathname } = useLocation();
  const active = pathname === to;
  return (
    <Link
      to={to}
      className={`relative px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
        active
          ? "text-white bg-gradient-to-br from-indigo-500/90 to-fuchsia-500/80 shadow-[0_0_16px_rgba(129,140,248,0.55)]"
          : "text-slate-300 hover:text-white hover:bg-white/5"
      }`}
    >
      {children}
    </Link>
  );
}

function Layout({ children }) {
  const { logout, isAdmin } = useAuth();
  return (
    <div className="min-h-screen">
      <header className="glass sticky top-0 z-20 shadow-[0_1px_0_rgba(255,255,255,0.06)]">
        <div className="max-w-6xl mx-auto px-4 h-14 flex items-center gap-1">
          <span className="font-bold text-lg text-glow mr-4 tracking-wide">
            IT TICKET
          </span>
          <NavLink to="/">ภาพรวม</NavLink>
          <NavLink to="/tickets">Tickets</NavLink>
          <NavLink to="/reports">รายงาน</NavLink>
          {/* หน้าตั้งค่า/จัดการ เฉพาะ admin — staff ไม่ต้องเข้ามายุ่ง */}
          {isAdmin && <NavLink to="/kb">คลังความรู้</NavLink>}
          {isAdmin && <NavLink to="/users">เจ้าหน้าที่</NavLink>}
          {isAdmin && <NavLink to="/settings">ตั้งค่า</NavLink>}
          <NavLink to="/profile">โปรไฟล์</NavLink>
          <button
            onClick={logout}
            className="ml-auto text-sm text-slate-400 hover:text-fuchsia-300 transition-colors"
          >
            ออกจากระบบ
          </button>
        </div>
      </header>
      <main className="max-w-6xl mx-auto px-4 py-6 animate-fadein">{children}</main>
    </div>
  );
}

function Protected({ children }) {
  const { isAuthenticated } = useAuth();
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return <Layout>{children}</Layout>;
}

// หน้าเฉพาะ admin — staff ที่พยายามเข้า (พิมพ์ URL ตรง) เด้งกลับหน้าแรก
function AdminOnly({ children }) {
  const { isAuthenticated, isAdmin, loadingUser } = useAuth();
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  if (loadingUser)
    return (
      <Layout>
        <p className="text-slate-500">กำลังโหลด...</p>
      </Layout>
    );
  if (!isAdmin) return <Navigate to="/" replace />;
  return <Layout>{children}</Layout>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/liff/form" element={<ServiceForm />} />
      <Route path="/" element={<Protected><Dashboard /></Protected>} />
      <Route path="/tickets" element={<Protected><TicketList /></Protected>} />
      <Route path="/tickets/:id" element={<Protected><TicketDetail /></Protected>} />
      <Route path="/reports" element={<Protected><Reports /></Protected>} />
      <Route path="/profile" element={<Protected><Profile /></Protected>} />
      <Route path="/kb" element={<AdminOnly><KnowledgeBase /></AdminOnly>} />
      <Route path="/users" element={<AdminOnly><Users /></AdminOnly>} />
      <Route path="/settings" element={<AdminOnly><Settings /></AdminOnly>} />
    </Routes>
  );
}
