"use client";

import { useState } from "react";
import ActionButton from "@/components/ActionButton";
import { INPUT } from "@/components/ui";

export default function AddSourceForm() {
  const [ref, setRef] = useState("");
  return (
    <div className="flex flex-wrap items-center gap-2">
      <input
        value={ref}
        onChange={(e) => setRef(e.target.value)}
        placeholder="@username / t.me/name / -100ID / t.me/+hash"
        className={`w-96 ${INPUT}`}
      />
      <ActionButton
        path="sources"
        method="POST"
        body={{ ref }}
        label="Добавить"
        variant="primary"
        doneLabel="источник добавлен"
      />
      <span className="text-xs text-zinc-500">
        воркер проверит доступ через Telethon (resolve + title) и только потом сохранит; дубль не добавится
      </span>
    </div>
  );
}
