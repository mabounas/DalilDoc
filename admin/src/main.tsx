import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import "./index.css";
import { auth } from "./lib/api";
import Analytics from "./pages/Analytics";
import Dashboard from "./pages/Dashboard";
import DemarcheForm from "./pages/DemarcheForm";
import Demarches from "./pages/Demarches";
import Login from "./pages/Login";
import Preview from "./pages/Preview";
import Settings from "./pages/Settings";

function RequireAuth({ children }: { children: React.ReactElement }) {
  return auth.token ? children : <Navigate to="/login" replace />;
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter basename={import.meta.env.BASE_URL.replace(/\/$/, "")}>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route element={<RequireAuth><Layout /></RequireAuth>}>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/demarches" element={<Demarches />} />
          <Route path="/demarches/new" element={<DemarcheForm />} />
          <Route path="/demarches/:id/edit" element={<DemarcheForm />} />
          <Route path="/demarches/:id/preview" element={<Preview />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/settings" element={<Settings />} />
        </Route>
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>,
);
