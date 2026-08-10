import { ReactNode, useEffect, useState } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../store";

interface Props {
  children: ReactNode;
  /** 允许的全局角色；不填 = 所有登录用户 */
  roles?: string[];
}

export default function RequireRole({ children, roles }: Props) {
  const { user, token, hydrated } = useAuth();
  const loc = useLocation();
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    if (hydrated) setChecked(true);
  }, [hydrated]);

  if (!checked) return null;
  if (!token) return <Navigate to="/login" replace state={{ from: loc.pathname }} />;
  if (roles && user && !roles.includes(user.global_role)) {
    return (
      <div className="card text-center py-12">
        <h2 className="text-lg font-bold mb-2">权限不足</h2>
        <p className="text-sm muted mb-4">
          此页面需要以下角色之一：{roles.join(" / ")}
        </p>
        <p className="text-xs muted">
          当前角色：{user.global_role}
        </p>
      </div>
    );
  }
  return <>{children}</>;
}

export function RequirePI({ children }: { children: ReactNode }) {
  return <RequireRole roles={["pi", "admin"]}>{children}</RequireRole>;
}

export function RequireLeadOrPI({ children }: { children: ReactNode }) {
  return <RequireRole roles={["pi", "lead", "admin"]}>{children}</RequireRole>;
}
