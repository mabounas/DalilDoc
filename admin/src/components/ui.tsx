/* Composants de base au style shadcn/ui (Tailwind), sans générateur externe. */
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";
import type { Statut } from "../lib/api";

const cx = (...c: (string | false | undefined | null)[]) => c.filter(Boolean).join(" ");

type Variant = "default" | "outline" | "ghost" | "destructive" | "success";

export function Button({ variant = "default", className, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  const styles: Record<Variant, string> = {
    default: "bg-night text-white hover:bg-slate-800",
    outline: "border border-slate-300 bg-white hover:bg-slate-100",
    ghost: "hover:bg-slate-100",
    destructive: "bg-red-600 text-white hover:bg-red-700",
    success: "bg-mint text-white hover:opacity-90",
  };
  return (
    <button
      className={cx("inline-flex h-9 items-center justify-center gap-2 rounded-md px-4 text-sm font-medium transition disabled:pointer-events-none disabled:opacity-50", styles[variant], className)}
      {...props}
    />
  );
}

export const Input = ({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) => (
  <input className={cx("h-9 w-full rounded-md border border-slate-300 bg-white px-3 text-sm focus:outline-none focus:ring-2 focus:ring-gold", className)} {...props} />
);

export const Textarea = ({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) => (
  <textarea className={cx("min-h-[80px] w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gold", className)} {...props} />
);

export const Select = ({ className, ...props }: SelectHTMLAttributes<HTMLSelectElement>) => (
  <select className={cx("h-9 w-full rounded-md border border-slate-300 bg-white px-3 text-sm", className)} {...props} />
);

export const Label = ({ children, hint }: { children: ReactNode; hint?: string }) => (
  <label className="mb-1 block text-sm font-medium text-slate-700">
    {children}
    {hint && <span className="ml-2 font-normal text-slate-400">{hint}</span>}
  </label>
);

export const Card = ({ title, actions, children, className }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) => (
  <section className={cx("rounded-xl border border-slate-200 bg-white p-5 shadow-sm", className)}>
    {(title || actions) && (
      <header className="mb-4 flex items-center justify-between gap-3">
        <h2 className="text-base font-semibold">{title}</h2>
        {actions}
      </header>
    )}
    {children}
  </section>
);

const STATUT_STYLE: Record<Statut, string> = {
  brouillon: "bg-slate-100 text-slate-700",
  review: "bg-amber-100 text-amber-800",
  valide: "bg-sky-100 text-sky-800",
  production: "bg-emerald-100 text-emerald-800",
  inactif: "bg-red-100 text-red-700",
};

export const StatusBadge = ({ statut }: { statut: Statut }) => (
  <span className={cx("rounded-full px-2.5 py-0.5 text-xs font-semibold uppercase", STATUT_STYLE[statut])}>{statut}</span>
);

export const Stat = ({ label, value, sub }: { label: string; value: ReactNode; sub?: string }) => (
  <div className="rounded-xl border border-slate-200 bg-white p-4">
    <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
    <p className="mt-1 text-2xl font-bold">{value}</p>
    {sub && <p className="text-xs text-slate-400">{sub}</p>}
  </div>
);
