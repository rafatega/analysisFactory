from __future__ import annotations

import argparse
import html
import json
import unicodedata
from datetime import datetime
from pathlib import Path

import altair as alt
import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DATA_PATH = BASE_DIR / "Scrape99.xlsx"
DEFAULT_EXPORT_DIR = BASE_DIR / "exports"
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


def format_int(value: float | int) -> str:
    return f"{int(round(value)):,}".replace(",", ".")


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


def chart_container(chart: alt.Chart | alt.LayerChart, element_id: str) -> str:
    spec = chart.to_dict()
    spec["autosize"] = {"type": "fit", "contains": "padding"}
    return f"""
    <div class="chart" id="{element_id}"></div>
    <script>
      vegaEmbed("#{element_id}", {json.dumps(spec, ensure_ascii=False)}, {{
        actions: false,
        renderer: "svg"
      }});
    </script>
    """


def table_html(df: pd.DataFrame, max_rows: int | None = None) -> str:
    display_df = df.copy()
    if max_rows is not None:
        display_df = display_df.head(max_rows)
    return display_df.to_html(index=True, classes="data-table", border=0, escape=True)


def format_percent(value: float) -> str:
    return f"{value:.1f}%"


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


def build_report(data_path: Path, quarters: list[str] | None, month_detail: str | None) -> str:
    df = load_data(str(data_path))
    tags_df = explode_tags(df)

    available_quarters = sorted(q for q in df["quarter"].dropna().unique() if q != "Sem data")
    selected_quarters = quarters or available_quarters
    df = df[df["quarter"].isin(selected_quarters)]
    tags_df = tags_df[tags_df["quarter"].isin(selected_quarters)]
    if df.empty:
        raise ValueError("Nenhum registro encontrado para os filtros selecionados.")

    total_posts = len(df)
    total_views = int(df["view_count"].sum())
    total_interacoes = int(df["interacoes"].sum())

    rotulo_pct = (
        df["rotulo_canonico"].value_counts(normalize=True).mul(100).rename("percentual")
    )
    reclamacao_pct = float(rotulo_pct.get("Reclamacao", 0))
    satisfacao_pct = float(rotulo_pct.get("Satisfacao", 0))

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

    trend = (
        df[df["created_date"].notna() & df["rotulo_canonico"].eq("Reclamacao")]
        .groupby("created_date", as_index=False)["id_tweet"]
        .count()
        .rename(columns={"id_tweet": "Mencoes"})
        .sort_values("created_date")
    )
    trend_chart = None
    if not trend.empty:
        trend_chart = (
            alt.Chart(trend)
            .mark_line(color=BRAND_COLOR, strokeWidth=2)
            .encode(
                x=alt.X("created_date:T", title="Data"),
                y=alt.Y("Mencoes:Q", title="Mencoes", scale=alt.Scale(type="log")),
                tooltip=["created_date:T", "Mencoes:Q"],
            )
            .properties(height=340)
        )

    tag_sentimentos_df = tags_df[tags_df["tag_canonica"] != "Outros"].copy()
    tag_counts_positivo = (
        tag_sentimentos_df[tag_sentimentos_df["resumo_sentimento"].eq("Positivo")][
            "tag_canonica"
        ]
        .value_counts()
        .rename_axis("Tag")
        .reset_index(name="Mencoes")
        .sort_values("Mencoes", ascending=False)
        .head(10)
    )
    tag_counts_negativo = (
        tag_sentimentos_df[tag_sentimentos_df["resumo_sentimento"].eq("Negativo")][
            "tag_canonica"
        ]
        .value_counts()
        .rename_axis("Tag")
        .reset_index(name="Mencoes")
        .sort_values("Mencoes", ascending=False)
        .head(10)
    )

    cross = (
        tag_sentimentos_df.groupby(["tag_canonica", "resumo_sentimento"], as_index=False)[
            "id_tweet"
        ]
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

    negative_tag_history = (
        tag_sentimentos_df[tag_sentimentos_df["resumo_sentimento"].eq("Negativo")]
        .groupby(["mes", "tag_canonica"], as_index=False)["id_tweet"]
        .count()
        .rename(columns={"id_tweet": "Mencoes"})
    )
    available_months = sorted(month for month in df["mes"].dropna().unique() if month != "Sem data")
    negative_history_chart = None
    if not negative_tag_history.empty and available_months:
        top_negative_tags = (
            negative_tag_history.groupby("tag_canonica", as_index=False)["Mencoes"]
            .sum()
            .sort_values("Mencoes", ascending=False)
            .head(5)["tag_canonica"]
            .tolist()
        )
        historical_index = pd.MultiIndex.from_product(
            [available_months, top_negative_tags], names=["mes", "tag_canonica"]
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
            x=alt.X("mes:N", title="Mes", sort=available_months, axis=alt.Axis(labelAngle=0)),
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
                align="center", baseline="bottom", dy=-8, fontSize=11
            ).encode(text=alt.Text("Mencoes:Q", format=",.0f"))
        ).properties(height=380)

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
    impacto_tema = impacto_tema.sort_values(by="impacto_composto", ascending=False).head(8)
    impacto_tema = impacto_tema.assign(
        media_views=lambda x: x["media_views"].round(1),
        media_interacoes=lambda x: x["media_interacoes"].round(2),
        impacto_composto=lambda x: x["impacto_composto"].round(1),
    )

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
            x=alt.X("mes:N", title="Mes", sort=list(month_summary["mes"])),
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

    month_sentimento = (
        df.groupby(["mes", "resumo_sentimento"], as_index=False)["id_tweet"]
        .count()
        .rename(columns={"id_tweet": "Mencoes"})
        .pivot(index="mes", columns="resumo_sentimento", values="Mencoes")
        .fillna(0)
        .astype(int)
        .sort_index()
    )
    for col in sentiment_columns:
        if col not in month_sentimento.columns:
            month_sentimento[col] = 0
    month_sentimento = month_sentimento[sentiment_columns]

    selected_month_detail = month_detail or str(month_summary["mes"].iloc[-1])
    if selected_month_detail not in set(month_summary["mes"]):
        raise ValueError(f"Mes nao encontrado: {selected_month_detail}")
    month_df = df[df["mes"] == selected_month_detail]
    month_tags_df = tags_df[tags_df["mes"] == selected_month_detail]

    m_total = len(month_df)
    m_views = int(month_df["view_count"].sum())
    m_interacoes = int(month_df["interacoes"].sum())
    m_reclamacao_pct = month_df["rotulo_canonico"].eq("Reclamacao").mean() * 100 if m_total else 0
    m_sent_negativo_pct = (
        month_df["resumo_sentimento"].eq("Negativo").mean() * 100 if m_total else 0
    )

    month_tag_sentimentos_df = month_tags_df[month_tags_df["tag_canonica"] != "Outros"].copy()
    month_tag_counts_positivo = (
        month_tag_sentimentos_df[month_tag_sentimentos_df["resumo_sentimento"].eq("Positivo")][
            "tag_canonica"
        ]
        .value_counts()
        .rename_axis("Tag")
        .reset_index(name="Mencoes")
        .sort_values("Mencoes", ascending=False)
        .head(10)
    )
    month_tag_counts_negativo = (
        month_tag_sentimentos_df[month_tag_sentimentos_df["resumo_sentimento"].eq("Negativo")][
            "tag_canonica"
        ]
        .value_counts()
        .rename_axis("Tag")
        .reset_index(name="Mencoes")
        .sort_values("Mencoes", ascending=False)
        .head(10)
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

    top_tag_reclamacao = ""
    share_top_reclamacao = 0.0
    if not tags_df.empty:
        recl_tags = tags_df[tags_df["rotulo_canonico"] == "Reclamacao"]["tag_canonica"]
        if not recl_tags.empty:
            top_tag_reclamacao = str(recl_tags.value_counts().index[0])
            share_top_reclamacao = float(recl_tags.value_counts(normalize=True).iloc[0] * 100)
    negativos_pct = df["resumo_sentimento"].eq("Negativo").mean() * 100 if len(df) else 0
    oportunidade_positiva = 100 - reclamacao_pct

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
    support_df = df[support_cols].sort_values("view_count", ascending=False).copy()
    if "created_datetime" in support_df.columns:
        support_df["created_datetime"] = support_df["created_datetime"].astype(str)

    generated_at = datetime.now().strftime("%d/%m/%Y %H:%M")
    quarters_label = ", ".join(selected_quarters)

    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Insight Factory | Percepcao 99 no X</title>
  <script src="https://cdn.jsdelivr.net/npm/vega@6"></script>
  <script src="https://cdn.jsdelivr.net/npm/vega-lite@6"></script>
  <script src="https://cdn.jsdelivr.net/npm/vega-embed@7"></script>
  <style>
    :root {{
      --brand: #ffdd00;
      --ink: #18181b;
      --muted: #71717a;
      --line: #e4e4e7;
      --bg: #f7f7f8;
      --panel: #ffffff;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      background: var(--bg);
      font-family: Arial, Helvetica, sans-serif;
      line-height: 1.45;
    }}
    main {{
      width: min(1180px, calc(100% - 36px));
      margin: 0 auto;
      padding: 32px 0 48px;
    }}
    header {{
      border-bottom: 4px solid var(--brand);
      margin-bottom: 24px;
      padding-bottom: 18px;
    }}
    h1, h2, h3 {{ margin: 0; letter-spacing: 0; }}
    h1 {{ font-size: 32px; }}
    h2 {{ font-size: 22px; margin: 30px 0 14px; }}
    h3 {{ font-size: 16px; margin: 0 0 10px; }}
    .caption {{ color: var(--muted); margin: 8px 0 0; }}
    .meta {{ color: var(--muted); font-size: 13px; margin-top: 10px; }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin: 24px 0;
    }}
    .metric, .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
    }}
    .metric .label {{
      color: var(--muted);
      font-size: 13px;
      margin-bottom: 8px;
    }}
    .metric .value {{
      font-size: 26px;
      font-weight: 700;
    }}
    .grid-2 {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;
    }}
    .chart {{
      width: 100%;
      min-height: 120px;
    }}
    .table-wrap {{
      overflow-x: auto;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 8px;
    }}
    table.data-table {{
      border-collapse: collapse;
      min-width: 720px;
      width: 100%;
      font-size: 13px;
    }}
    .data-table th, .data-table td {{
      border-bottom: 1px solid var(--line);
      padding: 8px 10px;
      text-align: left;
      vertical-align: top;
    }}
    .data-table th {{
      background: #fafafa;
      font-weight: 700;
      position: sticky;
      top: 0;
    }}
    .insights {{
      background: #1f2937;
      color: #ffffff;
      border-radius: 8px;
      padding: 18px 22px;
    }}
    .insights strong {{ color: var(--brand); }}
    .insights li {{ margin: 8px 0; }}
    @media (max-width: 860px) {{
      .metrics, .grid-2 {{ grid-template-columns: 1fr; }}
      h1 {{ font-size: 26px; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>Percepcao de Usuarios da 99 no X</h1>
      <p class="caption">Base: scraping da query <code>99 (app OR corrida) -R$99 -99% lang:pt since:2026-02-29 until:2026-03-24 -filter:links -filter:replies -from:voude99</code>.</p>
      <p class="meta">Snapshot gerado em {html.escape(generated_at)} | Quarters: {html.escape(quarters_label)} | Mes detalhado: {html.escape(selected_month_detail)}</p>
    </header>

    <section class="metrics">
      <div class="metric"><div class="label">Mencoes analisadas</div><div class="value">{format_int(total_posts)}</div></div>
      <div class="metric"><div class="label">Views totais</div><div class="value">{format_int(total_views)}</div></div>
      <div class="metric"><div class="label">Interacoes totais</div><div class="value">{format_int(total_interacoes)}</div></div>
      <div class="metric"><div class="label">% Reclamacao</div><div class="value">{format_percent(reclamacao_pct)}</div></div>
    </section>

    <h2>Sentimento Consolidado</h2>
    <section class="panel">{chart_container(resumo_bars + resumo_labels, "chart-resumo")}</section>

    {f'<h2>Evolucao diaria de mencoes</h2><section class="panel">{chart_container(trend_chart, "chart-trend")}</section>' if trend_chart is not None else ''}

    <h2>TOP Tags que moldam os sentimentos</h2>
    <section class="grid-2">
      <div class="panel">
        <h3>Tags que moldam sentimento positivo</h3>
        {chart_container(brand_bar_chart(tag_counts_positivo, "Tag", "Mencoes"), "chart-tag-pos") if not tag_counts_positivo.empty else '<p class="caption">Sem tags positivas para os filtros selecionados.</p>'}
      </div>
      <div class="panel">
        <h3>Tags que moldam sentimento negativo</h3>
        {chart_container(brand_bar_chart(tag_counts_negativo, "Tag", "Mencoes"), "chart-tag-neg") if not tag_counts_negativo.empty else '<p class="caption">Sem tags negativas para os filtros selecionados.</p>'}
      </div>
    </section>

    <h2>Matriz Tag x Sentimento</h2>
    <div class="table-wrap">{table_html(cross.astype(int))}</div>

    {f'<h2>TAGS que moldam o sentimento negativo</h2><section class="panel">{chart_container(negative_history_chart, "chart-neg-history")}</section>' if negative_history_chart is not None else ''}

    <h2>Temas prioritarios por impacto composto</h2>
    <p class="caption">Volume + interacao media</p>
    <div class="table-wrap">{table_html(impacto_tema.set_index("tag_canonica"))}</div>

    <h2>Analise por mes</h2>
    <section class="panel">{chart_container(month_chart, "chart-month")}</section>

    <h2>Distribuicao de sentimentos por mes</h2>
    <div class="table-wrap">{table_html(month_sentimento)}</div>

    <h2>Detalhar mes: {html.escape(selected_month_detail)}</h2>
    <section class="metrics">
      <div class="metric"><div class="label">Mencoes no mes</div><div class="value">{format_int(m_total)}</div></div>
      <div class="metric"><div class="label">Views no mes</div><div class="value">{format_int(m_views)}</div></div>
      <div class="metric"><div class="label">Interacoes no mes</div><div class="value">{format_int(m_interacoes)}</div></div>
      <div class="metric"><div class="label">% Reclamacao</div><div class="value">{format_percent(m_reclamacao_pct)}</div></div>
      <div class="metric"><div class="label">% Negativo</div><div class="value">{format_percent(m_sent_negativo_pct)}</div></div>
    </section>

    <section class="grid-2">
      <div class="panel">
        <h3>Tags que moldam sentimento positivo</h3>
        {chart_container(brand_bar_chart(month_tag_counts_positivo, "Tag", "Mencoes"), "chart-month-tag-pos") if not month_tag_counts_positivo.empty else '<p class="caption">Sem tags positivas para este mes.</p>'}
      </div>
      <div class="panel">
        <h3>Tags que moldam sentimento negativo</h3>
        {chart_container(brand_bar_chart(month_tag_counts_negativo, "Tag", "Mencoes"), "chart-month-tag-neg") if not month_tag_counts_negativo.empty else '<p class="caption">Sem tags negativas para este mes.</p>'}
      </div>
    </section>

    <h2>Matriz Tag x Sentimento do mes</h2>
    <div class="table-wrap">{table_html(month_cross.astype(int))}</div>

    <h2>Insights executivos para lideranca</h2>
    <ol class="insights">
      <li><strong>Risco de marca imediato:</strong> Reclamacao concentra <strong>{format_percent(reclamacao_pct)}</strong> das mencoes, com apenas <strong>{format_percent(satisfacao_pct)}</strong> de Satisfacao.</li>
      <li><strong>Principal alavanca de crise:</strong> a tag com maior peso dentro de Reclamacao e <strong>{html.escape(top_tag_reclamacao or "N/A")}</strong> (<strong>{format_percent(share_top_reclamacao)}</strong> das reclamacoes tagueadas).</li>
      <li><strong>Tom emocional desfavoravel:</strong> <strong>{format_percent(negativos_pct)}</strong> dos resumos foram classificados como Negativo.</li>
      <li><strong>Espaco para reversao:</strong> a soma de Satisfacao + Sugestao + Outros ainda representa <strong>{format_percent(oportunidade_positiva)}</strong>, criando janela para acoes de recuperacao.</li>
    </ol>

    <h2>Base de apoio</h2>
    <p class="caption">Ordenada por views. Exibindo ate 200 linhas para manter o HTML leve.</p>
    <div class="table-wrap">{table_html(support_df, max_rows=200)}</div>
  </main>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Exporta um snapshot HTML interativo do dashboard de insights."
    )
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA_PATH, help="Caminho do XLSX.")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Arquivo HTML de destino. Se omitido, cria em app/insights-x-scraping/exports.",
    )
    parser.add_argument(
        "--quarter",
        action="append",
        dest="quarters",
        help="Quarter para filtrar. Pode repetir: --quarter 2026Q1 --quarter 2026Q2.",
    )
    parser.add_argument("--month", default=None, help="Mes detalhado, por exemplo 2026-03.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output = args.output
    if output is None:
        DEFAULT_EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M")
        output = DEFAULT_EXPORT_DIR / f"insights_snapshot_{stamp}.html"
    else:
        output.parent.mkdir(parents=True, exist_ok=True)

    report = build_report(args.data, args.quarters, args.month)
    output.write_text(report, encoding="utf-8")
    print(f"HTML gerado: {output}")


if __name__ == "__main__":
    main()
