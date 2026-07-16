import { useEffect, useState } from "react";
import api from "../api";

export function useAuth() {
  const [token, setToken] = useState(() => localStorage.getItem("access_token"));
  const [user, setUser] = useState(null);
  const [loadingUser, setLoadingUser] = useState(!!token);

  // โหลดข้อมูลผู้ใช้ที่ล็อกอินอยู่ (รวม role) เพื่อตัดสินเมนู/สิทธิ์ฝั่ง UI
  useEffect(() => {
    if (!token) {
      setUser(null);
      setLoadingUser(false);
      return;
    }
    let active = true;
    setLoadingUser(true);
    api
      .get("/auth/me")
      .then(({ data }) => active && setUser(data))
      .catch(() => active && setUser(null))
      .finally(() => active && setLoadingUser(false));
    return () => {
      active = false;
    };
  }, [token]);

  async function login(username, password) {
    const { data } = await api.post("/auth/login", { username, password });
    localStorage.setItem("access_token", data.access_token);
    localStorage.setItem("refresh_token", data.refresh_token);
    setToken(data.access_token);
    return data;
  }

  function logout() {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    setToken(null);
    setUser(null);
    // useAuth ถูกเรียกหลาย instance (state แยกกัน) — reload เต็มหน้าไป /login
    // เพื่อล้าง state ทั้งหมดให้ชัวร์ (แนวเดียวกับที่ api.js ทำตอนเจอ 401)
    window.location.href = "/login";
  }

  return {
    token,
    isAuthenticated: !!token,
    user,
    isAdmin: user?.role === "admin",
    loadingUser,
    login,
    logout,
  };
}
