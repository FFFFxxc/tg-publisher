# Design

## Source of truth
- Status: Active
- Last refreshed: 2026-10-03
- Primary product surfaces: обзор состояния, источники, очередь публикаций, расписание, AI, подпись, архив своего канала, журнал событий.
- Evidence reviewed: `dashboard/src/app/*`, `dashboard/src/components/*`, `README.md`, `dashboard/README.md`.

## Brand
- Personality: спокойный, надёжный рабочий инструмент без технического шума.
- Trust signals: явное состояние бота, точные результаты действий, даты последнего обновления, понятные ошибки.
- Avoid: нерасшифрованные backend-термины, плотные таблицы без иерархии, декоративный «неон», ложное подтверждение успеха.

## Product goals
- Goals: за несколько секунд понять состояние публикаций; безопасно управлять очередью; менять настройки без сервера и командной строки.
- Non-goals: маркетинговый лендинг, полноценная аналитическая BI-система, изменение API-контрактов.
- Success signals: основные действия понятны без документации; ошибки и ожидание видны; интерфейс работает на телефоне.

## Personas and jobs
- Primary personas: владелец Telegram-канала и оператор публикаций.
- User jobs: проверить работу бота, найти проблемный пост, управлять источниками, изменить расписание/AI/подпись.
- Key contexts of use: быстрый контроль с телефона и подробная диагностика с компьютера.

## Information architecture
- Primary navigation: главная, контент (источники, очередь, архив), автоматизация (расписание, AI, подпись), контроль (журнал).
- Core routes/screens: `/`, `/sources`, `/queue`, `/schedule`, `/ai`, `/footer`, `/own-posts`, `/activity`.
- Content hierarchy: заголовок и объяснение → главное состояние/действие → фильтры → данные → технические детали.

## Design principles
- Сначала человеческий смысл, затем при необходимости техническое значение.
- Опасные, долгие и недоступные действия должны визуально отличаться и сохранять честное состояние.
- Плотность таблиц допустима на desktop, но управление и чтение остаются удобными на узких экранах.
- Tradeoffs: сохраняем текущий Tailwind и API; улучшаем систему через общие классы и компоненты без новой зависимости.

## Visual language
- Color: тёмно-синий фон, холодные синие поверхности, бирюзовый акцент, семантические зелёный/янтарный/красный.
- Typography: системный sans-serif, крупные заголовки, спокойный основной текст, моноширинный шрифт только для идентификаторов.
- Spacing/layout rhythm: 4/8/12/16/24/32 px, ширина контента до 1440 px.
- Shape/radius/elevation: радиусы 10–18 px, тонкие границы, мягкие тени без тяжёлого glassmorphism.
- Motion: короткие hover/focus-переходы; никаких обязательных анимаций.
- Imagery/iconography: простые встроенные SVG-иконки навигации, без внешней библиотеки.

## Components
- Existing components to reuse: `Card`, `Stat`, `Badge`, `ActionButton`, таблицы и формы.
- New/changed components: `AppShell`, `PageHeader`, `Notice`, русские словари статусов и типов.
- Variants and states: default/primary/danger; loading/success/error/disabled/empty.
- Token/component ownership: глобальные токены — `globals.css`; семантика и базовые компоненты — `components/ui.tsx`.

## Accessibility
- Target standard: WCAG 2.1 AA для основных сценариев.
- Keyboard/focus behavior: видимый `focus-visible`, нативные поля/кнопки, мобильное меню без hover-зависимости.
- Contrast/readability: основной текст светлый на тёмно-синем фоне; вторичный текст не используется для критичной информации.
- Screen-reader semantics: landmarks, заголовки, подписи полей, `aria-current`, live-регионы для результатов.
- Reduced motion and sensory considerations: переходы отключаются через `prefers-reduced-motion`.

## Responsive behavior
- Supported breakpoints/devices: от 360 px до широкого desktop.
- Layout adaptations: боковая навигация на desktop, горизонтальная прокручиваемая навигация сверху на mobile; таблицы прокручиваются.
- Touch/hover differences: интерактивные элементы не меньше 40 px там, где это возможно; hover не несёт уникальный смысл.

## Interaction states
- Loading: кнопка показывает действие словами и блокируется.
- Empty: объясняет причину и следующий шаг.
- Error: отдельный заметный блок с человеческим заголовком и исходным сообщением.
- Success: зелёное подтверждение после реального ответа backend.
- Disabled: сниженная контрастность и запрет взаимодействия.
- Offline/slow network: сохраняем данные на экране и показываем сбой автообновления.

## Content voice
- Tone: короткий, спокойный, без обвинений.
- Terminology: «подготовленный пост», «повторная публикация», «ожидает», «рейтинг», «загрузка прошлых публикаций».
- Microcopy rules: технический код допускается в деталях после понятного русского названия; кнопка описывает действие глаголом.

## Implementation constraints
- Framework/styling system: Next.js 14, React 18, Tailwind CSS 3.
- Design-token constraints: без новых пакетов; цвета и общие паттерны задаются в существующем CSS/Tailwind.
- Performance constraints: серверные страницы и параллельные независимые запросы сохраняются.
- Compatibility constraints: API-пути, payload и значения enum не меняются.
- Test/screenshot expectations: `npm run build`; ручная проверка desktop/mobile при доступном браузере.

## Open questions
- [ ] Нужна ли отдельная светлая тема после проверки обновлённой тёмной версии / владелец / низкое влияние.

## Queue update (2026-10-03)
- Default queue is responsive content cards, no tiny table thumbnails.
- Media uses object-contain, height 256–320px; native modal opens 96vw × 94dvh and closes with Escape or Close.
- Every sendable card and detail has individual date/time control (Europe/Moscow), reschedule/cancel and visible scheduled timestamp. Scheduling does not publish immediately.
