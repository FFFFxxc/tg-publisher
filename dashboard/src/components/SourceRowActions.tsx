"use client";

import { useState } from "react";
import ActionButton from "@/components/ActionButton";

export default function SourceRowActions({ s }: { s: any }) {
  const [n, setN] = useState(25);
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <ActionButton
        path={`sources/${s.id}`}
        method="PATCH"
        body={{ enabled: !s.enabled }}
        label={s.enabled ? "Выключить" : "Включить"}
        doneLabel={s.enabled ? "выключен" : "включен"}
      />
      <ActionButton path={`sources/${s.id}/check`} label="Проверить" doneLabel="доступен" />
      <ActionButton
        path={`sources/${s.id}/backfill`}
        body={{ n }}
        label={`Забрать ${n}`}
        doneLabel="backfill готов"
      />
      <select
        value={n}
        onChange={(e) => setN(Number(e.target.value))}
        className="rounded border border-zinc-700 bg-zinc-900 px-1 py-1 text-xs"
      >
        {[10, 25, 50, 100].map((x) => (
          <option key={x} value={x}>
            {x}
          </option>
        ))}
      </select>
      <ActionButton
        path={`sources/${s.id}`}
        method="DELETE"
        variant="danger"
        confirm={`Удалить источник ${s.ref}? (если есть посты — просто выключится)`}
        label="Удалить"
        doneLabel="удалён"
      />
    </div>
  );
}
