import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button, Card, Input, Label } from "../components/ui";
import { login } from "../lib/api";

export default function Login() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [totp, setTotp] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  return (
    <div className="flex min-h-screen items-center justify-center bg-night p-6">
      <Card className="w-full max-w-sm" title={<span>Connexion <span className="text-gold">WathiqaDoc</span></span>}>
        <form
          className="flex flex-col gap-4"
          onSubmit={async (e) => {
            e.preventDefault();
            setLoading(true);
            setError(null);
            try {
              await login(email, password, totp);
              navigate("/dashboard");
            } catch (err) {
              setError((err as Error).message);
            } finally {
              setLoading(false);
            }
          }}
        >
          <div>
            <Label>E-mail</Label>
            <Input type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required />
          </div>
          <div>
            <Label>Mot de passe</Label>
            <Input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          </div>
          <div>
            <Label hint="super-admin">Code 2FA</Label>
            <Input inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={totp} onChange={(e) => setTotp(e.target.value)} />
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <Button type="submit" disabled={loading}>{loading ? "Connexion…" : "Se connecter"}</Button>
        </form>
      </Card>
    </div>
  );
}
