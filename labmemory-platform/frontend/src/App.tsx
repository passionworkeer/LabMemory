import { useEffect } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./store";
import Layout from "./components/Layout";
import DialogHost from "./components/DialogHost";
import { RequireAdmin, RequirePI } from "./components/RequireRole";
import Login from "./pages/Login";
import ControlTower from "./pages/ControlTower";
import PreMeetingBrief from "./pages/PreMeetingBrief";
import DecisionCompiler from "./pages/DecisionCompiler";
import PostMeetingReview from "./pages/PostMeetingReview";
import PassportList from "./pages/PassportList";
import ExperimentPassport from "./pages/ExperimentPassport";
import ActionAudit from "./pages/ActionAudit";
import ResultBackflow from "./pages/ResultBackflow";
import TrustedQA from "./pages/TrustedQA";
import Experiments from "./pages/Experiments";
import AdminUsers from "./pages/AdminUsers";
import ReviewsList from "./pages/ReviewsList";
import AuditList from "./pages/AuditList";
import ResultList from "./pages/ResultList";

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { token, hydrated } = useAuth();
  const loc = useLocation();
  if (!hydrated) return null;
  if (!token) return <Navigate to="/login" replace state={{ from: loc.pathname }} />;
  return <>{children}</>;
}

export default function App() {
  const hydrate = useAuth((s) => s.hydrate);
  useEffect(() => {
    hydrate();
  }, [hydrate]);

  return (
    <>
    <DialogHost />
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="/"
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route index element={<Navigate to="/tower" replace />} />
        <Route path="tower" element={<ControlTower />} />

        {/* 会后复核：列表 + 详情 */}
        <Route path="review" element={<ReviewsList />} />
        <Route path="review/:meetingId" element={<PostMeetingReview />} />
        <Route path="compiler/:meetingId" element={<DecisionCompiler />} />
        <Route path="brief/:experimentId" element={<PreMeetingBrief />} />

        {/* 行动审计：列表 + 详情 */}
        <Route path="audit" element={<AuditList />} />
        <Route path="audit/:taskId" element={<ActionAudit />} />

        {/* 结果回流：列表 + 详情 */}
        <Route path="result" element={<ResultList />} />
        <Route path="result/:taskId" element={<ResultBackflow />} />

        {/* 实验管理（仅 PI） */}
        <Route
          path="experiments"
          element={
            <RequirePI>
              <Experiments />
            </RequirePI>
          }
        />

        {/* 系统管理（仅 Admin） */}
        <Route
          path="admin/users"
          element={
            <RequireAdmin>
              <AdminUsers />
            </RequireAdmin>
          }
        />

        {/* 可信问答 */}
        <Route path="qa" element={<TrustedQA />} />

        {/* 实验护照：列表 + 详情 */}
        <Route path="passport" element={<PassportList />} />
        <Route path="passport/:experimentId" element={<ExperimentPassport />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
    </>
  );
}
