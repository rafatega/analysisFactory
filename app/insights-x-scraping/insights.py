from __future__ import annotations

import unicodedata

import altair as alt
import pandas as pd
import streamlit as st

# streamlit run app/insights-x-scraping/insights.py

DATA_PATH = (
    r"C:\Users\rafaeltegazzini\Documents\Projetos\analysisFactory\app\insights-x-scraping\Scrape99.xlsx"
)
BRAND_COLOR = "#ffdd00"


def normalize_text(value: object) -> str:
    text = str(value or "").strip().lower()
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return " ".join(text.split())


def canonical_rotulo(raw: str) -> str:
    normalized = normalize_text(raw)
    if "reclam" in normalized:
        return "Reclamacao"
    if "satisf" in normalized:
        return "Satisfacao"
    if "sugest" in normalized:
        return "Sugestao"
    return "Outros"


def canonical_tag(raw: str) -> str:
    normalized = normalize_text(raw)
    if not normalized:
        return "Sem tag"
    if "preco" in normalized:
        return "Preco"
    if "comportamento" in normalized and "motorista" in normalized:
        return "Comportamento do Motorista"
    if "cancel" in normalized:
        return "Cancelamentos"
    if "pagamento" in normalized:
        return "Problema de Pagamento"
    if "espera" in normalized or "disponibilidade" in normalized:
        return "Tempo de Espera/Disponibilidade"
    if "qualidade" in normalized and "carro" in normalized:
        return "Qualidade do Carro"
    if "outro" in normalized:
        return "Outros"
    return raw.strip().title()


def resumo_sentiment(raw: str) -> str:
    normalized = normalize_text(raw)
    positive = {
        "satisfacao",
        "felicidade",
        "gratidao",
        "confianca",
        "entusiasmo",
        "otimismo",
        "alivio",
        "preferencia",
        "praticidade",
    }
    negative = {
        "insatisfacao",
        "frustracao",
        "indignacao",
        "raiva",
        "desconfianca",
        "irritacao",
        "medo",
        "desespero",
        "inseguranca",
        "trauma",
        "humilhacao",
        "desprezo",
        "infelicidade",
        "insatisfeito",
        "insatisfeita",
        "descontentamento",
        "odio",
        "arrependimento",
        "vergonha",
    }
    if normalized in positive:
        return "Positivo"
    if normalized in negative:
        return "Negativo"
    return "Neutro"


def brand_bar_chart(data: pd.DataFrame, category_col: str, value_col: str) -> alt.Chart:
    ordered = data.sort_values(value_col, ascending=False).copy()
    return (
        alt.Chart(ordered)
        .mark_bar(color=BRAND_COLOR)
        .encode(
            x=alt.X(f"{value_col}:Q", title=value_col),
            y=alt.Y(f"{category_col}:N", sort="-x", title=category_col),
            tooltip=[category_col, value_col],
        )
        .properties(height=320)
    )


def format_int(value: float | int) -> str:
    return f"{int(round(value)):,}".replace(",", ".")


@st.cache_data(show_spinner=False)
def load_data(path: str) -> pd.DataFrame:
    df = pd.read_excel(path, engine="openpyxl")
    col_map = {}
    for col in df.columns:
        normalized = normalize_text(col).replace(" ", "_")
        col_map[col] = normalized
    df = df.rename(columns=col_map)

    required = ["rotulo", "resumo", "tag", "created_date"]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"Colunas obrigatorias ausentes: {missing}")

    if "view_count" not in df.columns:
        df["view_count"] = 0
    for col in ["favorite_count", "reply_count", "retweet_count", "quote_count"]:
        if col not in df.columns:
            df[col] = 0

    df["rotulo"] = df["rotulo"].fillna("Outros").astype(str).str.strip()
    df["resumo"] = df["resumo"].fillna("Outro").astype(str).str.strip()
    df["tag"] = df["tag"].fillna("").astype(str)
    df["rotulo_canonico"] = df["rotulo"].apply(canonical_rotulo)
    df["resumo_sentimento"] = df["resumo"].apply(resumo_sentiment)

    df["created_date"] = pd.to_datetime(
        df["created_date"].astype(str), format="%Y%m%d", errors="coerce"
    )
    if "created_time" in df.columns:
        created_time = df["created_time"].astype(str).str.strip()
        df["created_datetime"] = pd.to_datetime(
            df["created_date"].dt.strftime("%Y-%m-%d") + " " + created_time,
            errors="coerce",
        )
    else:
        df["created_datetime"] = df["created_date"]
    df["quarter"] = df["created_date"].dt.to_period("Q").astype(str)
    df.loc[df["created_date"].isna(), "quarter"] = "Sem data"
    df["mes"] = df["created_date"].dt.to_period("M").astype(str)
    df.loc[df["created_date"].isna(), "mes"] = "Sem data"
    df["interacoes"] = (
        pd.to_numeric(df["favorite_count"], errors="coerce").fillna(0)
        + pd.to_numeric(df["reply_count"], errors="coerce").fillna(0)
        + pd.to_numeric(df["retweet_count"], errors="coerce").fillna(0)
        + pd.to_numeric(df["quote_count"], errors="coerce").fillna(0)
    )
    df["view_count"] = pd.to_numeric(df["view_count"], errors="coerce").fillna(0)
    return df


def explode_tags(df: pd.DataFrame) -> pd.DataFrame:
    tags = df[
        [
            "id_tweet",
            "quarter",
            "mes",
            "rotulo_canonico",
            "resumo_sentimento",
            "view_count",
            "interacoes",
            "tag",
        ]
    ].copy()
    tags["tag"] = tags["tag"].str.split(",")
    tags = tags.explode("tag")
    tags["tag"] = tags["tag"].fillna("").astype(str).str.strip()
    tags = tags[tags["tag"] != ""]
    tags["tag_canonica"] = tags["tag"].apply(canonical_tag)
    return tags


def main() -> None:
    st.set_page_config(
        page_title="Insight Factory | Percepcao 99 no X",
        page_icon="📊",
        layout="wide",
    )
    st.title("Percepcao de Usuarios da 99 no X")
    st.caption(
        "Base: scraping da query `99 (app OR corrida) -R$99 -99% lang:pt "
        "since:2026-02-29 until:2026-03-24 -filter:links -filter:replies -from:voude99`."
    )

    try:
        df = load_data(DATA_PATH)
    except Exception as exc:
        st.error(f"Falha ao carregar base: {exc}")
        return

    tags_df = explode_tags(df)
    available_quarters = sorted(q for q in df["quarter"].dropna().unique() if q != "Sem data")

    st.sidebar.header("Filtros")
    selected_quarters = st.sidebar.multiselect(
        "Quarter",
        available_quarters,
        default=available_quarters,
        help="Use para comparar periodos ou isolar um quarter especifico.",
    )
    if not selected_quarters:
        st.warning("Selecione pelo menos um quarter para visualizar os insights.")
        return

    df = df[df["quarter"].isin(selected_quarters)]
    tags_df = tags_df[tags_df["quarter"].isin(selected_quarters)]

    if df.empty:
        st.warning("Nenhum registro encontrado para os filtros selecionados.")
        return

    total_posts = len(df)
    total_views = int(df["view_count"].sum())
    total_interacoes = int(df["interacoes"].sum())

    rotulo_pct = (
        df["rotulo_canonico"].value_counts(normalize=True).mul(100).rename("percentual")
    )
    reclamacao_pct = float(rotulo_pct.get("Reclamacao", 0))
    satisfacao_pct = float(rotulo_pct.get("Satisfacao", 0))

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Mencoes analisadas", format_int(total_posts))
    col2.metric("Views totais", format_int(total_views))
    col3.metric("Interacoes totais", format_int(total_interacoes))
    col4.metric("% Reclamacao", f"{reclamacao_pct:.1f}%")

    st.divider()

    st.subheader("Sentimento Consolidado")
    resumo_chart = (
        df["resumo_sentimento"]
        .value_counts()
        .rename_axis("Sentimento")
        .reset_index(name="Mencoes")
        .sort_values("Mencoes", ascending=False)
    )
    resumo_bars = brand_bar_chart(resumo_chart, "Sentimento", "Mencoes")
    resumo_labels = (
        alt.Chart(resumo_chart)
        .mark_text(align="left", baseline="middle", dx=4, color="#222222")
        .encode(
            x=alt.X("Mencoes:Q"),
            y=alt.Y("Sentimento:N", sort="-x"),
            text=alt.Text("Mencoes:Q", format=",.0f"),
        )
    )
    st.altair_chart(
        resumo_bars + resumo_labels,
        use_container_width=True,
    )

    trend = (
        df[
            df["created_date"].notna()
            & df["rotulo_canonico"].eq("Reclamacao")
        ]
        .groupby("created_date", as_index=False)["id_tweet"]
        .count()
        .rename(columns={"id_tweet": "Mencoes"})
        .sort_values("created_date")
    )
    if not trend.empty:
        st.subheader("Evolução diária de menções")
        trend_chart = (
            alt.Chart(trend)
            .mark_line(color=BRAND_COLOR, strokeWidth=2)
            .encode(
                x=alt.X("created_date:T", title="Data"),
                y=alt.Y(
                    "Mencoes:Q",
                    title="Mencoes",
                    scale=alt.Scale(type="log"),
                ),
                tooltip=["created_date:T", "Mencoes:Q"],
            )
            .properties(height=340)
        )
        st.altair_chart(trend_chart, use_container_width=True)

    st.subheader("TOP Tags que moldam os sentimentos")
    if tags_df.empty:
        st.warning("Nenhuma tag encontrada para analise.")
    else:
        tag_sentimentos_df = tags_df[tags_df["tag_canonica"] != "Outros"].copy()

        sentimento_left, sentimento_right = st.columns(2)
        with sentimento_left:
            st.caption("Tags que moldam sentimento positivo")
            tag_counts_positivo = (
                tag_sentimentos_df[
                    tag_sentimentos_df["resumo_sentimento"].eq("Positivo")
                ]["tag_canonica"]
                .value_counts()
                .rename_axis("Tag")
                .reset_index(name="Mencoes")
                .sort_values("Mencoes", ascending=False)
                .head(10)
            )
            if tag_counts_positivo.empty:
                st.info("Sem tags positivas para os filtros selecionados.")
            else:
                st.altair_chart(
                    brand_bar_chart(tag_counts_positivo, "Tag", "Mencoes"),
                    use_container_width=True,
                )

        with sentimento_right:
            st.caption("Tags que moldam sentimento negativo")
            tag_counts_negativo = (
                tag_sentimentos_df[
                    tag_sentimentos_df["resumo_sentimento"].eq("Negativo")
                ]["tag_canonica"]
                .value_counts()
                .rename_axis("Tag")
                .reset_index(name="Mencoes")
                .sort_values("Mencoes", ascending=False)
                .head(10)
            )
            if tag_counts_negativo.empty:
                st.info("Sem tags negativas para os filtros selecionados.")
            else:
                st.altair_chart(
                    brand_bar_chart(tag_counts_negativo, "Tag", "Mencoes"),
                    use_container_width=True,
                )

        cross = (
            tag_sentimentos_df.groupby(
                ["tag_canonica", "resumo_sentimento"], as_index=False
            )["id_tweet"]
            .count()
            .rename(columns={"id_tweet": "Mencoes"})
            .pivot(index="tag_canonica", columns="resumo_sentimento", values="Mencoes")
            .fillna(0)
        )
        sentiment_columns = ["Negativo", "Neutro", "Positivo"]
        for col in sentiment_columns:
            if col not in cross.columns:
                cross[col] = 0
        cross = cross[sentiment_columns].sort_values(
            by=["Negativo", "Positivo", "Neutro"], ascending=False
        )
        st.caption("Matriz Tag x Sentimento")
        st.dataframe(cross.astype(int), use_container_width=True)

        st.subheader("TAGS que moldam o sentimento negativo")
        negative_tag_history = (
            tag_sentimentos_df[tag_sentimentos_df["resumo_sentimento"].eq("Negativo")]
            .groupby(["mes", "tag_canonica"], as_index=False)["id_tweet"]
            .count()
            .rename(columns={"id_tweet": "Mencoes"})
        )
        available_months = sorted(
            month for month in df["mes"].dropna().unique() if month != "Sem data"
        )
        if negative_tag_history.empty or not available_months:
            st.info("Sem tags negativas para exibir na evolução histórica.")
        else:
            top_negative_tags = (
                negative_tag_history.groupby("tag_canonica", as_index=False)["Mencoes"]
                .sum()
                .sort_values("Mencoes", ascending=False)
                .head(5)["tag_canonica"]
                .tolist()
            )
            historical_index = pd.MultiIndex.from_product(
                [available_months, top_negative_tags],
                names=["mes", "tag_canonica"],
            ).to_frame(index=False)
            historical_top_tags = (
                historical_index.merge(
                    negative_tag_history[
                        negative_tag_history["tag_canonica"].isin(top_negative_tags)
                    ],
                    on=["mes", "tag_canonica"],
                    how="left",
                )
                .fillna({"Mencoes": 0})
                .assign(Mencoes=lambda x: x["Mencoes"].astype(int))
            )
            color_range = ["#ffdd00", "#2563eb", "#16a34a", "#dc2626", "#7c3aed"]
            base_negative_history = alt.Chart(historical_top_tags).encode(
                x=alt.X(
                    "mes:N",
                    title="Mês",
                    sort=available_months,
                    axis=alt.Axis(labelAngle=0),
                ),
                y=alt.Y("Mencoes:Q", title="Mencoes"),
                color=alt.Color(
                    "tag_canonica:N",
                    title="Tag",
                    scale=alt.Scale(domain=top_negative_tags, range=color_range),
                    legend=alt.Legend(labelLimit=420),
                ),
                tooltip=["mes:N", "tag_canonica:N", "Mencoes:Q"],
            )
            negative_history_chart = (
                base_negative_history.mark_line(point=True, strokeWidth=3)
                + base_negative_history.mark_text(
                    align="center",
                    baseline="bottom",
                    dy=-8,
                    fontSize=11,
                ).encode(text=alt.Text("Mencoes:Q", format=",.0f"))
            ).properties(height=380)
            st.altair_chart(negative_history_chart, use_container_width=True)

        impacto_tema = (
            tags_df.groupby("tag_canonica", as_index=False)
            .agg(
                mencoes=("id_tweet", "count"),
                media_views=("view_count", "mean"),
                media_interacoes=("interacoes", "mean"),
            )
            .sort_values(by=["mencoes", "media_views"], ascending=False)
        )
        impacto_tema["impacto_composto"] = (
            impacto_tema["mencoes"] * 0.6 + impacto_tema["media_interacoes"] * 0.4
        )
        impacto_tema = impacto_tema.sort_values(
            by="impacto_composto", ascending=False
        ).head(8)
        st.caption("Temas prioritarios por impacto composto (volume + interacao media)")
        st.dataframe(
            impacto_tema.assign(
                media_views=lambda x: x["media_views"].round(1),
                media_interacoes=lambda x: x["media_interacoes"].round(2),
                impacto_composto=lambda x: x["impacto_composto"].round(1),
            ),
            use_container_width=True,
        )

    st.subheader("Análise por mês")
    month_summary = (
        df.groupby("mes", as_index=False)
        .agg(
            mencoes=("id_tweet", "count"),
            views=("view_count", "sum"),
            interacoes=("interacoes", "sum"),
            reclamacoes=("rotulo_canonico", lambda x: (x == "Reclamacao").sum()),
        )
        .sort_values("mes")
    )
    month_summary["percentual_reclamacao"] = (
        month_summary["reclamacoes"] / month_summary["mencoes"] * 100
    )

    month_chart = (
        alt.Chart(month_summary)
        .mark_bar(color=BRAND_COLOR)
        .encode(
            x=alt.X("mes:N", title="Mês", sort=list(month_summary["mes"])),
            y=alt.Y("mencoes:Q", title="Mencoes"),
            tooltip=[
                "mes:N",
                "mencoes:Q",
                "views:Q",
                "interacoes:Q",
                alt.Tooltip("percentual_reclamacao:Q", title="% Reclamacao", format=".1f"),
            ],
        )
        .properties(height=280)
    )
    st.altair_chart(month_chart, use_container_width=True)

    month_sentimento = (
        df.groupby(["mes", "resumo_sentimento"], as_index=False)["id_tweet"]
        .count()
        .rename(columns={"id_tweet": "Mencoes"})
        .pivot(index="mes", columns="resumo_sentimento", values="Mencoes")
        .fillna(0)
        .astype(int)
        .sort_index()
    )
    sentiment_columns = ["Negativo", "Neutro", "Positivo"]
    for col in sentiment_columns:
        if col not in month_sentimento.columns:
            month_sentimento[col] = 0
    month_sentimento = month_sentimento[sentiment_columns]
    st.caption("Distribuicao de sentimentos por mês")
    st.dataframe(month_sentimento, use_container_width=True)

    st.subheader("Detalhar mês")
    selected_month_detail = st.selectbox(
        "Mês",
        list(month_summary["mes"]),
        index=len(month_summary) - 1,
        help="Selecione um periodo para ver os principais indicadores e assuntos.",
    )
    month_df = df[df["mes"] == selected_month_detail]
    month_tags_df = tags_df[tags_df["mes"] == selected_month_detail]

    m_total = len(month_df)
    m_views = int(month_df["view_count"].sum())
    m_interacoes = int(month_df["interacoes"].sum())
    m_reclamacao_pct = (
        month_df["rotulo_canonico"].eq("Reclamacao").mean() * 100 if m_total else 0
    )
    m_sent_negativo_pct = (
        month_df["resumo_sentimento"].eq("Negativo").mean() * 100 if m_total else 0
    )

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Mencoes no mês", format_int(m_total))
    m2.metric("Views no mês", format_int(m_views))
    m3.metric("Interacoes no mês", format_int(m_interacoes))
    m4.metric("% Reclamacao", f"{m_reclamacao_pct:.1f}%")
    m5.metric("% Negativo", f"{m_sent_negativo_pct:.1f}%")

    st.caption(f"TOP Tags que moldam os sentimentos em {selected_month_detail}")
    month_tag_sentimentos_df = month_tags_df[
        month_tags_df["tag_canonica"] != "Outros"
    ].copy()
    if month_tag_sentimentos_df.empty:
        st.info("Sem tags preenchidas para este mês.")
    else:
        month_sentimento_left, month_sentimento_right = st.columns(2)
        with month_sentimento_left:
            st.caption("Tags que moldam sentimento positivo")
            month_tag_counts_positivo = (
                month_tag_sentimentos_df[
                    month_tag_sentimentos_df["resumo_sentimento"].eq("Positivo")
                ]["tag_canonica"]
                .value_counts()
                .rename_axis("Tag")
                .reset_index(name="Mencoes")
                .sort_values("Mencoes", ascending=False)
                .head(10)
            )
            if month_tag_counts_positivo.empty:
                st.info("Sem tags positivas para este mês.")
            else:
                st.altair_chart(
                    brand_bar_chart(month_tag_counts_positivo, "Tag", "Mencoes"),
                    use_container_width=True,
                )

        with month_sentimento_right:
            st.caption("Tags que moldam sentimento negativo")
            month_tag_counts_negativo = (
                month_tag_sentimentos_df[
                    month_tag_sentimentos_df["resumo_sentimento"].eq("Negativo")
                ]["tag_canonica"]
                .value_counts()
                .rename_axis("Tag")
                .reset_index(name="Mencoes")
                .sort_values("Mencoes", ascending=False)
                .head(10)
            )
            if month_tag_counts_negativo.empty:
                st.info("Sem tags negativas para este mês.")
            else:
                st.altair_chart(
                    brand_bar_chart(month_tag_counts_negativo, "Tag", "Mencoes"),
                    use_container_width=True,
                )

        month_cross = (
            month_tag_sentimentos_df.groupby(
                ["tag_canonica", "resumo_sentimento"], as_index=False
            )["id_tweet"]
            .count()
            .rename(columns={"id_tweet": "Mencoes"})
            .pivot(index="tag_canonica", columns="resumo_sentimento", values="Mencoes")
            .fillna(0)
        )
        for col in sentiment_columns:
            if col not in month_cross.columns:
                month_cross[col] = 0
        month_cross = month_cross[sentiment_columns].sort_values(
            by=["Negativo", "Positivo", "Neutro"], ascending=False
        )
        st.caption("Matriz Tag x Sentimento")
        st.dataframe(month_cross.astype(int), use_container_width=True)

    st.subheader("Insights executivos para lideranca")
    top_tag_reclamacao = ""
    share_top_reclamacao = 0.0
    if not tags_df.empty:
        recl_tags = tags_df[tags_df["rotulo_canonico"] == "Reclamacao"]["tag_canonica"]
        if not recl_tags.empty:
            top_tag_reclamacao = recl_tags.value_counts().index[0]
            share_top_reclamacao = float(recl_tags.value_counts(normalize=True).iloc[0] * 100)

    negativos_pct = (
        df["resumo_sentimento"].eq("Negativo").mean() * 100 if len(df) else 0
    )
    oportunidade_positiva = 100 - reclamacao_pct

    st.markdown(
        f"""
1. **Risco de marca imediato:** `Reclamacao` concentra **{reclamacao_pct:.1f}%** das mencoes, com apenas **{satisfacao_pct:.1f}%** de `Satisfacao`.
2. **Principal alavanca de crise:** a tag com maior peso dentro de `Reclamacao` e **{top_tag_reclamacao or "N/A"}** (**{share_top_reclamacao:.1f}%** das reclamacoes tagueadas).
3. **Tom emocional desfavoravel:** **{negativos_pct:.1f}%** dos resumos foram classificados como `Negativo`.
4. **Espaco para reversao:** a soma de `Satisfacao` + `Sugestao` + `Outros` ainda representa **{oportunidade_positiva:.1f}%**, criando janela para acoes de recuperacao.
"""
    )

    st.subheader("Base de apoio")
    support_cols = [
        "created_datetime",
        "rotulo_canonico",
        "resumo",
        "tag",
        "view_count",
        "interacoes",
    ]
    if "full_text" in df.columns:
        support_cols.insert(3, "full_text")
    st.dataframe(
        df[support_cols].sort_values("view_count", ascending=False),
        use_container_width=True,
        hide_index=True,
    )


if __name__ == "__main__":
    main()
