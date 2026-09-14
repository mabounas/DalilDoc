import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { auth } from "../lib/api";

const NAV = [
  ["/dashboard", "Tableau de bord"],
  ["/demarches", "Démarches"],
  ["/analytics", "Analytics"],
  ["/settings", "Paramètres"],
] as const;

export default function Layout() {
  const navigate = useNavigate();
  return (
    <div className="flex min-h-screen">
      <aside className="flex w-60 flex-col bg-night p-5 text-white">
        <div className="mb-8">
          <p className="text-lg font-bold text-gold">WathiqaDoc</p>
          <p className="text-xs text-slate-400">Back-office · وثيقة دوك</p>
        </div>
        <nav className="flex flex-col gap-1">
          {NAV.map(([to, label]) => (
            <NavLink key={to} to={to} className={({ isActive }) => `rounded-md px-3 py-2 text-sm ${isActive ? "bg-white/10 text-gold" : "text-slate-300 hover:bg-white/5"}`}>
              {label}
            </NavLink>
          ))}
        </nav>
        <button
          className="mt-auto rounded-md px-3 py-2 text-left text-sm text-slate-400 hover:bg-white/5"
          onClick={() => {
            auth.clear();
            navigate("/login");
          }}
        >
          Déconnexion
        </button>
      </aside>
      <main className="flex-1 overflow-auto p-8">
        <Outlet />
      </main>
    </div>
  );
}
