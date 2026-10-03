"use client";

import ActionButton from "@/components/ActionButton";
import PostSchedule from "@/components/PostSchedule";
import CaptionEditor from "@/components/CaptionEditor";

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
          doneLabel="опубликовано"
        />
      )}
      {canRetry && (
        <ActionButton path={`posts/${p.id}/requeue`} label="Повторить" doneLabel="добавлено в очередь" />
      )}
      {canSkip && (
        <ActionButton
          path={`posts/${p.id}/skip`}
          label="Пропустить"
          variant="danger"
          confirm={`Пропустить пост ${p.id}?`}
          doneLabel="пост пропущен"
        />
      )}
      {canAi && (
        <ActionButton path={`posts/${p.id}/ai`} body={{ force: true }} label="Создать текст AI" doneLabel="текст AI готов" />
      )}
      {canPublish && <PostSchedule p={p} />}
      {canPublish && <CaptionEditor p={p} />}
    </div>
  );
}
