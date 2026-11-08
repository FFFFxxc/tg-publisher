type ScheduleState = {
  enabled?: boolean;
  blocked?: boolean;
  reason?: string;
  waiting_for_slot?: boolean;
  scheduled_posts?: number;
  quiet_seconds?: number;
};

export function nativeScheduleNotice(value?: ScheduleState | null) {
  if (!value?.enabled) return null;
  const waiting = !!value.blocked || !!value.waiting_for_slot ||
    ["native_queue", "quiet_period", "check_failed", "not_checked", "history_overflow"].includes(value.reason ?? "");
  const tone: "warning" | "success" = waiting ? "warning" : "success";
  let title = "Защита от сдвоений включена";
  let detail = "Отложка Telegram пуста. Автоматические посты выходят по расписанию.";
  if (value.reason === "native_queue") {
    title = `Приоритет твоим постам: в отложке Telegram — ${value.scheduled_posts ?? 0}`;
    detail = "Автопубликации и реклама этого канала ждут. После последнего твоего поста бот продолжит со следующего свободного слота, без отправки всей очереди сразу.";
  } else if (value.reason === "quiet_period") {
    title = "Пауза после твоей публикации";
    detail = `Бот выдерживает интервал ${Math.ceil((value.quiet_seconds ?? 600) / 60)} мин., чтобы посты не выходили вплотную. Затем продолжит по расписанию.`;
  } else if (value.reason === "check_failed") {
    title = "Проверка отложки Telegram временно недоступна";
    detail = "Автоматические публикации ждут успешной проверки, чтобы не пересечься с твоими постами. Материалы остаются в очереди.";
  } else if (value.reason === "not_checked" || value.reason === "history_overflow") {
    title = "Проверяем отложку и недавние публикации Telegram";
    detail = "До завершения проверки автоматические публикации ждут. Материалы остаются в очереди.";
  } else if (value.waiting_for_slot) {
    title = "Отложка Telegram пуста — ждём следующий слот";
    detail = "Пропущенные слоты не догоняются. Отложенные материалы будут выходить по одному на слот расписания.";
  }
  return { title, detail, waiting, tone };
}
