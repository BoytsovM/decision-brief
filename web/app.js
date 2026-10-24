/* Figma shell for page "02 Экраны". News rows come from /api/feed. */

const screens = {
  home: renderHome,
  feed: renderFeed,
  card: renderCard,
  profile: renderProfile,
  source: renderSource,
};

const state = {
  screen: "home",
  filter: "",
  trade: "Импорт",
  rate: "",
  clients: "Госзаказ",
  hiddenTopic: "",
  useful: "",
  asked: "",
  profileNote: "",
  companyId: "",
  roleId: "",
  itemId: "",
  companies: [],
  roles: [],
  feed: null,
  error: "",
  loading: true,
  mode: "demo",
  eventNote: "",
  analysis: null,
  analysisNote: "",
  askOpen: false,
  managerNote: "",
  openMenu: "",
  period: "week",
};

const periods = [
  ["today", "Сегодня"],
  ["week", "Неделя"],
  ["month", "Месяц"],
];

const topicFilters = [
  ["all", "Все"],
  ["important", "Важно"],
  ["rate", "Ставка и долг"],
  ["fx", "Курс"],
  ["fuel", "Издержки"],
  ["demand", "Спрос"],
];

const topicFactors = {
  rate: ["F1", "F8"],
  fx: ["F2"],
  fuel: ["F6"],
  demand: ["F4"],
};

const hiddenFactors = {
  "Золото": ["F9"],
  "Розничный спрос": ["F4"],
};

function esc(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function chooseMenu(name, value) {
  state.openMenu = "";
  if (name === "period") {
    state.period = value;
    paint();
    return;
  }
  state.itemId = "";
  state.analysis = null;
  state.analysisNote = "";
  if (name === "company") {
    state.companyId = value;
  }
  if (name === "role") {
    state.roleId = value;
  }
  loadFeed(false);
}

function go(screen) {
  state.screen = screen;
  state.openMenu = "";
  if (screen !== "card") {
    state.askOpen = false;
  }
  if (location.hash !== `#${screen}`) {
    history.pushState({ screen }, "", `#${screen}`);
  }
  paint();
}

function dot(level) {
  const file = level === "mid" ? "dot-notice.svg" : "dot-important.svg";
  return `<img class="dot" src="assets/${file}" width="8" height="8" alt="">`;
}

function importance(level, label) {
  const tone = level === "mid" ? "importance-mid" : "importance-high";
  return `<span class="importance ${tone}">${dot(level)}${esc(label)}</span>`;
}

function origin(kind) {
  const label = { fact: "Факт", bank: "Позиция банка", ai: "Вывод ИИ" }[kind];
  return `<span class="origin origin-${kind}">${label}</span>`;
}

function items() {
  return state.feed && Array.isArray(state.feed.items) ? state.feed.items : [];
}

function selected() {
  const rows = items();
  return rows.find((row) => row.id === state.itemId) || rows[0] || null;
}

function shiftIso(iso, days) {
  const [year, month, day] = iso.split("-").map(Number);
  const stamp = new Date(Date.UTC(year, month - 1, day));
  stamp.setUTCDate(stamp.getUTCDate() + days);
  return stamp.toISOString().slice(0, 10);
}

function hiddenIds() {
  return hiddenFactors[state.hiddenTopic] || [];
}

function inPeriod(item) {
  const asOf = state.feed ? state.feed.as_of : "";
  const published = item.published_iso || "";
  if (!asOf || !published) {
    return true;
  }
  if (published > asOf) {
    return false;
  }
  if (state.period === "today") {
    return published === asOf;
  }
  if (state.period === "month") {
    return published >= `${asOf.slice(0, 8)}01`;
  }
  return published >= shiftIso(asOf, -7);
}

function visibleFeed() {
  const hidden = hiddenIds();
  return items().filter((item) => {
    const ids = (item.factors || []).map((factor) => factor.id);
    if (hidden.some((id) => ids.includes(id))) {
      return false;
    }
    if (!state.filter || state.filter === "all") {
      return true;
    }
    if (state.filter === "important") {
      return item.level === "high";
    }
    const wanted = topicFactors[state.filter] || [];
    return ids.some((id) => wanted.includes(id));
  });
}

function caret() {
  return `<svg class="caret" viewBox="0 0 12 12" width="12" height="12" aria-hidden="true"><path d="M2.2 4.4 6 8.1 9.8 4.4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
}

function dropdown(name, buttonClass, label, options, value, menuClass) {
  const open = state.openMenu === name;
  const rows = options.map((option) => {
    const on = option.id === value ? " is-on" : "";
    return `<button class="menu-item${on}" type="button" role="option" data-pick="${esc(name)}:${esc(option.id)}">${esc(option.label)}</button>`;
  }).join("");
  const list = open ? `<div class="menu-list" role="listbox">${rows}</div>` : "";
  const placed = menuClass ? ` ${menuClass}` : "";
  return `
    <div class="menu${placed}${open ? " is-open" : ""}">
      <button class="${buttonClass}" type="button" data-menu="${esc(name)}" aria-expanded="${open ? "true" : "false"}">
        <span>${esc(label)}</span>${caret()}
      </button>
      ${list}
    </div>`;
}

function companyMenu() {
  const current = state.companies.find((company) => company.id === state.companyId) || state.companies[0];
  const options = state.companies.map((company) => ({ id: company.id, label: company.chip }));
  return dropdown("company", "company-btn", current ? current.chip : "Компания", options, state.companyId, "menu-end");
}

function roleMenu() {
  const current = state.roles.find((role) => role.id === state.roleId);
  const options = state.roles.map((role) => ({ id: role.id, label: role.label }));
  return dropdown("role", "chip is-on", `Роль: ${current ? current.label : ""}`, options, state.roleId);
}

function periodMenu() {
  const current = periods.find((row) => row[0] === state.period) || periods[1];
  const options = periods.map(([id, label]) => ({ id, label }));
  return dropdown("period", "chip", current[1], options, state.period);
}

function header(active) {
  const item = (id, label) =>
    `<button class="nav-link ${active === id ? "is-active" : ""}" type="button" data-go="${id}">${label}</button>`;
  const line = active === "feed" ? " header-line" : "";
  const company = state.companies.length
    ? companyMenu()
    : `<span class="company">Компания</span>`;
  const role = state.roles.find((row) => row.id === state.roleId);
  return `
    <header class="header${line}">
      <button class="logo" type="button" data-go="home">Альфа-Бизнес</button>
      <nav>${item("home", "Главная")}${item("payments", "Платежи")}${item("accounts", "Счета")}${item("credits", "Кредиты")}${item("feed", "События")}</nav>
      <div class="spacer"></div>
      ${company}
      <span class="role">${esc(role ? role.label : "")}</span>
    </header>`;
}

function notice() {
  if (!state.feed || !state.feed.notice) {
    return "";
  }
  return `<p class="banner">${esc(state.feed.notice)}</p>`;
}

function widgetCards() {
  return visibleFeed().slice(0, 3);
}

function renderHome() {
  const cards = widgetCards();
  const badge = cards.length ? `${cards.length} новых` : "0";
  const rows = cards.length
    ? cards.map((item) => `
        <button class="widget-item" type="button" data-go="card" data-item="${esc(item.id)}">
          ${importance(item.level, item.label)}
          <strong>${esc(item.title)}</strong>
          <span class="caption">${esc(item.why)}</span>
        </button>`).join("")
    : `<p class="caption">${esc(state.loading ? "Читаем ленты." : "Нет событий выше порога.")}</p>`;
  const company = state.feed ? state.feed.company : null;
  return `
    <main class="screen">
      ${header("home")}
      <div class="content">
        <section class="home-main">
          <h1 class="h1">Добрый день</h1>
          <div class="accounts">
            <article class="account"><p class="caption">Расчётный счёт</p><strong>Суммы счетов не переданы</strong></article>
            <article class="account"><p class="caption">Депозиты</p><strong>${esc(company ? company.deposit : "…")}</strong></article>
            <article class="account"><p class="caption">Кредиты</p><strong>${esc(company ? company.loan : "…")}</strong></article>
          </div>
          <section class="payments">
            <h2 class="h3">Последние платежи</h2>
            ${paymentLines(company)}
          </section>
        </section>
        <aside class="widget">
          <div class="widget-head">
            <h2 class="h3">События для вашего бизнеса</h2>
            <div class="spacer"></div>
            <span class="badge">${esc(badge)}</span>
          </div>
          <p class="caption">События недели, которые касаются вашей компании</p>
          ${rows}
          <button class="btn" type="button" data-go="feed">Все события</button>
        </aside>
      </div>
    </main>`;
}

function paymentLines(company) {
  const rows = company && Array.isArray(company.payments) ? company.payments : [];
  if (!rows.length) {
    return `<p class="caption">Исходящих платежей этой компании нет.</p>`;
  }
  return rows.map((row) => `
    <p class="body">${esc(row.beneficiary)} · ${esc(row.amount)} · ${esc(row.count)} платежей</p>
  `).join("");
}

function eventForm() {
  const asOf = state.feed && state.feed.as_of ? state.feed.as_of : "2026-10-21";
  return `
    <section class="rail-card add-form">
      <h2 class="h3">Проверить новую новость</h2>
      <p class="caption">Тот же классификатор и порог, что у ленты. Дата позже сценария скрывает событие.</p>
      <form data-event>
        <input name="title" type="text" maxlength="300" placeholder="Заголовок">
        <textarea name="body" maxlength="4000" placeholder="Текст события"></textarea>
        <input name="published" type="date" value="${esc(asOf)}">
        <input name="url" type="text" maxlength="1000" placeholder="Ссылка на первоисточник, необязательно">
        <button class="btn" type="submit">Добавить материал</button>
      </form>
      <p class="caption">${esc(state.eventNote)}</p>
    </section>
    <section class="rail-card add-form">
      <h2 class="h3">Уточняющий вопрос</h2>
      <form data-analyze>
        <input name="q" type="text" maxlength="1000" placeholder="Что означает изменение спроса?" value="${esc(state.asked)}">
        <button class="btn" type="submit">Подготовить анализ</button>
      </form>
      <p class="caption">${esc(state.analysisNote)}</p>
    </section>`;
}

function analysisBlock() {
  const result = state.analysis;
  if (!result) {
    return "";
  }
  const status = {
    rules_only: "Интерпретация по правилам. Это не ответ языковой модели.",
    model_verified: "Вывод модели проверен по структуре, ссылкам и числам. Смысл требует экспертной оценки.",
    model_failed: "Шлюз недоступен. Показаны правила, лента сохранена.",
    model_rejected: "Ответ модели не прошёл проверку. Показаны правила.",
    insufficient_evidence: "Нет новостей выше порога.",
    missing_profile: "Компания отсутствует в справочнике.",
  }[result.status] || result.status;
  const claims = (result.claims || []).map((row) => `
    <div class="point">
      <strong>${esc(row.title)}</strong>
      <p>${esc(row.text)}</p>
      <p class="caption">Основание: ${esc((row.sources || []).join(", "))}</p>
    </div>`).join("");
  const gaps = (result.gaps || []).map((gap) => `<p class="caption">${esc(gap)}</p>`).join("");
  const banks = (result.banks || []).map((row) => `
    <div class="point">${origin("bank")}<p>${esc(row.title)}. ${esc(row.text)}</p></div>`).join("");
  const trace = (result.trace || []).map((step) => `
    <p class="caption">${esc(step.tool)} · ${esc(step.status)} · ${esc(step.detail)}</p>`).join("");
  return `
    <section class="rail-card">
      <h2 class="h3">Персональная интерпретация</h2>
      <p class="caption">${esc(status)}</p>
      ${claims}
      ${gaps}
      <h3 class="body" style="font-weight:600">Аналитика Альфа-Банка</h3>
      ${banks || `<p class="caption">Свежей карточки банка в этом разборе нет.</p>`}
      <h3 class="body" style="font-weight:600">Журнал шагов</h3>
      ${trace}
      <button class="btn btn-secondary" type="button" data-download="1">Скачать анализ и журнал (JSON)</button>
    </section>`;
}

function profileFields() {
  const company = state.feed ? state.feed.company : null;
  const rows = company && Array.isArray(company.rows) ? company.rows : [];
  if (!rows.length) {
    return `<p class="caption">Профиль ещё не загружен.</p>`;
  }
  return rows.map((row) => `
    <div class="field"><p class="caption">${esc(row.label)}</p><p class="body">${esc(row.value)}</p></div>
  `).join("");
}

function renderFeed() {
  const rows = visibleFeed().filter(inPeriod);
  const cards = rows.length
    ? rows.map((item) => `
      <button class="feed-card" type="button" data-go="card" data-item="${esc(item.id)}">
        <div class="meta-row">
          ${importance(item.level, item.label)}
          <span class="caption">${esc(item.published)} · ${esc(item.source_name)}</span>
        </div>
        <h2 class="h3">${esc(item.title)}</h2>
        <p class="body muted">Почему вам: ${esc(item.why)}</p>
        <div class="factors">${(item.factors || []).map((factor) => `<span class="factor">${esc(factor.label)}</span>`).join("")}</div>
      </button>`).join("")
    : `<p class="body">${esc(state.error || (state.loading ? "Считаем ленту." : "Нет новостей выше порога."))}</p>`;
  const chips = topicFilters.map(([id, label]) =>
    `<button class="chip ${state.filter === id ? "is-on" : ""}" type="button" data-filter="${id}">${label}</button>`,
  ).join("");
  const incoming = state.feed ? state.feed.incoming : 0;
  const ranked = state.feed ? state.feed.ranked : 0;
  const updated = state.feed ? state.feed.loaded_at : "";
  return `
    <main class="screen">
      ${header("feed")}
      <div class="content">
        <section class="stack grow" style="gap:16px;width:100%">
          <div class="title-row">
            <h1 class="h1">События для вашего бизнеса</h1>
            <div class="spacer"></div>
            <button class="btn btn-secondary" type="button" data-go="profile">Настроить темы</button>
          </div>
          <p class="body muted">Мы отобрали события, которые влияют на вашу компанию, и объяснили почему. Обновлено ${esc(updated)}. <button class="text-btn" type="button" data-refresh="1">Обновить</button></p>
          ${notice()}
          <div class="filters">
            <button class="chip ${state.mode === "demo" ? "is-on" : ""}" type="button" data-mode="demo">Демонстрационные события</button>
            <button class="chip ${state.mode === "live" ? "is-on" : ""}" type="button" data-mode="live">Публичные RSS</button>
            ${roleMenu()}
            ${periodMenu()}
            ${chips}
          </div>
          <div class="feed-list">${cards}</div>
          <p class="caption">Показаны ${rows.length} из ${incoming} событий. Выше порога: ${ranked}. Остальные скрыты для этой компании и роли.</p>
          ${eventForm()}
          ${analysisBlock()}
        </section>
        <aside class="side">
          <h2 class="h3">Что мы учитываем о компании</h2>
          ${profileFields()}
          <div class="callout">
            <p>Уточните данные, и инсайты станут точнее: импорт или экспорт с Китаем? Какая доля долга по плавающей ставке?</p>
            <button class="btn btn-secondary" type="button" data-go="profile">Уточнить профиль</button>
          </div>
        </aside>
      </div>
    </main>`;
}

function block(accent, number, title, aside, inner) {
  return `
    <section class="block">
      <div class="accent accent-${accent}"></div>
      <div class="block-body">
        <div class="block-head">
          <span class="num">${number}</span>
          <h2 class="body" style="font-weight:600">${title}</h2>
          <div class="spacer"></div>
          <span class="caption">${aside}</span>
        </div>
        ${inner}
      </div>
    </section>`;
}

function effectColumn(title, className, rows, empty) {
  const points = rows && rows.length
    ? rows.map((row) => `<div class="point">${origin(row.kind)}<p>${esc(row.text)}</p></div>`).join("")
    : `<div class="point">${origin("fact")}<p>${esc(empty)}</p></div>`;
  return `<div class="col ${className}"><h3>${title}</h3>${points}</div>`;
}

function effectsBlock(card) {
  const effects = card.effects || {};
  const gaps = effects.gaps
    ? `<p class="gap-line">${esc(effects.gaps)}</p>`
    : "";
  return block("ai", "03", "ПОСЛЕДСТВИЯ", "Риски, возможности, факторы", `
    <div class="cols">
      ${effectColumn("Риски", "col-risk", effects.risks, "Отдельный риск по профилю не выделен.")}
      ${effectColumn("Возможности", "col-chance", effects.opportunities, "Отдельная возможность по профилю не выделена.")}
      ${effectColumn("Что повлияет дальше", "col-next", effects.next, "В материалах банка нет отдельного будущего события.")}
    </div>
    ${gaps}`);
}

function bankParagraphs(text) {
  const parts = String(text || "").split(/(?<=\.)\s+/).filter(Boolean);
  if (!parts.length) {
    return `<p class="body">Свежей позиции банка по этой теме нет.</p>`;
  }
  return parts.map((line) => `<p class="body">${esc(line)}</p>`).join("");
}

function renderCard() {
  const item = selected();
  if (!item) {
    return `
      <main class="screen">
        ${header("feed")}
        <div class="content"><p class="body">В ленте нет события для карточки.</p></div>
      </main>`;
  }
  const card = item.card;
  const modelText = card.model
    ? card.model
    : "Модель на просмотр ленты не вызывается. Вывод появится только по отдельному запросу анализа.";
  return `
    <main class="screen">
      ${header("feed")}
      <div class="content">
        <article class="card-main">
          <button class="back" type="button" data-go="feed">← События</button>
          <div class="meta-row">
            ${importance(item.level, item.label)}
            <span class="caption">${esc(item.published)} · ${esc(item.source_name)}</span>
          </div>
          <h1 class="h1">${esc(item.title)}</h1>
          ${block("ink", "01", "ФАКТ", esc(item.source_name), `
            <div class="claim">${origin("fact")}<p class="body">${esc(card.happened)}</p></div>`)}
          ${block("mid", "02", "СВЯЗЬ С КОМПАНИЕЙ", "Профиль компании", `
            <div class="claim">${origin("fact")}<p class="body">${esc(card.why || "Для этого события ранжирование не назвало отдельную причину.")}</p></div>`)}
          ${effectsBlock(card)}
          ${block("bank", "04", "ПОЗИЦИЯ БАНКА", "Материал банка", `
            <div class="claim">${origin("bank")}<div class="stack">${bankParagraphs(card.bank)}</div></div>`)}
          ${block("ai", "05", "ВЫВОД МОДЕЛИ", "Не вызывалась", `
            <div class="claim">${origin("ai")}<p class="body">${esc(modelText)}</p></div>`)}
          ${block("ink", "06", "ПЕРЕХОД К ИСТОЧНИКУ", "Основания вывода", `
            <p class="body">${esc(item.source_name)} · <a class="text-btn" href="${esc(item.source_url)}" target="_blank" rel="noopener noreferrer">открыть материал</a> · <button class="text-btn" type="button" data-go="source" data-item="${esc(item.id)}">карточка источника</button></p>
            ${card.signs ? `<p class="body">${esc(card.signs)}</p>` : ""}`)}
          <form class="composer" data-ask="1">
            <input name="q" type="text" placeholder="Задайте вопрос по событию" value="${esc(state.asked)}">
            <button class="btn" type="submit">Спросить</button>
          </form>
        </article>
        <aside class="rail ${state.askOpen ? "is-ask" : ""}">
          ${state.askOpen ? clarifyPanel() : cardRail(item)}
        </aside>
      </div>
    </main>`;
}

function useful(id, label) {
  const on = state.useful === id ? "is-on" : "";
  return `<button class="btn btn-secondary ${on}" type="button" data-useful="${id}">${label}</button>`;
}

function cardRail(item) {
  return `
    <div class="rail-actions">
      <button class="btn" type="button" data-manager="1">Обсудить с менеджером</button>
      <button class="btn btn-secondary" type="button">Поделиться</button>
    </div>
    ${state.managerNote ? `<p class="caption">${esc(state.managerNote)}</p>` : ""}
    <section class="rail-card">
      <h2 class="h3">Почему в ленте</h2>
      <p class="body">${esc(item.why)}</p>
    </section>
    <section class="rail-card">
      <h2 class="h3">Это было полезно?</h2>
      <div class="choice-row">
        ${useful("yes", "Полезно")}
        ${useful("no", "Не про нас")}
        ${useful("known", "Уже знал")}
      </div>
    </section>
    <section class="legend">
      <strong>Как читать карточку</strong>
      <p>Блоки 01–04 собраны из новости, профиля и карточки банка. Блок 05 пуст, пока модель не запрошена отдельно.</p>
    </section>`;
}

function clarifyPanel() {
  const item = selected();
  const title = item ? item.title : "Событие не выбрано";
  const result = state.analysis;
  const pending = state.analysisNote
    ? `<p class="caption">${esc(state.analysisNote)}</p>`
    : "";
  const asked = state.asked
    ? `<button class="bubble" type="button">${esc(state.asked)}</button>`
    : "";
  const answer = result
    ? `<div class="answer">
         ${(result.claims || []).map((row) => `
           <div class="stack" style="gap:4px">${origin(row.title === "риск" || row.title === "возможность" ? "ai" : "fact")}<p class="body"><strong>${esc(row.title)}</strong> ${esc(row.text)}</p></div>`).join("")}
         ${(result.banks || []).map((row) => `<div class="stack" style="gap:4px">${origin("bank")}<p class="body">${esc(row.text)}</p></div>`).join("")}
         <p class="caption">${esc(result.status === "model_verified" ? "Ответ модели проверен по источникам." : "Модель на этот запуск не подменяла правила.")}</p>
       </div>`
    : pending;
  const suggestions = [
    "Что это значит для лизинга?",
    "Как это касается всей группы?",
    "Сравнить с прошлым решением",
  ];
  return `
    <section class="panel">
      <div class="meta-row">
        <h2 class="h3">Уточнить по событию</h2>
        <div class="spacer"></div>
        <button class="text-btn" type="button" data-close-ask="1">Закрыть</button>
      </div>
      <p class="caption">${esc(title)}</p>
      ${asked}
      ${answer}
      <div class="suggests">
        ${suggestions.map((line) => `<button class="suggest" type="button" data-prefill="${esc(line)}">${esc(line)}</button>`).join("")}
      </div>
      <form class="panel-input" data-ask="1">
        <input name="q" type="text" placeholder="Ваш вопрос" value="${esc(state.asked)}">
        <button class="btn" type="submit">Спросить</button>
      </form>
      <div class="note">
        <p>Вопрос остаётся на этом событии. Ответ не выходит за факт, последствие по профилю и позицию банка. Если данных нет, так и написано.</p>
      </div>
    </section>`;
}

function choice(group, id) {
  const on = state[group] === id ? "is-on" : "";
  return `<button class="chip ${on}" type="button" data-choice="${group}:${id}">${id}</button>`;
}

function renderProfile() {
  const company = state.feed ? state.feed.company : null;
  const rows = company && Array.isArray(company.rows) ? company.rows : [];
  const bankRows = rows.map((row) => `
    <div class="row"><dt>${esc(row.label)}</dt><dd>${esc(row.value)}</dd></div>
  `).join("");
  return `
    <main class="screen">
      ${header("feed")}
      <div class="content stack" style="gap:16px">
        <h1 class="h1">Что сервис знает о компании</h1>
        <p class="body muted profile-lead">Эти сведения уже есть в профиле компании. От них зависит, какие события поднимаются выше порога. Уточнения справа в профиль не пишутся.</p>
        <div class="columns">
          <section class="profile-card">
            <h2 class="h3">Из данных банка</h2>
            <dl>${bankRows}</dl>
          </section>
          <section class="profile-card profile-card-edit">
            <h2 class="h3">Уточните сами</h2>
            <p class="caption profile-hint">Этого нет в профиле. Скрытая тема только прячет фактор.</p>
            <div class="group">
              <h3 class="body" style="font-weight:600">Торговля с Китаем</h3>
              <div class="choice-row">${choice("trade", "Импорт")}${choice("trade", "Экспорт")}${choice("trade", "Оба направления")}</div>
            </div>
            <div class="group">
              <h3 class="body" style="font-weight:600">Ставка по долгу</h3>
              <div class="choice-row">${choice("rate", "В основном плавающая")}${choice("rate", "В основном фиксированная")}${choice("rate", "Не знаю")}</div>
            </div>
            <div class="group">
              <h3 class="body" style="font-weight:600">Главные заказчики</h3>
              <div class="choice-row">${choice("clients", "Госзаказ")}${choice("clients", "Частные девелоперы")}${choice("clients", "Промышленность")}</div>
            </div>
            <div class="group">
              <h3 class="body" style="font-weight:600">Темы, которые не показывать</h3>
              <div class="choice-row">${choice("hiddenTopic", "Золото")}${choice("hiddenTopic", "Розничный спрос")}${choice("hiddenTopic", "Нет")}</div>
            </div>
            <button class="btn" type="button" data-save="1">Сохранить</button>
            <p class="caption">${esc(state.profileNote)}</p>
          </section>
        </div>
      </div>
    </main>`;
}

function renderSource() {
  const item = selected();
  if (!item) {
    return `<main class="screen">${header("home")}<div class="content"><p class="body">Источник не выбран.</p></div></main>`;
  }
  const card = item.card;
  return `
    <main class="screen">
      <header class="header">
        <button class="logo" type="button" data-go="home">Альфа-Бизнес</button>
        <p class="crumb">События / ${esc(item.title)} / Источник</p>
      </header>
      <div class="content content-tight">
        <section class="source-card">
          <h2 class="h3" style="width:420px;max-width:100%">${esc(item.title)}</h2>
          <div class="snippet"><b>01 ФАКТ</b><span>${esc(card.happened)}</span></div>
          <div class="snippet"><b>04 ПОЗИЦИЯ БАНКА</b><span>${esc(card.bank)}</span></div>
          <div class="snippet"><b>05 ВЫВОД МОДЕЛИ</b><span>${esc(card.model || "Модель не вызывалась")}</span></div>
          <p class="caption" style="width:420px;max-width:100%">Карточка остаётся открытой: можно продолжить работу</p>
        </section>
        <article class="doc">
          <div class="doc-head">
            <h2 class="body" style="font-weight:600">${esc(item.source_name)}</h2>
            <div class="spacer"></div>
            <span class="caption">${esc(item.published)}</span>
          </div>
          <div class="sheet">
            <p class="caption">${esc(item.source_url)}</p>
            <div class="highlight">
              <strong>Текст, который прочитал парсер:</strong>
              <p class="body">${esc(item.summary || item.title)}</p>
            </div>
          </div>
          <p class="caption" style="max-width:700px"><a href="${esc(item.source_url)}" target="_blank" rel="noopener noreferrer">Открыть первоисточник</a>.</p>
        </article>
      </div>
    </main>`;
}

function paint() {
  const root = document.getElementById("app");
  const draw = screens[state.screen] || renderHome;
  root.innerHTML = draw();
  root.querySelectorAll("[data-go]").forEach((node) => {
    node.addEventListener("click", () => {
      const itemId = node.getAttribute("data-item");
      if (itemId) {
        state.itemId = itemId;
      }
      const next = node.getAttribute("data-go");
      state.askOpen = false;
      if (screens[next]) {
        go(next);
      }
    });
  });
  root.querySelectorAll("[data-filter]").forEach((node) => {
    node.addEventListener("click", () => {
      const id = node.getAttribute("data-filter");
      state.filter = state.filter === id ? "" : id;
      paint();
    });
  });
  root.querySelectorAll("[data-choice]").forEach((node) => {
    node.addEventListener("click", () => {
      const [group, id] = node.getAttribute("data-choice").split(":");
      state[group] = state[group] === id ? "" : id;
      paint();
    });
  });
  root.querySelectorAll("[data-useful]").forEach((node) => {
    node.addEventListener("click", () => {
      const id = node.getAttribute("data-useful");
      state.useful = state.useful === id ? "" : id;
      paint();
    });
  });
  root.querySelectorAll("[data-prefill]").forEach((node) => {
    node.addEventListener("click", () => {
      state.asked = node.getAttribute("data-prefill");
      const field = root.querySelector("[name=q]");
      if (field) {
        field.value = state.asked;
        field.focus();
      } else {
        paint();
      }
    });
  });
  root.querySelectorAll("[data-menu]").forEach((node) => {
    node.addEventListener("click", (event) => {
      event.stopPropagation();
      const name = node.getAttribute("data-menu");
      state.openMenu = state.openMenu === name ? "" : name;
      paint();
    });
  });
  root.querySelectorAll("[data-pick]").forEach((node) => {
    node.addEventListener("click", (event) => {
      event.stopPropagation();
      const raw = node.getAttribute("data-pick") || "";
      const splitAt = raw.indexOf(":");
      chooseMenu(raw.slice(0, splitAt), raw.slice(splitAt + 1));
    });
  });
  const refresh = root.querySelector("[data-refresh]");
  if (refresh) {
    refresh.addEventListener("click", () => loadFeed(true));
  }
  root.querySelectorAll("[data-mode]").forEach((node) => {
    node.addEventListener("click", () => setMode(node.getAttribute("data-mode")));
  });
  const eventFormNode = root.querySelector("[data-event]");
  if (eventFormNode) {
    eventFormNode.addEventListener("submit", (event) => {
      event.preventDefault();
      const data = new FormData(eventFormNode);
      addEvent({
        title: String(data.get("title") || ""),
        body: String(data.get("body") || ""),
        published: String(data.get("published") || ""),
        url: String(data.get("url") || ""),
      });
    });
  }
  const analyze = root.querySelector("[data-analyze]");
  if (analyze) {
    analyze.addEventListener("submit", (event) => {
      event.preventDefault();
      const field = analyze.querySelector("[name=q]");
      state.asked = field.value.trim();
      runAnalysis(state.asked);
    });
  }
  const download = root.querySelector("[data-download]");
  if (download) {
    download.addEventListener("click", () => {
      const text = state.analysis && state.analysis.download;
      if (!text) {
        return;
      }
      const blob = new Blob([text], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "decision-brief-analysis.json";
      link.click();
      URL.revokeObjectURL(url);
    });
  }
  const save = root.querySelector("[data-save]");
  if (save) {
    save.addEventListener("click", () => {
      state.profileNote = state.hiddenTopic && state.hiddenTopic !== "Нет"
        ? "Скрытая тема применена к ленте. Остальные ответы в профиль не записаны."
        : "В профиль ничего не записано: этих сведений в нём нет.";
      paint();
    });
  }
  root.querySelectorAll("[data-ask]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const field = form.querySelector("[name=q]");
      const question = field.value.trim();
      if (!question) {
        return;
      }
      state.asked = question;
      state.askOpen = true;
      runAnalysis(question);
    });
  });
  const closeAsk = root.querySelector("[data-close-ask]");
  if (closeAsk) {
    closeAsk.addEventListener("click", () => {
      state.askOpen = false;
      paint();
    });
  }
  const manager = root.querySelector("[data-manager]");
  if (manager) {
    manager.addEventListener("click", () => {
      state.managerNote = "Обращение к менеджеру отмечено. Карточка остаётся открытой.";
      paint();
    });
  }
}

async function setMode(mode) {
  if (!mode || state.mode === mode) {
    return;
  }
  state.mode = mode;
  state.companyId = "";
  state.companies = [];
  state.itemId = "";
  state.analysis = null;
  await loadFeed(false);
}

async function addEvent(fields) {
  state.eventNote = "Добавляем материал.";
  paint();
  try {
    const response = await fetch("/api/events", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: state.mode, ...fields }),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Материал не добавлен");
    }
    state.eventNote = `Материалов добавлено: ${payload.added}. Лента пересчитана.`;
    state.companies = state.companies;
    await loadFeed(false);
  } catch (error) {
    state.eventNote = error instanceof Error ? error.message : "Материал не добавлен";
    state.loading = false;
    paint();
  }
}

async function runAnalysis(question) {
  state.analysisNote = "Собираем контекст, проверяем источники и вывод.";
  state.asked = question;
  paint();
  try {
    const response = await fetch("/api/analysis", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        mode: state.mode,
        company: state.companyId,
        role: state.roleId,
        question,
      }),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Анализ не собрался");
    }
    state.analysis = payload;
    state.analysisNote = "";
  } catch (error) {
    state.analysisNote = error instanceof Error ? error.message : "Анализ не собрался";
  }
  state.loading = false;
  paint();
}

async function loadBootstrap() {
  const response = await fetch(`/api/bootstrap?mode=${encodeURIComponent(state.mode)}`);
  if (!response.ok) {
    throw new Error("Список компаний не открылся");
  }
  const payload = await response.json();
  state.companies = payload.companies || [];
  state.roles = payload.roles || [];
  const ids = state.companies.map((company) => company.id);
  if (!ids.includes(state.companyId)) {
    state.companyId = payload.default_company || "";
  }
  if (!state.roleId) {
    state.roleId = payload.default_role || "";
  }
}

async function loadFeed(refresh) {
  state.loading = true;
  state.error = "";
  paint();
  try {
    if (!state.companies.length) {
      await loadBootstrap();
    }
    const params = new URLSearchParams({
      mode: state.mode,
      company: state.companyId,
      role: state.roleId,
    });
    if (refresh) {
      params.set("refresh", "1");
    }
    const response = await fetch(`/api/feed?${params}`);
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Лента не загрузилась");
    }
    state.feed = payload;
    state.roleId = payload.role.id;
    if (!items().some((row) => row.id === state.itemId)) {
      state.itemId = items()[0] ? items()[0].id : "";
    }
  } catch (error) {
    state.error = error instanceof Error ? error.message : "Лента не загрузилась";
  } finally {
    state.loading = false;
    paint();
  }
}

window.addEventListener("popstate", () => {
  applyRoute();
  paint();
});

function applyRoute() {
  const name = (location.hash || "#home").slice(1);
  if (name === "clarify") {
    state.screen = "card";
    state.askOpen = true;
    return;
  }
  state.screen = screens[name] ? name : "home";
}

document.addEventListener("click", () => {
  if (!state.openMenu) {
    return;
  }
  state.openMenu = "";
  paint();
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && state.openMenu) {
    state.openMenu = "";
    paint();
  }
});

applyRoute();
paint();
loadFeed(false);
