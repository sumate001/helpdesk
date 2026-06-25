import { useState } from "react";
import api from "../api";

export function useAuth() {
  const [token, setToken] = useState(() => localStorage.getItem("access_token"));

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
  }

  return { token, isAuthenticated: !!token, login, logout };
}
