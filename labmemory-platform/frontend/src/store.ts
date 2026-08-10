import { create } from "zustand";
import type { User } from "./types";
import { clearToken, getStoredUser, getToken, setToken } from "./api";

interface AuthState {
  user: User | null;
  token: string;
  setAuth: (token: string, user: User) => void;
  logout: () => void;
  hydrated: boolean;
  hydrate: () => void;
}

export const useAuth = create<AuthState>((set) => ({
  user: null,
  token: "",
  hydrated: false,
  setAuth: (token, user) => {
    setToken(token, user);
    set({ token, user });
  },
  logout: () => {
    clearToken();
    set({ token: "", user: null });
  },
  hydrate: () => {
    const token = getToken();
    const user = getStoredUser();
    set({ token, user, hydrated: true });
  },
}));
