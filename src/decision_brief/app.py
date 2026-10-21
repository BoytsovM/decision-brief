"""Streamlit screen: pick a demo company and a role, then read the feed.

Run from the repository root with ``PYTHONPATH=src``:

    python -m streamlit run src/decision_brief/app.py
"""

from __future__ import annotations

import csv
from datetime import date

import streamlit as st

from decision_brief.conclusion import ModelClient, client_from_env
from decision_brief.models import CompanyProfile, NewsItem
from decision_brief.roles import Role
from decision_brief.screen import (
    CardView,
    NewsLoad,
    card_blocks,
    card_view,
    companies_source_label,
    company_labels,
    empty_feed_message,
    load_demo_companies,
    load_news,
    markdown_block,
    rank_feed,
    resolve_companies_path,
    retain_feed,
    role_choices,
    rss_failure_message,
    source_link_html,
)


def main() -> None:
    """Draw the one-scenario screen. A missing model key leaves that block empty."""
    st.set_page_config(page_title="Сводка для компании", layout="centered")
    st.title("Сводка для компании")
    st.caption(
        "Компания из демо-набора и роль. Другая компания или другая роль "
        "меняет состав и порядок ленты."
    )
    companies = _companies()
    if companies is None:
        return
    source = st.session_state.get("companies_source", "")
    if source:
        st.caption(source)
    if not companies:
        st.info("Демо-набор пуст.")
        return
    company, role_name, role, refresh = _selectors(companies)
    items, failed = _news(refresh)
    _render(company, role_name, role, items, failed)


def _companies() -> list[CompanyProfile] | None:
    """Demo set for this browser session. A missing file is an error, not a crash."""
    if "demo_companies" in st.session_state:
        return st.session_state["demo_companies"]
    path = resolve_companies_path()
    if not path.is_file():
        st.error(
            "Нет файла компаний. Нужен data/sample/companies.csv "
            "или полный data/raw/df_Uid_data_hack.csv."
        )
        return None
    try:
        with st.spinner("Читаю демо-набор..."):
            companies = load_demo_companies(path)
    except (OSError, UnicodeError, csv.Error):
        st.error("Демо-набор не прочитан.")
        return None
    st.session_state["demo_companies"] = companies
    st.session_state["companies_source"] = companies_source_label(path)
    return companies


def _selectors(
    companies: list[CompanyProfile],
) -> tuple[CompanyProfile, str, Role, bool]:
    labels = company_labels(companies)
    by_name = dict(labels)
    roles = role_choices()
    by_role = dict(roles)
    left, right = st.columns(2)
    with left:
        company_name = st.selectbox("Компания", [label for label, _row in labels])
    with right:
        role_name = st.selectbox("Роль", [label for label, _row in roles])
    refresh = st.button("Обновить ленту")
    return by_name[company_name], role_name, by_role[role_name], refresh


def _news(refresh: bool) -> tuple[list[NewsItem], bool]:
    """Load RSS once per session. A failed refresh keeps the previous feed."""
    if refresh or "news_items" not in st.session_state:
        previous = list(st.session_state.get("news_items", []))
        with st.spinner("Загружаю RSS..."):
            loaded = _safe_load()
        items, show_error = retain_feed(previous, loaded)
        st.session_state["news_items"] = items
        st.session_state["news_failed"] = show_error
    return (
        list(st.session_state["news_items"]),
        bool(st.session_state["news_failed"]),
    )


def _safe_load() -> NewsLoad:
    """RSS load that cannot take the already computed feed down with it."""
    try:
        return load_news()
    except Exception:
        return NewsLoad((), True)


def _render(
    company: CompanyProfile,
    role_name: str,
    role: Role,
    items: list[NewsItem],
    failed: bool,
) -> None:
    st.subheader(company.synthetic_u)
    st.caption(f"Роль: {role_name}.")
    if failed and items:
        st.warning(rss_failure_message(kept_previous=True))
    if not items:
        if failed:
            st.error(rss_failure_message(kept_previous=False))
        else:
            st.info(empty_feed_message())
        return
    ranked = rank_feed(company, items, role, as_of=date.today())
    if not ranked:
        st.info(empty_feed_message())
        return
    st.caption(f"В ленте {len(ranked)}.")
    client = _model_client()
    for index, scored in enumerate(ranked, start=1):
        view = card_view(
            company,
            scored,
            role=role,
            client=client,
            shown=ranked,
        )
        _render_card(index, view, client_ready=client is not None)


class _CachedClient:
    """One gateway answer per prompt for the rest of this browser session."""

    def __init__(self, inner: ModelClient, cache: dict[str, str]) -> None:
        self._inner = inner
        self._cache = cache

    def complete(self, prompt: str) -> str:
        """Return the stored completion, or ask the gateway once."""
        stored = self._cache.get(prompt)
        if stored is not None:
            return stored
        stored = self._inner.complete(prompt)
        self._cache[prompt] = stored
        return stored


def _model_client() -> ModelClient | None:
    """Gateway client, or None when the three environment values are absent.

    A present client is wrapped so a rerun does not send the same prompt again.
    A vision model name never produces a client.
    """
    client = client_from_env()
    if client is None:
        return None
    cache: dict[str, str] = st.session_state.setdefault("model_cache", {})
    return _CachedClient(client, cache)


def _render_card(index: int, view: CardView, *, client_ready: bool) -> None:
    with st.container(border=True):
        st.caption(f"{index}. {view.score_line()}")
        for title, body in card_blocks(view):
            if title == "Источник":
                st.markdown("**Источник.**")
                st.html(source_link_html(view.source_name, view.source_url))
                continue
            if title == "Вывод модели":
                st.markdown("**Вывод модели.**")
                if body.strip():
                    st.markdown(markdown_block(body))
                elif not client_ready:
                    st.caption("Пусто: нет ключа модели.")
                continue
            st.markdown(f"**{title}.**")
            st.markdown(markdown_block(body))
        st.markdown(markdown_block(view.csv_fields_line()))


if __name__ == "__main__":
    main()
