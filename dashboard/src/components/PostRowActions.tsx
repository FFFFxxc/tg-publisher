"use client";

import ActionButton from "@/components/ActionButton";

const SENDABLE = ["candidate", "pending", "failed", "expired"];

export default function PostRowActions({ p }: { p: any }) {
  const sent = (p.dest_msg_ids ?? []).length > 0;
  const canPublish = SENDABLE.includes(p.status) && !sent;
  const canRetry = ["failed", "ambiguous"].includes(p.status) && !sent;
  const canSkip = SENDABLE.includes(p.status);
  const canAi = p.kind === "parsed";

  return (
    <div className="flex flex-wrap gap-1.5">
      {canPublish && (
        <ActionButton
          path={`posts/${p.id}/publish`}
          label="Опубликовать"
          variant="primary"
          confirm={`Публиковать пост ${p.id} сейчас?`}
          doneLabel="готово"
        />
      )}
      {canRetry && (
        <ActionButton path={`posts/${p.id}/requeue`} label="Ретрай" doneLabel="в очереди" />
      )}
      {canSkip && (
        <ActionButton
          path={`posts/${p.id}/skip`}
          label="Скип"
          variant="danger"
          confirm={`Пропустить пост ${p.id}?`}
          doneLabel="skipped"
        />
      )}
      {canAi && (
        <ActionButton path={`posts/${p.id}/ai`} body={{ force: true }} label="AI" doneLabel="AI готов" />
      )}
    </div>
  );
}
