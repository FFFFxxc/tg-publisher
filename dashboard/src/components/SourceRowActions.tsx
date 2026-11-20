"use client";

import { useState } from "react";
import ActionButton from "@/components/ActionButton";

export default function SourceRowActions({ s }: { s: any }) {
  const [n, setN] = useState(25);
  return (
    <div className="row-actions">
      <ActionButton
        path={`sources/${s.id}`}
        method="PATCH"
        body={{ enabled: !s.enabled }}
        label={s.enabled ? "Выключить" : "Включить"}
        doneLabel={s.enabled ? "выключен" : "включен"}
      />
      <ActionButton path={`sources/${s.id}/check`} label="Проверить" doneLabel="доступен" />
      <div className="backfill-actions">
        <ActionButton
          path={`sources/${s.id}/backfill`}
          body={{ n }}
          label={`Загрузить прошлые (${n})`}
          doneLabel="прошлые публикации загружены"
        />
        <select
          value={n}
          onChange={(e) => setN(Number(e.target.value))}
          aria-label="Количество прошлых публикаций"
        >
          {[10, 25, 50, 100].map((x) => (
            <option key={x} value={x}>
              {x}
            </option>
          ))}
        </select>
      </div>
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
