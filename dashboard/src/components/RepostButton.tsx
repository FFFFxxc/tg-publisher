"use client";

import ActionButton from "@/components/ActionButton";

export default function RepostButton({ groupKey }: { groupKey: string }) {
  return (
    <ActionButton
      path="own/repost"
      body={{ group_key: groupKey }}
      label="Репост"
      variant="primary"
      confirm="Опубликовать этот пост в канал сейчас?"
      doneLabel="готово"
    />
  );
}
