"""Interactive jury scenario: bank entry, personalised feed, agent and trace."""
from __future__ import annotations

import csv
import hashlib
import json
import os
from datetime import date
from urllib.parse import urlsplit

import streamlit as st

from decision_brief.agent import prepare_analysis
from decision_brief.classify import factors_in_text
from decision_brief.conclusion import client_from_env
from decision_brief.demo import DEMO_DATE, SAMPLE_DIR, demo_news
from decision_brief.feeds import dedupe_by_link, parse_rss
from decision_brief.models import NewsItem
from decision_brief.roles import Role
from decision_brief.screen import (
    company_labels, load_demo_companies, load_news, markdown_block,
    rank_feed, resolve_companies_path, role_choices,
)


def main():
    st.set_page_config(page_title="Decision Brief | Альфа-Бизнес", page_icon="А", layout="wide")
    st.markdown("<style>.stApp h1{letter-spacing:-.035em} div[data-testid='stMetricValue']{color:#ef3124}</style>", unsafe_allow_html=True)
    st.sidebar.title("Альфа-Бизнес")
    st.sidebar.caption("Демонстрационный интерфейс команды. Не банковская система.")
    if st.sidebar.button("Главная", width="stretch"):
        st.session_state["page"] = "home"
    if st.sidebar.button("Бизнес-аналитика", type="primary", width="stretch"):
        st.session_state["page"] = "analytics"
    st.sidebar.divider()
    st.sidebar.caption("Decision Brief · персональные события, риски и возможности")
    if st.session_state.get("page", "home") == "home":
        st.title("Добро пожаловать")
        st.write("Рабочее пространство руководителя компании")
        with st.container(border=True):
            st.subheader("Что меняется для вашего бизнеса?")
            st.write("Выберите компанию и свою роль. Узнайте, какие события важны, "
                     "как их оценивает банк и что стоит проверить.")
            if st.button("Открыть бизнес-аналитику", type="primary"):
                st.session_state["page"] = "analytics"
                st.rerun()
        st.info("Для проверки не требуется учётная запись. Все компании стартового набора вымышлены.")
        return
    _analytics()


def _analytics():
    st.title("События для вашего бизнеса")
    labels = ["Демонстрационные события", "Публичные RSS"]
    mode = st.selectbox("Источники", labels,
                        index=1 if os.getenv("DECISION_BRIEF_NEWS_MODE") == "live" else 0,
                        key="news_mode")
    demo = mode == labels[0]
    as_of = DEMO_DATE if demo else date.today()
    path = resolve_companies_path()
    if demo and not os.getenv("DECISION_BRIEF_COMPANIES"):
        path = SAMPLE_DIR / "companies.csv"
    try:
        companies = load_demo_companies(path)
    except (OSError, UnicodeError, csv.Error, ValueError):
        st.error("Не удалось прочитать CSV компаний. Проверьте DECISION_BRIEF_COMPANIES и формат файла.")
        return
    if not companies:
        st.warning("В CSV нет компаний, подходящих по выручке. Проверьте профиль и единицы измерения.")
        return
    if demo:
        st.info(f"Синтетические события; дата сценария {as_of:%d.%m.%Y}. "
                "Банковская аналитика — отдельные материалы кейса с собственными датами.")
    by_company, by_role = dict(company_labels(companies)), dict(role_choices())
    left, right = st.columns([2, 1])
    company_name = left.selectbox("Компания", list(by_company), key="company")
    role_name = right.selectbox("Роль", list(by_role), key="role")
    company, role = by_company[company_name], by_role[role_name]
    refresh = st.button("Обновить ленту")
    cache_key = "demo_news" if demo else "live_news"
    if refresh or cache_key not in st.session_state:
        if demo:
            st.session_state[cache_key] = demo_news()
        else:
            with st.spinner("Читаем публичные RSS..."):
                loaded = load_news()
            if loaded.failed:
                st.warning("RSS недоступны. Сохранена предыдущая лента этого режима. "
                           "Для автономной проверки выберите демонстрационные события.")
            else:
                st.session_state[cache_key] = list(loaded.items)
    items = list(st.session_state.get(cache_key, []))
    extras_key = "extra_demo" if demo else "extra_live"
    _add_event(as_of, extras_key)
    items = dedupe_by_link(items + st.session_state.get(extras_key, []))
    ranked = rank_feed(company, items, role, as_of=as_of)
    a, b, c = st.columns(3)
    a.metric("Входящих событий", len(items))
    b.metric("Релевантных событий", len(ranked))
    c.metric("Роль", role_name)
    if not ranked:
        st.info("Релевантных событий пока нет. Добавьте новый материал или смените компанию и роль.")
        return

    client = client_from_env()
    if client is None:
        st.caption("Режим правил: LLM не подключена. Для генерации нужны разрешённая модель, HTTPS-шлюз и ключ в окружении.")
    else:
        st.caption(f"Настроена модель {client.model}. Вызов выполняется по кнопке; не более двух попыток на анализ.")
    fingerprint = hashlib.sha256(repr((company, items, role, as_of)).encode()).hexdigest()
    state_key = "analysis_" + fingerprint
    payments_env = os.getenv("DECISION_BRIEF_PAYMENTS", "").strip()
    from pathlib import Path
    payments = Path(payments_env) if payments_env else (
        SAMPLE_DIR / "payments.csv" if path.resolve() == (SAMPLE_DIR / "companies.csv").resolve() else None)
    kwargs = dict(as_of=as_of, companies_path=path, payments_path=payments)
    if state_key not in st.session_state:
        # Viewing the feed is always free of model calls.
        st.session_state[state_key] = prepare_analysis(company, items, role, **kwargs)
    with st.form("analysis_form"):
        question = st.text_input("Уточняющий вопрос", max_chars=1000,
                                 placeholder="Как события влияют на стоимость финансирования?")
        submitted = st.form_submit_button("Подготовить анализ", type="primary")
    if submitted:
        with st.spinner("Собираем контекст, проверяем источники и вывод..."):
            result = prepare_analysis(company, items, role, question=question, client=client, **kwargs)
        st.session_state[state_key] = result
    result = st.session_state[state_key]
    analysis_tab, news_tab = st.tabs(["Выводы и источники", "Лента событий"])
    with analysis_tab:
        _result(result, fingerprint)
    with news_tab:
        for row in ranked[:20]:
            with st.container(border=True):
                st.subheader(row.item.title)
                st.caption(f"{row.item.published_on:%d.%m.%Y} · {row.item.source_name} · {row.relevance.value} · {row.score:.2f}")
                st.write(row.item.summary)
                st.caption("Почему показано: " + "; ".join(row.reasons))
                _source_link(row.item.source_url)


def _add_event(as_of, extras_key):
    with st.expander("Проверить новую новость или RSS-файл"):
        st.caption("Материалы обрабатываются тем же классификатором и ранжированием. Ссылки из файла не скачиваются.")
        with st.form("event_form"):
            title = st.text_input("Заголовок", max_chars=300)
            body = st.text_area("Текст события", max_chars=4000)
            published = st.date_input("Дата публикации", value=as_of)
            url = st.text_input("Ссылка на первоисточник (необязательно)", max_chars=1000)
            uploaded = st.file_uploader("Или загрузите RSS 2.0 (до 2 МБ)", type=["xml", "rss"])
            add = st.form_submit_button("Добавить материал")
        if not add:
            return
        try:
            if uploaded is not None:
                if uploaded.size > 2_000_000:
                    raise ValueError("Файл превышает 2 МБ.")
                from decision_brief.feeds import decode_rss
                new_items = parse_rss(decode_rss(uploaded.getvalue()), "Загруженный RSS")[:100]
                if not new_items:
                    raise ValueError("Не найдены элементы с заголовком, HTTP(S)-ссылкой и корректной датой.")
            else:
                if not title.strip() or not body.strip():
                    raise ValueError("Укажите заголовок и текст события.")
                parsed = urlsplit(url)
                if url and (parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username):
                    raise ValueError("Ссылка должна быть HTTP(S), без учётных данных.")
                identifier = hashlib.sha256((title + body).encode()).hexdigest()[:12]
                new_items = [NewsItem(title.strip(), published, "Введено пользователем",
                    url or f"https://example.invalid/user-event/{identifier}", body.strip(),
                    factors_in_text(title + " " + body))]
            st.session_state[extras_key] = dedupe_by_link(st.session_state.get(extras_key, []) + new_items)[-100:]
            st.success(f"Материалов добавлено: {len(new_items)}. Лента пересчитана.")
        except Exception as exc:
            st.error(f"Материал не добавлен: {type(exc).__name__}. Проверьте поля, размер и формат RSS.")


def _result(result, fingerprint):
    st.subheader("Персональная интерпретация")
    if result.status == "model_verified":
        st.caption("Вывод LLM: проверены структура, ссылки и числа. Смысловые выводы требуют экспертной оценки.")
    else:
        st.caption("Интерпретация по правилам; это не ответ языковой модели.")
    if result.question:
        st.write("Вопрос:", result.question)
    for title, row in result.claims.items():
        st.markdown(f"**{title.capitalize()}**")
        st.markdown(markdown_block(row["text"]))
        st.caption("Основание: " + ", ".join(row["source_ids"]))
    for gap in result.gaps:
        st.warning(gap)
    st.subheader("Аналитика Альфа-Банка")
    st.caption("Пересказы материалов кейса. Позиция банка датирована и отделена от выводов системы.")
    for source in result.evidence:
        if source.kind == "bank":
            with st.container(border=True):
                st.write(source.title)
                st.write(source.text)
                _source_link(source.url)
    with st.expander("Источники, признаки клиента и журнал шагов"):
        for source in result.evidence:
            st.markdown(f"**{source.id} · {source.title}**")
            st.text(source.text)
            _source_link(source.url)
        st.dataframe([{"Шаг": step.tool, "Статус": step.status, "Результат": step.detail}
                      for step in result.trace], width="stretch", hide_index=True)
    st.download_button("Скачать анализ и журнал (JSON)", result.to_json(),
                        file_name="decision-brief-analysis.json", mime="application/json")
    feedback = st.radio("Насколько полезен анализ?", ["Не оценено", "Полезен", "Требует проверки"],
                        horizontal=True, key="feedback_" + fingerprint)
    if feedback != "Не оценено":
        st.caption("Оценка сохранена в текущей сессии.")
        st.download_button("Скачать оценку", json.dumps({"company": result.company_id,
            "role": result.role, "feedback": feedback}, ensure_ascii=False),
            file_name="decision-brief-feedback.json", mime="application/json")


def _source_link(url):
    if url.startswith(("http://", "https://")) and "example.invalid" not in url:
        st.link_button("Открыть первоисточник", url)
    elif url:
        st.caption("Синтетический или введённый материал: внешнего первоисточника нет.")


if __name__ == "__main__":
    main()
