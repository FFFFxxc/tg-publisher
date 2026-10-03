"use client";

import { useState } from "react";
import ActionButton from "@/components/ActionButton";
import { INPUT } from "@/components/ui";

export default function AddSourceForm() {
  const [ref, setRef] = useState("");
  return (
    <div className="grid gap-3 sm:grid-cols-[minmax(260px,1fr)_auto]">
      <label className="field-label">Ссылка или имя канала
      <input
        value={ref}
        onChange={(e) => setRef(e.target.value)}
        placeholder="@channel или https://t.me/channel"
        className={`w-full ${INPUT}`}
      />
      </label>
      <div className="flex items-end">
      <ActionButton
        path="sources"
        method="POST"
        body={{ ref }}
        label="Добавить источник"
        variant="primary"
        doneLabel="источник добавлен"
      />
      </div>
      <span className="field-help sm:col-span-2">Поддерживаются публичные и закрытые каналы, ссылка-приглашение и числовой ID. Повторный источник не добавится.</span>
    </div>
  );
}
