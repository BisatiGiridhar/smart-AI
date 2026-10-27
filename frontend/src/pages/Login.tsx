import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Navigate, useNavigate } from "react-router-dom";
import { z } from "zod";
import { Button, ErrorNote, Field, Input, Loading } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";

const loginSchema = z.object({ email: z.string().email("Enter a valid email."), password: z.string().min(1, "Enter your password.") });
const setupSchema = loginSchema.extend({
  password: z.string().min(12, "Use at least 12 characters."),
  full_name: z.string().max(200),
  workspace_name: z.string().min(1, "Name the first workspace."),
});

const loginOnly = loginSchema.extend({ full_name: z.string(), workspace_name: z.string() });

export default function Login() {
  const { me } = useAuth();
  const status = useQuery({ queryKey: ["bootstrap"], queryFn: () => api<{ needs_bootstrap: boolean }>("/api/auth/bootstrap-status") });
  if (me) return <Navigate to="/app" replace />;
  if (status.isLoading) return <div className="p-8"><Loading label="Connecting to the API" /></div>;
  const setup = status.data?.needs_bootstrap === true;
  return <AuthForm key={String(setup)} setup={setup} apiDown={status.isError} />;
}

function AuthForm({ setup, apiDown }: { setup: boolean; apiDown: boolean }) {
  const { login } = useAuth();
  const nav = useNavigate();
  const [error, setError] = useState<unknown>(null);
  const form = useForm<z.infer<typeof setupSchema>>({ resolver: zodResolver(setup ? setupSchema : loginOnly),
    defaultValues: { email: "", password: "", full_name: "", workspace_name: "" } });

  const submit = form.handleSubmit(async (v) => {
    setError(null);
    try {
      if (setup) await api("/api/auth/bootstrap", { method: "POST", json: v });
      await login(v.email, v.password);
      nav("/app");
    } catch (e) { setError(e); }
  });
  const err = form.formState.errors;
  return (
    <div className="flex min-h-full items-center justify-center px-4 py-10">
      <form onSubmit={submit} className="w-full max-w-sm space-y-4 rounded-panel border border-line bg-surface p-6" noValidate>
        <div>
          <h1 className="text-xl font-semibold">{setup ? "Create the administrator account" : "Sign in"}</h1>
          <p className="mt-1 text-sm text-muted">{setup ? "No users exist yet. This first account becomes the workspace administrator." : "Smart AI Hiring Assistant"}</p>
        </div>
        {apiDown && <ErrorNote error="The API is not reachable. Start the backend and reload." />}
        <Field label="Email" error={err.email?.message}><Input type="email" autoComplete="username" {...form.register("email")} /></Field>
        <Field label="Password" error={err.password?.message}><Input type="password" autoComplete={setup ? "new-password" : "current-password"} {...form.register("password")} /></Field>
        {setup && (
          <>
            <Field label="Your name" error={err.full_name?.message}><Input {...form.register("full_name")} /></Field>
            <Field label="Workspace name" error={err.workspace_name?.message}><Input {...form.register("workspace_name")} /></Field>
          </>
        )}
        <ErrorNote error={error} />
        <Button type="submit" className="w-full" loading={form.formState.isSubmitting}>{setup ? "Create account and sign in" : "Sign in"}</Button>
      </form>
    </div>
  );
}
