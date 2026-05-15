from __future__ import annotations

from datetime import datetime
from pathlib import Path
import importlib.util

import matplotlib.pyplot as plt
import pandas as pd

# uv run python app/insights-x-scraping/generate_executive_report.py

BASE_DIR = Path(
    r"C:\Users\rafaeltegazzini\Documents\Projetos\analysisFactory\app\insights-x-scraping"
)
INSIGHTS_PATH = BASE_DIR / "insights.py"
OUTPUT_MD = BASE_DIR / "documentacao_executiva.md"
ASSETS_DIR = BASE_DIR / "assets"
BRAND_COLOR = "#ffdd00"
QUERY_SINCE = "01/01/2026"
QUERY_UNTIL = "24/03/2026"


def load_insights_module():
    spec = importlib.util.spec_from_file_location("insights_app", INSIGHTS_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def fmt_int(value: float | int) -> str:
    return f"{int(round(value)):,}".replace(",", ".")


def fmt_pct(value: float) -> str:
    return f"{value:.1f}%"


def markdown_table(df: pd.DataFrame) -> str:
    headers = list(df.columns)
    lines = []
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for row in df.itertuples(index=False):
        values = [str(v) for v in row]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def barh_chart(df: pd.DataFrame, category_col: str, value_col: str, title: str, output: Path):
    plot_df = df.sort_values(value_col, ascending=True)
    plt.figure(figsize=(10, 6))
    plt.barh(plot_df[category_col], plot_df[value_col], color=BRAND_COLOR)
    plt.title(title)
    plt.xlabel("Quantidade")
    plt.tight_layout()
    plt.savefig(output, dpi=150)
    plt.close()


def line_chart(df: pd.DataFrame, output: Path):
    plt.figure(figsize=(12, 6))
    ordered = sorted(df["rotulo_canonico"].dropna().unique())
    for rotulo in ordered:
        item = df[df["rotulo_canonico"] == rotulo].sort_values("created_date")
        plt.plot(item["created_date"], item["Mencoes"], linewidth=2, label=rotulo)
    plt.title("Evolucao diaria de mencoes por rotulo")
    plt.xlabel("Data")
    plt.ylabel("Mencoes")
    plt.legend()
    plt.tight_layout()
    plt.savefig(output, dpi=150)
    plt.close()


def quarter_tags_chart(df: pd.DataFrame, output: Path):
    plot_df = df.copy()
    plot_df["Label"] = plot_df["Quarter"] + " | " + plot_df["Tag"]
    plot_df = plot_df.sort_values(["Quarter", "Quantidade"], ascending=[False, True])
    plt.figure(figsize=(11, max(5, len(plot_df) * 0.35)))
    plt.barh(plot_df["Label"], plot_df["Quantidade"], color=BRAND_COLOR)
    plt.title("Top tags por quarter")
    plt.xlabel("Quantidade")
    plt.tight_layout()
    plt.savefig(output, dpi=150)
    plt.close()


def main() -> None:
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    insights = load_insights_module()

    df = insights.load_data(insights.DATA_PATH).copy()
    tags_df = insights.explode_tags(df).copy()

    total_posts = len(df)
    total_views = int(df["view_count"].sum())
    total_interacoes = int(df["interacoes"].sum())
    reclamacao_pct = float(df["rotulo_canonico"].eq("Reclamacao").mean() * 100)
    satisfacao_pct = float(df["rotulo_canonico"].eq("Satisfacao").mean() * 100)
    sugestao_pct = float(df["rotulo_canonico"].eq("Sugestao").mean() * 100)
    negativos_pct = float(df["resumo_sentimento"].eq("Negativo").mean() * 100)
    engagement_por_mil = (total_interacoes / total_views * 1000) if total_views else 0.0

    distribuicao = (
        df["rotulo_canonico"]
        .value_counts()
        .rename_axis("Rotulo")
        .reset_index(name="Quantidade")
        .sort_values("Quantidade", ascending=False)
    )
    distribuicao["Percentual"] = (distribuicao["Quantidade"] / total_posts * 100).map(fmt_pct)

    sentimento = (
        df["resumo_sentimento"]
        .value_counts()
        .rename_axis("Sentimento")
        .reset_index(name="Quantidade")
        .sort_values("Quantidade", ascending=False)
    )
    sentimento["Percentual"] = (sentimento["Quantidade"] / total_posts * 100).map(fmt_pct)

    tag_counts = (
        tags_df["tag_canonica"]
        .value_counts()
        .rename_axis("Tag")
        .reset_index(name="Quantidade")
        .sort_values("Quantidade", ascending=False)
    )
    tag_counts = tag_counts[tag_counts["Tag"] != "Outros"].copy()
    total_tag_ref = int(tag_counts["Quantidade"].sum()) if not tag_counts.empty else 0
    tag_counts["Percentual"] = (
        (tag_counts["Quantidade"] / total_tag_ref * 100).map(fmt_pct) if total_tag_ref else "0.0%"
    )
    top_tags = tag_counts.head(10).copy()

    trend = (
        df.dropna(subset=["created_date"])
        .groupby(["created_date", "rotulo_canonico"], as_index=False)["id_tweet"]
        .count()
        .rename(columns={"id_tweet": "Mencoes"})
    )

    quarter_summary = (
        df.groupby("quarter", as_index=False)
        .agg(
            Mencoes=("id_tweet", "count"),
            Views=("view_count", "sum"),
            Interacoes=("interacoes", "sum"),
            Reclamacoes=("rotulo_canonico", lambda x: (x == "Reclamacao").sum()),
        )
        .sort_values("quarter")
    )
    quarter_summary["Percentual reclamacao"] = (
        quarter_summary["Reclamacoes"] / quarter_summary["Mencoes"] * 100
    )

    quarter_tags = (
        tags_df[tags_df["tag_canonica"] != "Outros"]
        .groupby(["quarter", "tag_canonica"], as_index=False)["id_tweet"]
        .count()
        .rename(
            columns={
                "quarter": "Quarter",
                "tag_canonica": "Tag",
                "id_tweet": "Quantidade",
            }
        )
        .sort_values(["Quarter", "Quantidade"], ascending=[True, False])
    )
    if not quarter_tags.empty:
        quarter_tags["Percentual"] = quarter_tags.groupby("Quarter")["Quantidade"].transform(
            lambda x: x / x.sum() * 100
        )
        quarter_tags_top = quarter_tags.groupby("Quarter", group_keys=False).head(5).copy()
    else:
        quarter_tags_top = quarter_tags.copy()
    quarters_sem_tag = sorted(set(df["quarter"].unique()) - set(tags_df["quarter"].unique()))
    quarters_sem_tag_note = (
        f"\n\nObservacao: a coluna `Tag` nao esta preenchida para {', '.join(quarters_sem_tag)}. "
        "Nesses periodos, a leitura por quarter fica concentrada em volume, interacoes e rotulos."
        if quarters_sem_tag
        else ""
    )

    recorte_txt = f"{QUERY_SINCE} a {QUERY_UNTIL}"

    dist_png = ASSETS_DIR / "distribuicao_percepcao.png"
    sent_png = ASSETS_DIR / "sentimento_consolidado.png"
    trend_png = ASSETS_DIR / "evolucao_diaria.png"
    tag_png = ASSETS_DIR / "top_temas_tag.png"
    quarter_png = ASSETS_DIR / "top_temas_por_quarter.png"

    barh_chart(distribuicao, "Rotulo", "Quantidade", "Distribuicao de percepcao", dist_png)
    barh_chart(sentimento, "Sentimento", "Quantidade", "Sentimento consolidado", sent_png)
    if not trend.empty:
        line_chart(trend, trend_png)
    barh_chart(top_tags, "Tag", "Quantidade", "Top temas por tag", tag_png)
    if not quarter_tags_top.empty:
        quarter_tags_chart(quarter_tags_top, quarter_png)

    top_tag_reclamacao = ""
    top_tag_reclamacao_pct = 0.0
    recl_tags = tags_df[tags_df["rotulo_canonico"] == "Reclamacao"]["tag_canonica"]
    if not recl_tags.empty:
        top_tag_reclamacao = recl_tags.value_counts().index[0]
        top_tag_reclamacao_pct = float(recl_tags.value_counts(normalize=True).iloc[0] * 100)

    summary_points = [
        f"**{fmt_int(total_posts)} mencoes analisadas** no X, com recorte de **{recorte_txt}**.",
        f"**{fmt_int(total_views)} views totais** e **{fmt_int(total_interacoes)} interacoes** (engajamento de **{engagement_por_mil:.1f} por 1.000 views**).",
        f"**Reclamacao domina a conversa ({fmt_pct(reclamacao_pct)})**, enquanto Satisfacao representa **{fmt_pct(satisfacao_pct)}**.",
        f"Sentimento **Negativo** em **{fmt_pct(negativos_pct)}** dos casos.",
        f"Na frente de reclamacoes, a principal alavanca e **{top_tag_reclamacao or 'N/A'}** ({fmt_pct(top_tag_reclamacao_pct)} das reclamacoes com tag).",
    ]

    dist_table = distribuicao.copy()
    dist_table["Quantidade"] = dist_table["Quantidade"].map(fmt_int)
    sent_table = sentimento.copy()
    sent_table["Quantidade"] = sent_table["Quantidade"].map(fmt_int)
    tags_table = top_tags.copy()
    tags_table["Quantidade"] = tags_table["Quantidade"].map(fmt_int)
    quarter_summary_table = quarter_summary.copy()
    quarter_summary_table["Views"] = quarter_summary_table["Views"].map(fmt_int)
    quarter_summary_table["Interacoes"] = quarter_summary_table["Interacoes"].map(fmt_int)
    quarter_summary_table["Percentual reclamacao"] = quarter_summary_table[
        "Percentual reclamacao"
    ].map(fmt_pct)
    quarter_tags_table = quarter_tags_top.copy()
    if not quarter_tags_table.empty:
        quarter_tags_table["Quantidade"] = quarter_tags_table["Quantidade"].map(fmt_int)
        quarter_tags_table["Percentual"] = quarter_tags_table["Percentual"].map(fmt_pct)

    md = f"""# Documentacao Executiva - Percepcao de Usuarios no X (99)

Gerado automaticamente em {datetime.now().strftime("%d/%m/%Y %H:%M")}.

## Base de dados e dicionario de colunas
- Base completa: [Google Sheets](https://docs.google.com/spreadsheets/d/1If2wWa5sSXJTmc5J2O6DfCPb8naOm5oGvhHSZFt8iLY/edit?usp=sharing)
- `id_tweet`: id da mensagem. Ao copiar o id e colar apos a URL do X, voce e redirecionado para a respectiva mencao no site oficial.
- `created_date`: data da publicacao.
- `created_time`: hora da publicacao.
- `full_text`: texto da publicacao onde a 99 foi mencionada.
- `view_count`: quantidade de visualizacoes.
- `retweet_count`: quantidade de reposts.
- `favorite_count`: quantidade de curtidas.
- `reply_count`: quantidade de respostas.
- `quote_count`: quantidade de citacoes.
- `id_user`: id da conta do usuario.
- `followers_count`: contagem de seguidores.
- `following_count`: contagem de pessoas que o usuario segue.
- `verified`: se o usuario assina o plano pago do X.
- `rotulo`: rotulo da publicacao usando Gemini com o prompt: `Crie uma nova coluna e categorize os textos dos tweets na coluna A usando os rotulos: 'Satisfacao', 'Reclamacao' e 'Sugestao'`.
- `resumo`: resumo da publicacao usando Gemini com o prompt: `Resuma em uma palavra o que essa pessoa sente a respeito do servico prestado pelo aplicativo de mobilidade 99, caso o texto nao esteja no contexto esperado retorne 'Outro'`.
- `Tag`: tag da publicacao usando Gemini com o prompt: `classifique o conteudo da mensagem em seguintes categorias: preco, tempo de espera ou disponibilidade, cancelamentos, comportamento do motorista, qualidade do carro, problema de pagamento e outros. Caso identifique mais de uma categoria, separe por virgula`.

## Visao executiva
{chr(10).join([f"- {line}" for line in summary_points])}

## Big numbers
- Mencoes analisadas: **{fmt_int(total_posts)}**
- Views totais: **{fmt_int(total_views)}**
- Total de interacoes: **{fmt_int(total_interacoes)}**
- Percentual de reclamacao: **{fmt_pct(reclamacao_pct)}**
- Percentual de satisfacao: **{fmt_pct(satisfacao_pct)}**
- Percentual de sugestao: **{fmt_pct(sugestao_pct)}**

## Leitura rapida para diretoria
| O que olhar | Resultado |
| --- | --- |
| Pressao reputacional | Reclamacao em **{fmt_pct(reclamacao_pct)}** |
| Qualidade da experiencia | Negativo em **{fmt_pct(negativos_pct)}** dos resumos |
| Driver principal de ruido | **{top_tag_reclamacao or 'N/A'}** com **{fmt_pct(top_tag_reclamacao_pct)}** das reclamacoes com tag |

## Distribuicao de percepcao (rotulo)
{markdown_table(dist_table)}

![Distribuicao de percepcao](assets/distribuicao_percepcao.png)

## Sentimento consolidado (resumo)
{markdown_table(sent_table)}

![Sentimento consolidado](assets/sentimento_consolidado.png)

## Evolucao diaria
Leitura recomendada: acompanhar picos de **Reclamacao** por dia para relacionar com eventos operacionais (disponibilidade, preco e cancelamentos).

![Evolucao diaria](assets/evolucao_diaria.png)

## Top temas por tag que moldam a percepcao
{markdown_table(tags_table)}

![Top temas por tag](assets/top_temas_tag.png)

## Analise por quarter
A leitura por quarter ajuda a comparar como os temas evoluem por periodo e quais assuntos ganham ou perdem relevancia ao longo do tempo.{quarters_sem_tag_note}

{markdown_table(quarter_summary_table)}

### Top tags por quarter
{markdown_table(quarter_tags_table) if not quarter_tags_table.empty else "Sem tags suficientes para analise por quarter."}

![Top temas por quarter](assets/top_temas_por_quarter.png)

## Proximos passos recomendados (30 dias)
1. **Ajustar as classificacoes:** expandir os rotulos de categorizacao e refinar os prompts para aumentar a precisao da segmentacao e reduzir agrupamentos genericos.
2. **Testar API oficial:** estimar o custo mensal e mapear quais campos adicionais podem enriquecer a analise (metadados, autoria, granularidade temporal e sinais de engajamento).
3. **Expandir para outros canais:** incluir **Reclame Aqui** e **LinkedIn** para ampliar cobertura de percepcao externa e comparar se os temas criticos se repetem entre canais.
4. **Criar painel de acompanhamento continuo:** disponibilizar uma aplicacao para monitoramento recorrente do que esta sendo dito, com alertas e leitura por tema critico.

## Parte tecnica (resumo)
### Objetivo
Criar uma estrutura inicial de monitoramento de mencoes no X sobre a empresa para:
- identificar temas recorrentes
- capturar sinais de percepcao de marca
- apoiar analises de experiencia e operacao
- viabilizar base reutilizavel para novos estudos

### O que foi feito
#### Coleta de dados
- Estruturado processo de coleta via web scraping
- Busca historica por periodo e por query
- Abordagem sem custo de API nesta etapa

#### Primeira versao dos filtros
- idioma em portugues (`lang:pt`)
- exclusao de links (`-filter:links`)
- exclusao de replies (`-filter:replies`)
- exclusao de perfil especifico (`-from:voude99`)
- exclusao de termos de ruido (`-R$99 -99%`)
- recorte por periodo (`since:2026-01-01 until:2026-03-24`)

#### Estrategia de busca aplicada nesta versao
```text
99 (app OR corrida) -R$99 -99% lang:pt since:2026-01-01 until:2026-03-24 -filter:links -filter:replies -from:voude99
```

#### Tratamento e consolidacao analitica
- Normalizacao de rotulos, sentimentos e tags
- Quebra de tags multiplas por virgula
- Desenvolvimento de script em Python para remover mensagens onde `food` aparece, focando o recorte em mencoes de ride hailing
- Consolidacao de big numbers, distribuicoes, tendencias e temas prioritarios
- Geracao automatica de dashboard e documentacao executiva
"""

    OUTPUT_MD.write_text(md, encoding="utf-8-sig")
    print(f"Relatorio criado: {OUTPUT_MD}")
    print(f"Graficos criados em: {ASSETS_DIR}")


if __name__ == "__main__":
    main()
