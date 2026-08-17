"use client";

import { useQuery } from "@tanstack/react-query";
import { InfoTip } from "@/components/InfoTip";
import { StateBlock } from "@/components/StateBlock";
import { api } from "@/lib/api";

export default function AdminPage() {
  const health = useQuery({ queryKey: ["admin-health"], queryFn: api.adminHealth });
  const users = useQuery({ queryKey: ["admin-users"], queryFn: api.adminUsers });
  const logs = useQuery({ queryKey: ["admin-logs"], queryFn: api.adminLogs });

  if (health.isError) {
    return <StateBlock title="Admin only" message={(health.error as Error).message} />;
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">
        Admin
        <InfoTip text="Local operations view. Provider keys are never displayed." />
      </h1>
      <div className="grid gap-3 md:grid-cols-4">
        {Object.entries(health.data || {}).map(([key, value]) => (
          <div key={key} className="rounded-xl border border-line bg-ink-800 p-4">
            <p className="text-xs uppercase text-mist">{key}</p>
            <p className="mt-1 text-lg">{String(value)}</p>
          </div>
        ))}
      </div>
      <section>
        <h2 className="mb-2 text-sm text-mist">Users</h2>
        <div className="rounded-xl border border-line">
          {(users.data?.items || []).map((user) => (
            <div key={user.id} className="flex justify-between border-b border-line px-3 py-2 text-sm last:border-0">
              <span>{user.email}</span>
              <span className="text-mist">{user.role}</span>
            </div>
          ))}
        </div>
      </section>
      <section>
        <h2 className="mb-2 text-sm text-mist">Analysis logs</h2>
        <div className="max-h-80 overflow-auto rounded-xl border border-line text-xs">
          {((logs.data?.analyses || []) as { id: string; symbol: string; status: string; error?: string }[]).map((row) => (
            <div key={row.id} className="border-b border-line px-3 py-2">
              {row.symbol} · {row.status} {row.error ? `· ${row.error}` : ""}
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
