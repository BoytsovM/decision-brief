/* Figma shell for page "02 Экраны". News rows come from /api/feed. */

const screens = {
  home: renderHome,
  feed: renderFeed,
  card: renderCard,
  profile: renderProfile,
  source: renderSource,
};

function initialMode() {
  const requested = new URLSearchParams(window.location.search).get("mode");
  return requested === "demo" ? "demo" : "live";
}

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
  mode: initialMode(),
  analysis: null,
  analysisNote: "",
  cardModels: {},
  cardEffects: {},
  cardTitles: {},
  cardQuestions: {},
  cardAnswers: {},
  cardModelPending: "",
  cardAnswerPending: "",
  ownDraft: {},
  ownThreads: {},
  ownPending: "",
  ownPendingQuestion: "",
  replyQuestion: "",
  askOpen: false,
  managerNote: "",
  openMenu: "",
  period: "all",
  level: "",
  topic: "",
};

const FEED_POLL_MS = 3000;
let feedEpoch = 0;
let quietInFlight = false;

const periods = [
  ["all", "Все"],
  ["today", "Сегодня"],
  ["week", "Неделя"],
  ["month", "Месяц"],
];

const levels = [
  ["all", "Все"],
  ["high", "Важно"],
  ["mid", "К сведению"],
];

const topicFilters = [
  ["all", "Все"],
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
  if (name === "level") {
    state.level = value === "all" ? "" : value;
    paint();
    return;
  }
  if (name === "topic") {
    state.topic = value === "all" ? "" : value;
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
  const file = level === "high" ? "dot-important.svg" : "dot-notice.svg";
  return `<img class="dot" src="assets/${file}" width="8" height="8" alt="">`;
}

function importance(level, label) {
  const tone = level === "high" ? "importance-high" : "importance-mid";
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
  if (state.period === "week") {
    return published >= shiftIso(asOf, -7);
  }
  if (state.period === "month") {
    return published >= `${asOf.slice(0, 8)}01`;
  }
  return true;
}

function visibleFeed() {
  const hidden = hiddenIds();
  return items().filter((item) => {
    const ids = (item.factors || []).map((factor) => factor.id);
    if (hidden.some((id) => ids.includes(id))) {
      return false;
    }
    if (state.level && item.level !== state.level) {
      return false;
    }
    if (state.topic) {
      const wanted = topicFactors[state.topic] || [];
      return ids.some((id) => wanted.includes(id));
    }
    return true;
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

function namedMenu(name, title, rows, value) {
  const current = rows.find((row) => row[0] === (value || "all")) || rows[0];
  const options = rows.map(([id, label]) => ({ id, label }));
  const selected = value ? "chip is-on" : "chip";
  return dropdown(name, selected, `${title}: ${current[1]}`, options, value || "all");
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
          <strong>${esc(displayTitle(item))}</strong>
          <span class="caption">${esc(item.why)}</span>
        </button>`).join("")
    : `<p class="caption">${esc(state.loading ? "Читаем ленты." : "Нет событий выше порога.")}</p>`;
  return `
    <main class="screen">
      ${header("home")}
      <div class="content">
        <section class="home-main">
          <h1 class="h1">Добрый день</h1>
          <div class="accounts">
            <article class="account"><p class="caption">Расчётный счёт</p><strong>Сумма из банка</strong></article>
            <article class="account"><p class="caption">Депозиты</p><strong>Сумма из банка</strong></article>
            <article class="account"><p class="caption">Кредиты</p><strong>Сумма из банка</strong></article>
          </div>
          <section class="payments">
            <h2 class="h3">Последние платежи</h2>
            <p class="caption">Обычный блок интернет-банка, в прототипе не детализируем</p>
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

function profileFields() {
  const company = state.feed ? state.feed.company : null;
  const rows = company && Array.isArray(company.rows) ? company.rows : [];
  if (!rows.length) {
    return `<p class="caption">Профиль ещё не загружен.</p>`;
  }
  const value = (label) => {
    const row = rows.find((item) => item.label === label);
    return row ? String(row.value) : "";
  };
  const industry = value("Отрасль").replace(", ОКВЭД ", " (ОКВЭД ");
  const industryText = industry.includes("(ОКВЭД ") ? `${industry})` : industry;
  const revenue = value("Выручка");
  const staff = value("Штат");
  const scale = [`Выручка ${revenue}`, staff].filter((part) => part && part !== "Выручка ").join(", ");
  const products = value("Продукты в Альфе");
  const titled = products ? products.charAt(0).toUpperCase() + products.slice(1) : "";
  const trade = value("ВЭД");
  const ved = !trade || trade === "не отмечена" ? "не отмечена" : `${trade} (по данным ФТС)`;
  const region = company.region ? company.region : "не указан";
  const fields = [
    ["Отрасль", industryText],
    ["Масштаб", scale],
    ["Продукты в Альфе", titled],
    ["ВЭД", ved],
    ["Регион", region],
  ];
  return fields.map(([label, text]) => `
    <div class="field"><p class="caption">${esc(label)}</p><p class="body">${esc(text)}</p></div>
  `).join("");
}

function renderFeed() {
  const rows = visibleFeed().filter(inPeriod);
  const cards = rows.length
    ? rows.map((item) => `
      <button class="feed-card" type="button" data-go="card" data-item="${esc(item.id)}">
        <div class="meta-row feed-meta">
          ${importance(item.level, item.label)}
          <span class="caption">${esc(item.published)} · ${esc(item.source_name)}</span>
          <span class="caption event-score">Значимость ${esc(item.score)}</span>
        </div>
        <h2 class="h3">${esc(displayTitle(item))}</h2>
        <p class="body muted">Почему вам: ${esc(item.why)}</p>
        <div class="factors">${(item.factors || []).map((factor) => `<span class="factor">${esc(factor.label)}</span>`).join("")}</div>
      </button>`).join("")
    : `<p class="body">${esc(state.error || (state.loading ? "Считаем ленту." : "Нет событий по этим фильтрам."))}</p>`;
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
          <p class="body muted">Мы отобрали события, которые влияют на вашу компанию, и объяснили почему. Обновлено <span data-updated>${esc(updated)}</span>.</p>
          ${notice()}
          <div class="filters">
            ${roleMenu()}
            ${periodMenu()}
            ${namedMenu("level", "Важность", levels, state.level)}
            ${namedMenu("topic", "Тема", topicFilters, state.topic)}
          </div>
          <div class="feed-scroll">
            <div class="feed-scroll-list" role="region" aria-label="Спарсенные события" tabindex="0">${cards}</div>
          </div>
          <p class="caption">В списке ${rows.length} из ${incoming} спарсенных событий. Выше порога: ${ranked}.</p>
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

function withModelPoint(rows, text) {
  const base = Array.isArray(rows) ? rows.slice() : [];
  if (!text) {
    return base;
  }
  return [{ kind: "ai", text }].concat(base);
}

function gapLine(card, extra) {
  const modelGap = String(extra || "").trim();
  if (modelGap) {
    const text = modelGap.startsWith("Каких данных нет")
      ? modelGap
      : `Каких данных нет: ${modelGap.replace(/\.$/, "")}.`;
    return `<p class="gap-line">${esc(text)}</p>`;
  }
  const stored = card.effects && card.effects.gaps ? card.effects.gaps : "";
  return stored ? `<p class="gap-line">${esc(stored)}</p>` : "";
}

function effectsBlock(card, item) {
  const effects = card.effects || {};
  const model = item && state.cardEffects[item.id] ? state.cardEffects[item.id] : {};
  return block("ai", "03", "ПОСЛЕДСТВИЯ", "Риски, возможности, факторы", `
    <div class="cols">
      ${effectColumn("Риски", "col-risk", withModelPoint(effects.risks, model.risk), "Отдельный риск по профилю не выделен.")}
      ${effectColumn("Возможности", "col-chance", withModelPoint(effects.opportunities, model.opportunity), "Отдельная возможность по профилю не выделена.")}
      ${effectColumn("Что повлияет дальше", "col-next", withModelPoint(effects.next, model.next), "Следующий ориентир по срокам — в позиции банка ниже.")}
    </div>
    ${gapLine(card, model.gaps)}`);
}

function flowingText(text, empty) {
  const value = String(text || "").replace(/\s*\n+\s*/g, " ").replace(/[ \t]{2,}/g, " ").trim();
  if (!value) {
    return empty ? `<p class="body">${esc(empty)}</p>` : "";
  }
  return `<p class="body">${esc(value)}</p>`;
}

function modelParagraphs(text) {
  return flowingText(text, "");
}

function prose(text) {
  return flowingText(text, "");
}

function externalMaterial(url) {
  const value = String(url || "");
  return /^https?:\/\//i.test(value) && !/example\.invalid/i.test(value);
}

function materialControl(item) {
  if (externalMaterial(item.source_url)) {
    return `<a class="text-btn" href="${esc(item.source_url)}" target="_blank" rel="noopener noreferrer">открыть материал</a>`;
  }
  return `<button class="text-btn" type="button" data-go="source" data-item="${esc(item.id)}">открыть материал</button>`;
}

function bankParagraphs(text) {
  return flowingText(text, "Свежей позиции банка по этой теме нет.");
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
  const modelText = cardModelText(item);
  const modelAside = modelText ? "Синтез ИИ" : "Запрос к шлюзу";
  const modelBody = modelText
    ? `<div class="claim">${origin("ai")}<div class="stack">${modelParagraphs(modelText)}</div></div>`
    : state.cardModelPending === item.id
      ? aiWait()
      : `<div class="claim">${origin("ai")}<div class="stack">${modelParagraphs("Модель готовит вывод по этому событию.")}</div></div>`;
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
          <h1 class="h1">${esc(displayTitle(item))}</h1>
          ${block("ink", "01", "ФАКТ", "", `
            <div class="claim">${origin("fact")}<div class="stack">${prose(card.happened)}</div></div>`)}
          ${block("mid", "02", "СВЯЗЬ С КОМПАНИЕЙ", "Профиль компании", `
            <div class="claim">${origin("fact")}<div class="stack">${prose(card.why || "Для этого события ранжирование не назвало отдельную причину.")}</div></div>`)}
          ${effectsBlock(card, item)}
          ${block("bank", "04", "ПОЗИЦИЯ БАНКА", "Материал банка", `
            <div class="claim">${origin("bank")}<div class="stack">${bankParagraphs(card.bank)}</div></div>`)}
          ${block("ai", "05", "ВЫВОД МОДЕЛИ", modelAside, `
            ${modelBody}
            ${modelQuestionBar(item)}
            ${ownQuestionForm(item)}`)}
          ${block("ink", "06", "ПЕРЕХОД К ИСТОЧНИКУ", "Основания вывода", `
            <p class="body">${esc(item.source_name)} · ${materialControl(item)} · <button class="text-btn" type="button" data-go="source" data-item="${esc(item.id)}">карточка источника</button></p>
            ${card.signs ? `<p class="body">${esc(card.signs)}</p>` : ""}`)}
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
      <p>Блоки 01–04 собраны из новости, профиля и карточки банка. Блок 05 заполняет подключённая модель, когда карточка открыта. Позицию банка модель не заменяет.</p>
    </section>`;
}

function clarifyPanel() {
  const item = selected();
  const title = item ? displayTitle(item) : "Событие не выбрано";
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
      ${state.replyQuestion ? `<p class="body">Вопрос: ${esc(state.replyQuestion)}</p>` : ""}
      ${asked}
      ${answer}
      <div class="suggests">
        ${suggestions.map((line) => `<button class="suggest" type="button" data-prefill="${esc(line)}">${esc(line)}</button>`).join("")}
      </div>
      <form class="panel-input" data-ask="1">
        <input name="q" type="text" placeholder="${state.replyQuestion ? "Ваш ответ" : "Ваш вопрос"}" value="${state.replyQuestion ? "" : esc(state.asked)}">
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

function profileBankRows(company) {
  const rows = company && Array.isArray(company.rows) ? company.rows : [];
  const value = (label) => {
    const row = rows.find((item) => item.label === label);
    return row ? String(row.value) : "";
  };
  const scale = [value("Выручка"), value("Штат")].filter(Boolean).join(", ");
  const trade = value("ВЭД");
  const ved = !trade || trade === "не отмечена"
    ? "Не отмечена"
    : `Есть, ${trade} (данные ФТС)`;
  const products = value("Продукты в Альфе");
  const titled = products ? products.charAt(0).toUpperCase() + products.slice(1) : "";
  const payments = company && Array.isArray(company.payments) ? company.payments.length : 0;
  const counterparties = payments
    ? `${recipientCount(payments)}; события по ним попадают в ленту, если доля от 10%`
    : "События по контрагентам попадают в ленту, если доля от 10%";
  return [
    ["Отрасль", value("Отрасль")],
    ["Выручка и масштаб", scale],
    ["Группа компаний", "Учитываем события по всей группе"],
    ["Продукты в Альфе", titled],
    ["ВЭД", ved],
    ["Крупные контрагенты", counterparties],
  ];
}

function recipientCount(count) {
  const mod10 = count % 10;
  const mod100 = count % 100;
  let word = "получателей";
  if (mod10 === 1 && mod100 !== 11) {
    word = "получатель";
  } else if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) {
    word = "получателя";
  }
  return `${count} ${word} платежей`;
}

function renderProfile() {
  const company = state.feed ? state.feed.company : null;
  const bankRows = profileBankRows(company).map(([label, value]) => `
    <div class="row"><dt>${esc(label)}</dt><dd>${esc(value)}</dd></div>
  `).join("");
  return `
    <main class="screen">
      ${header("feed")}
      <div class="content stack" style="gap:16px">
        <h1 class="h1">Что сервис знает о компании</h1>
        <p class="body muted profile-lead">Эти данные определяют, какие события попадут в вашу ленту. Часть мы берём из банка, часть можете уточнить вы: тогда выводы станут точнее, а пометок «вывод ИИ» станет меньше.</p>
        <div class="columns">
          <section class="profile-card">
            <h2 class="h3">Из данных банка</h2>
            <dl>${bankRows}</dl>
          </section>
          <section class="profile-card profile-card-edit">
            <h2 class="h3">Уточните сами</h2>
            <p class="caption profile-hint">Этого нет в данных банка, сейчас модель делает предположение</p>
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
        <p class="crumb">События / ${esc(displayTitle(item))} / Источник</p>
      </header>
      <div class="content content-tight">
        <section class="source-card">
          <h2 class="h3" style="width:420px;max-width:100%">${esc(displayTitle(item))}</h2>
          <div class="snippet"><b>01 ФАКТ</b><span>${esc(card.happened)}</span></div>
          <div class="snippet"><b>04 ПОЗИЦИЯ БАНКА</b><span>${esc(card.bank)}</span></div>
          <div class="snippet"><b>05 ВЫВОД МОДЕЛИ</b><span>${esc(cardModelText(item) || "Модель готовит вывод по этому событию.")}</span></div>
          <p class="caption" style="width:420px;max-width:100%">Карточка остаётся открытой: можно продолжить работу</p>
        </section>
        <article class="doc">
          <div class="doc-head">
            <h2 class="body" style="font-weight:600">${esc(item.source_name)}</h2>
            <div class="spacer"></div>
            <span class="caption">${esc(item.published)}</span>
          </div>
          <div class="sheet">
            <h3 class="h3">${esc(item.title)}</h3>
            <div class="stack">${prose(item.summary || item.title)}</div>
          </div>
          ${externalMaterial(item.source_url)
            ? `<p class="caption" style="max-width:700px"><a href="${esc(item.source_url)}" target="_blank" rel="noopener noreferrer">Открыть страницу источника</a>.</p>`
            : `<p class="body">Внешней страницы у этого материала нет. Выше текст, который сервис прочитал и использовал в карточке.</p>`}
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
  root.querySelectorAll("[data-help-panel]").forEach((panel) => {
    panel.addEventListener("click", (event) => event.stopPropagation());
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
  const save = root.querySelector("[data-save]");
  if (save) {
    save.addEventListener("click", () => {
      state.profileNote = state.hiddenTopic && state.hiddenTopic !== "Нет"
        ? "Скрытая тема применена к ленте. Остальные ответы в профиль не записаны."
        : "В профиль ничего не записано: этих сведений в нём нет.";
      go("feed");
    });
  }
  root.querySelectorAll("[data-own]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const item = selected();
      const field = form.querySelector("input");
      const question = field ? field.value.trim() : "";
      if (!item || !question || state.ownPending === item.id) {
        return;
      }
      state.ownDraft[item.id] = "";
      askOwn(item.id, question);
    });
  });
  const reply = root.querySelector("[data-reply]");
  if (reply) {
    reply.addEventListener("click", () => {
      const question = reply.getAttribute("data-reply") || "";
      const item = selected();
      if (!question || !item || state.cardAnswerPending === item.id) {
        return;
      }
      askModel(item.id, question);
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
  scheduleFeedWindow();
  ensureCardModel();
}

function displayTitle(item) {
  if (!item) {
    return "";
  }
  return item.title || item.headline || "";
}

function aiWait() {
  return `<div class="claim">${origin("ai")}<span class="ai-wait" role="status" aria-label="Модель отвечает"><i></i><i></i><i></i></span></div>`;
}

function ownPair(row) {
  const bar = `<div class="ask-inline"><p>Вопрос: ${esc(row.question)}</p></div>`;
  if (row.note) {
    return `${bar}<p class="own-reject">${esc(row.note)}</p>`;
  }
  return `${bar}<div class="claim">${origin("ai")}<div class="stack">${modelParagraphs(row.answer)}</div></div>`;
}

function ownQuestionForm(item) {
  if (!item || !state.cardAnswers[item.id]) {
    return "";
  }
  const rows = state.ownThreads[item.id] || [];
  const history = rows.map((row) => ownPair(row)).join("");
  const pending = state.ownPending === item.id;
  const waiting = pending
    ? `${state.ownPendingQuestion ? `<div class="ask-inline"><p>Вопрос: ${esc(state.ownPendingQuestion)}</p></div>` : ""}${aiWait()}`
    : `<form class="composer own-ask" data-own="1">
        <input name="followup" type="text" maxlength="240" autocomplete="off" placeholder="Хотите задать свой вопрос?" value="">
        <button class="btn btn-secondary" type="submit">Спросить</button>
      </form>`;
  return `<div class="own-thread">${history}${waiting}</div>`;
}

function rememberOwn(itemId, question, answer, note) {
  const thread = state.ownThreads[itemId] ? state.ownThreads[itemId].slice() : [];
  thread.push({ question, answer, note });
  state.ownThreads[itemId] = thread;
}

function askOwn(itemId, question) {
  state.ownPending = itemId;
  state.ownPendingQuestion = question;
  state.askOpen = false;
  paint();
  fetch("/api/card-answer", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      mode: state.mode,
      company: state.companyId,
      role: state.roleId,
      item: itemId,
      question,
      own: true,
    }),
  })
    .then(async (response) => {
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error || "Вызов модели не выполнен.");
      }
      return payload;
    })
    .then((payload) => {
      if (payload.status === "rejected" || payload.status === "unavailable" || payload.status === "failed" || payload.status === "empty") {
        rememberOwn(itemId, question, "", payload.error || "Модель не ответила на вопрос.");
        return;
      }
      rememberOwn(itemId, question, payload.answer || payload.error || "Модель не ответила на вопрос.", "");
    })
    .catch((error) => {
      rememberOwn(itemId, question, "", error instanceof Error ? error.message : "Вызов модели не выполнен.");
    })
    .finally(() => {
      if (state.ownPending === itemId) {
        state.ownPending = "";
        state.ownPendingQuestion = "";
      }
      const current = selected();
      if (current && current.id === itemId && state.screen === "card") {
        paint();
        const field = document.querySelector("[data-own] input");
        if (field) {
          field.focus();
        }
      }
    });
}

function modelQuestionBar(item) {
  const stored = item && state.cardQuestions[item.id] ? state.cardQuestions[item.id] : "";
  const question = stored.replace(/^вопрос:\s*/i, "").replace(/\.$/, "");
  const pending = item && state.cardAnswerPending === item.id;
  const answer = item && state.cardAnswers[item.id] ? state.cardAnswers[item.id] : "";
  const reply = answer
    ? `<div class="claim">${origin("ai")}<div class="stack">${modelParagraphs(answer)}</div></div>`
    : pending
      ? aiWait()
      : "";
  if (!question) {
    return "";
  }
  const button = answer || pending
    ? ""
    : `<button class="btn btn-secondary" type="button" data-reply="${esc(question)}">Ответить</button>`;
  return `<div class="ask-inline"><p>Вопрос: ${esc(question)}</p>${button}</div>${reply}`;
}

function askModel(itemId, question) {
  state.cardAnswerPending = itemId;
  state.askOpen = false;
  paint();
  fetch("/api/card-answer", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      mode: state.mode,
      company: state.companyId,
      role: state.roleId,
      item: itemId,
      question,
    }),
  })
    .then(async (response) => {
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error || "Вызов модели не выполнен.");
      }
      state.cardAnswers[itemId] = payload.answer || payload.error || "Модель не ответила на вопрос.";
    })
    .catch((error) => {
      state.cardAnswers[itemId] = error instanceof Error ? error.message : "Вызов модели не выполнен.";
    })
    .finally(() => {
      if (state.cardAnswerPending === itemId) {
        state.cardAnswerPending = "";
      }
      const current = selected();
      if (current && current.id === itemId && state.screen === "card") {
        paint();
      }
    });
}

function cardModelText(item) {
  if (!item) {
    return "";
  }
  if (state.cardModels[item.id]) {
    return state.cardModels[item.id];
  }
  return item.card && item.card.model ? item.card.model : "";
}

function ensureCardModel() {
  if (state.screen !== "card" && state.screen !== "source") {
    return;
  }
  const item = selected();
  if (!item || !state.companyId || cardModelText(item) || state.cardModelPending === item.id) {
    return;
  }
  const itemId = item.id;
  state.cardModelPending = itemId;
  queueMicrotask(() => {
    const current = selected();
    if (
      current
      && current.id === itemId
      && state.cardModelPending === itemId
      && !cardModelText(current)
    ) {
      paint();
    }
  });
  const params = new URLSearchParams({
    mode: state.mode,
    company: state.companyId,
    role: state.roleId,
    item: itemId,
  });
  fetch(`/api/card-model?${params}`)
    .then(async (response) => {
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error || "Вызов модели не выполнен.");
      }
      return payload;
    })
    .then((payload) => {
      state.cardModels[itemId] = payload.model || payload.error || "Вызов модели не выполнен.";
      state.cardEffects[itemId] = payload.effects || {};
      if (payload.headline) {
        state.cardTitles[itemId] = payload.headline;
      }
      if (payload.question) {
        state.cardQuestions[itemId] = payload.question;
      }
    })
    .catch((error) => {
      state.cardModels[itemId] = error instanceof Error ? error.message : "Вызов модели не выполнен.";
    })
    .finally(() => {
      if (state.cardModelPending === itemId) {
        state.cardModelPending = "";
      }
      const current = selected();
      if (current && current.id === itemId && (state.screen === "card" || state.screen === "source")) {
        paint();
      }
    });
}

function fitFeedWindow() {
  const list = document.querySelector(".feed-scroll-list");
  if (!list) {
    return false;
  }
  const cards = [...list.querySelectorAll(".feed-card")];
  if (cards.length <= 5) {
    list.style.maxHeight = "none";
    return true;
  }
  const styles = getComputedStyle(list);
  const gap = parseFloat(styles.rowGap || styles.gap) || 0;
  const height = cards.slice(0, 5).reduce((sum, card) => sum + card.offsetHeight, 0) + gap * 4;
  if (height < 40) {
    return false;
  }
  list.style.maxHeight = `${Math.ceil(height)}px`;
  return true;
}

let feedWindowObserver = null;

function scheduleFeedWindow() {
  requestAnimationFrame(() => {
    if (!fitFeedWindow()) {
      requestAnimationFrame(() => fitFeedWindow());
    }
  });
  const box = document.querySelector(".feed-scroll");
  if (!box) {
    return;
  }
  if (feedWindowObserver) {
    feedWindowObserver.disconnect();
  }
  let width = box.clientWidth;
  feedWindowObserver = new ResizeObserver(() => {
    if (!box.isConnected || box.clientWidth === width) {
      return;
    }
    width = box.clientWidth;
    fitFeedWindow();
  });
  feedWindowObserver.observe(box);
  if (document.fonts) {
    document.fonts.ready.then(() => {
      if (box.isConnected) {
        fitFeedWindow();
      }
    });
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

function feedShowsNews() {
  return state.screen === "home" || state.screen === "feed" || state.screen === "card" || state.screen === "source";
}

function feedStamp(feed) {
  if (!feed) {
    return "";
  }
  const rows = (feed.items || []).map((item) => (
    [item.id, item.score, item.title, item.headline, item.why, item.level].join("|")
  ));
  return [feed.notice || "", feed.as_of || "", feed.ranked, rows.join("\n")].join("\n");
}

function captureView() {
  const active = document.activeElement;
  const list = document.querySelector(".feed-scroll-list");
  const fields = [...document.querySelectorAll("input, textarea")].map((element) => ({
    name: element.name,
    value: element.value,
    focused: element === active,
    start: element.selectionStart,
    end: element.selectionEnd,
  }));
  return { scrollY: window.scrollY, listScroll: list ? list.scrollTop : 0, fields };
}

function restoreView(saved) {
  window.scrollTo(0, saved.scrollY);
  const list = document.querySelector(".feed-scroll-list");
  if (list) {
    list.scrollTop = saved.listScroll;
  }
  saved.fields.forEach((field) => {
    if (!field.name) {
      return;
    }
    const element = document.querySelector(`[name="${field.name}"]`);
    if (!element) {
      return;
    }
    element.value = field.value;
    if (!field.focused) {
      return;
    }
    element.focus();
    if (field.start == null) {
      return;
    }
    try {
      element.setSelectionRange(field.start, field.end);
    } catch (_error) {
      // Date inputs do not accept a caret position.
    }
  });
}

function applyFeed(payload) {
  state.feed = payload;
  state.roleId = payload.role.id;
  if (!items().some((row) => row.id === state.itemId)) {
    state.itemId = items()[0] ? items()[0].id : "";
  }
}

async function refreshFeedQuietly() {
  if (quietInFlight || state.loading || !state.companyId) {
    return;
  }
  quietInFlight = true;
  const epoch = feedEpoch;
  try {
    const params = new URLSearchParams({
      mode: state.mode,
      company: state.companyId,
      role: state.roleId,
    });
    const response = await fetch(`/api/feed?${params}`);
    const payload = await response.json();
    if (epoch !== feedEpoch || state.loading || !response.ok || !state.feed) {
      return;
    }
    if (feedStamp(payload) === feedStamp(state.feed)) {
      state.feed.loaded_at = payload.loaded_at;
      const node = document.querySelector("[data-updated]");
      if (node) {
        node.textContent = payload.loaded_at;
      }
      return;
    }
    const saved = captureView();
    applyFeed(payload);
    if (!feedShowsNews()) {
      return;
    }
    paint();
    restoreView(saved);
  } catch (_error) {
    // A missed poll keeps the feed already on screen.
  } finally {
    quietInFlight = false;
  }
}

function watchFeed() {
  window.setInterval(() => {
    if (!document.hidden) {
      refreshFeedQuietly();
    }
  }, FEED_POLL_MS);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) {
      refreshFeedQuietly();
    }
  });
}

async function loadFeed(refresh) {
  const epoch = ++feedEpoch;
  state.loading = true;
  state.error = "";
  paint();
  try {
    if (!state.companies.length) {
      await loadBootstrap();
    }
    if (epoch !== feedEpoch) {
      return;
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
    if (epoch !== feedEpoch) {
      return;
    }
    if (!response.ok) {
      throw new Error(payload.error || "Лента не загрузилась");
    }
    applyFeed(payload);
  } catch (error) {
    if (epoch !== feedEpoch) {
      return;
    }
    state.error = error instanceof Error ? error.message : "Лента не загрузилась";
  } finally {
    if (epoch === feedEpoch) {
      state.loading = false;
      paint();
    }
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
watchFeed();
loadFeed(true);
