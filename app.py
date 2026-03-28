import streamlit as st
import pandas as pd
import io
from datetime import datetime, date
import pytz

# ── Configuração da página ──────────────────────────────────────────────────
st.set_page_config(
    page_title="Logística SRJ9 – Envios Extra",
    page_icon="🚚",
    layout="wide",
)

BRT = pytz.timezone("America/Sao_Paulo")

# ── CSS customizado ─────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main-title {
        font-size: 2rem; font-weight: 700; color: #1a1a2e;
        border-bottom: 3px solid #e94560; padding-bottom: 8px; margin-bottom: 4px;
    }
    .subtitle { color: #555; font-size: 0.95rem; margin-bottom: 24px; }
    .metric-card {
        background: #f8f9fa; border-radius: 10px;
        padding: 16px 20px; border-left: 4px solid #e94560;
        margin-bottom: 8px;
    }
    .metric-label { font-size: 0.78rem; color: #888; text-transform: uppercase; letter-spacing: 1px; }
    .metric-value { font-size: 1.6rem; font-weight: 700; color: #1a1a2e; }
    .status-ok    { background: #d4edda; color: #155724; border-radius: 5px; padding: 2px 10px; font-weight: 600; }
    .status-warn  { background: #fff3cd; color: #856404; border-radius: 5px; padding: 2px 10px; font-weight: 600; }
    .status-error { background: #f8d7da; color: #721c24; border-radius: 5px; padding: 2px 10px; font-weight: 600; }
    .log-box {
        background: #1e1e2e; color: #cdd6f4; font-family: monospace;
        font-size: 0.82rem; border-radius: 8px; padding: 14px;
        max-height: 220px; overflow-y: auto;
    }
    .tip-box {
        background: #e8f4fd; border-left: 4px solid #2196F3;
        border-radius: 8px; padding: 12px 16px; margin-bottom: 16px;
    }
</style>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════
# FUNÇÕES AUXILIARES
# ═══════════════════════════════════════════════════════════════════════════

def log(msg: str, level: str = "INFO"):
    now = datetime.now(BRT).strftime("%H:%M:%S")
    icon = {"INFO": "ℹ️", "OK": "✅", "WARN": "⚠️", "ERR": "❌"}.get(level, "•")
    st.session_state.logs.append(f"[{now}] {icon} {msg}")

def sugestao_horario() -> str:
    """Retorna sugestão de quando buscar os dados no Looker."""
    now = datetime.now(BRT)
    hora = now.hour
    if hora < 6:
        return "⏰ Looker ainda não rodou hoje. Sugestão: acesse após as 06h00."
    elif hora < 9:
        return "🟡 Dados do Looker recentes (rodou cedo). Verifique se já há alocação completa."
    elif hora < 12:
        return "🟢 Bom horário! Dados do Looker devem estar completos para o turno da manhã."
    elif hora < 17:
        return "🟢 Dados completos. Ideal para conferência do turno da tarde."
    else:
        return "🔵 Dados do turno completo disponíveis. Boa hora para fechamento do dia."

def carregar_mapeamentos(arquivos) -> pd.DataFrame:
    """Lê múltiplos CSVs de mapeamento e retorna DataFrame consolidado."""
    frames = []
    for arq in arquivos:
        try:
            df = pd.read_csv(arq)
            df.columns = df.columns.str.strip()
            # Normaliza nomes de colunas flexivelmente
            col_map = {}
            for c in df.columns:
                cl = c.lower()
                if "otimizada" in cl:
                    col_map[c] = "Rota otimizada"
                elif "original" in cl:
                    col_map[c] = "Rota original"
                elif "cluster" in cl:
                    col_map[c] = "Cluster"
                elif "transport" in cl:
                    col_map[c] = "Transportadora"
                elif "tipo" in cl or "veículo" in cl or "veiculo" in cl:
                    col_map[c] = "Tipo de veículo"
                elif "spr" in cl:
                    col_map[c] = "SPR"
            df = df.rename(columns=col_map)
            obrig = {"Rota otimizada", "Rota original", "Transportadora"}
            if not obrig.issubset(set(df.columns)):
                log(f"Arquivo '{arq.name}' ignorado — faltam colunas obrigatórias.", "WARN")
                continue
            df["_arquivo"] = arq.name
            frames.append(df)
            log(f"Mapeamento carregado: {arq.name} ({len(df)} rotas)", "OK")
        except Exception as e:
            log(f"Erro ao ler '{arq.name}': {e}", "ERR")

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def carregar_looker(arquivo, svc_filtro: str, data_filtro: date) -> pd.DataFrame:
    """Lê o CSV do Looker e aplica filtros de SVC e data."""
    df = pd.read_csv(arquivo)
    df.columns = df.columns.str.strip()
    log(f"Looker carregado: {len(df)} linhas | Colunas: {list(df.columns)}", "INFO")

    # Detecta coluna de data
    col_data = None
    for c in df.columns:
        if "data" in c.lower() or "date" in c.lower() or "dia" in c.lower():
            col_data = c
            break

    # Detecta coluna de SVC/cluster
    col_svc = None
    for c in df.columns:
        if "svc" in c.lower() or "cluster" in c.lower() or "centro" in c.lower():
            col_svc = c
            break

    # Filtro de SVC
    if col_svc and svc_filtro.strip():
        antes = len(df)
        df = df[df[col_svc].astype(str).str.upper().str.contains(svc_filtro.upper())]
        log(f"Filtro SVC '{svc_filtro}': {antes} → {len(df)} linhas", "INFO")

    # Filtro de data
    if col_data:
        df[col_data] = pd.to_datetime(df[col_data], dayfirst=True, errors="coerce")
        antes = len(df)
        df = df[df[col_data].dt.date == data_filtro]
        log(f"Filtro data '{data_filtro}': {antes} → {len(df)} linhas", "INFO")
    else:
        log("Coluna de data não detectada — sem filtro de data aplicado.", "WARN")

    return df


def detectar_coluna(df: pd.DataFrame, palavras: list[str]) -> str | None:
    """Detecta o nome de uma coluna a partir de palavras-chave."""
    for c in df.columns:
        cl = c.lower()
        if any(p in cl for p in palavras):
            return c
    return None


def processar(df_looker: pd.DataFrame, df_map: pd.DataFrame) -> pd.DataFrame:
    """
    Cruza o Looker com os mapeamentos e retorna o relatório final
    apenas com linhas da Envios Extra.
    """
    # ── Detecta colunas do Looker ──
    col_transportadora = detectar_coluna(df_looker, ["transport", "empresa", "carrier"])
    col_rota           = detectar_coluna(df_looker, ["rota", "route", "cod_rota"])
    col_motorista      = detectar_coluna(df_looker, ["motorista", "driver", "nome"])
    col_placa          = detectar_coluna(df_looker, ["placa", "veículo", "veiculo", "plate"])

    if not col_transportadora:
        log("Coluna de transportadora não encontrada no Looker!", "ERR")
        return pd.DataFrame()

    if not col_rota:
        log("Coluna de rota não encontrada no Looker!", "ERR")
        return pd.DataFrame()

    # ── Filtra Envios Extra ──
    mask = df_looker[col_transportadora].astype(str).str.lower().str.contains("envios extra", na=False)
    df_extra = df_looker[mask].copy()
    log(f"Envios Extra encontrados no Looker: {len(df_extra)} registros", "OK")

    if df_extra.empty:
        log("Nenhum registro da Envios Extra encontrado no Looker.", "WARN")
        return pd.DataFrame()

    # ── Normaliza rota para merge ──
    df_extra["_rota_norm"]  = df_extra[col_rota].astype(str).str.strip().str.upper()
    df_map["_rota_norm"]    = df_map["Rota original"].astype(str).str.strip().str.upper()

    # ── Merge ──
    df_merged = df_extra.merge(
        df_map[["_rota_norm", "Rota otimizada", "Cluster", "Transportadora", "Tipo de veículo"]],
        on="_rota_norm",
        how="left",
        suffixes=("_looker", "_map"),
    )

    # ── Status: confere se a transportadora bate ──
    def calcular_status(row):
        transp_map = str(row.get("Transportadora_map", "")).strip().lower()
        if pd.isna(row.get("Rota otimizada")):
            return "❓ Rota não mapeada"
        if "envios extra" in transp_map:
            return "✅ Correto"
        return "⚠️ Divergência de transportadora"

    df_merged["Status"] = df_merged.apply(calcular_status, axis=1)

    # ── Monta relatório final ──
    relatorio = pd.DataFrame()
    relatorio["Cluster / SVC"]       = df_merged.get("Cluster", "—")
    relatorio["Motorista"]           = df_merged[col_motorista] if col_motorista else "—"
    relatorio["Placa"]               = df_merged[col_placa] if col_placa else "—"
    relatorio["Rota Original (Looker)"]   = df_merged[col_rota]
    relatorio["Rota Otimizada (Planej.)"] = df_merged["Rota otimizada"].fillna("⚠️ Não encontrada")
    relatorio["Tipo de Veículo"]     = df_merged.get("Tipo de veículo", "—")
    relatorio["Status"]              = df_merged["Status"]

    log(f"Relatório gerado: {len(relatorio)} linhas", "OK")
    return relatorio


def to_excel(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Envios Extra")
        ws = writer.sheets["Envios Extra"]
        # Ajusta largura das colunas
        for col in ws.columns:
            max_len = max(len(str(cell.value or "")) for cell in col) + 4
            ws.column_dimensions[col[0].column_letter].width = min(max_len, 40)
    return buf.getvalue()


# ═══════════════════════════════════════════════════════════════════════════
# ESTADO DA SESSÃO
# ═══════════════════════════════════════════════════════════════════════════
if "logs" not in st.session_state:
    st.session_state.logs = []
if "df_mapa" not in st.session_state:
    st.session_state.df_mapa = pd.DataFrame()
if "df_relatorio" not in st.session_state:
    st.session_state.df_relatorio = pd.DataFrame()

# ═══════════════════════════════════════════════════════════════════════════
# INTERFACE
# ═══════════════════════════════════════════════════════════════════════════
st.markdown('<div class="main-title">🚚 Logística SRJ9 — Envios Extra</div>', unsafe_allow_html=True)
st.markdown(
    f'<div class="subtitle">Cruzamento de rotas Looker × Planejamento | '
    f'Processado em: <b>{datetime.now(BRT).strftime("%d/%m/%Y %H:%M:%S")}</b></div>',
    unsafe_allow_html=True,
)

# Sugestão de horário
st.markdown(f'<div class="tip-box">{sugestao_horario()}</div>', unsafe_allow_html=True)

# ── SIDEBAR ──────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Configuração")

    st.subheader("1️⃣ CSVs de Mapeamento de Rotas")
    st.caption("Carregue um ou mais arquivos (SD, outros clusters, etc.)")
    arqs_mapa = st.file_uploader(
        "Arquivos de mapeamento",
        type=["csv"],
        accept_multiple_files=True,
        key="mapa",
    )
    if arqs_mapa:
        st.session_state.df_mapa = carregar_mapeamentos(arqs_mapa)
        if not st.session_state.df_mapa.empty:
            st.success(f"{len(st.session_state.df_mapa)} rotas carregadas")
            transportadoras = st.session_state.df_mapa["Transportadora"].value_counts()
            st.caption("Transportadoras no mapeamento:")
            for t, n in transportadoras.items():
                st.caption(f"  • {t}: {n} rota(s)")

    st.divider()

    st.subheader("2️⃣ CSV do Looker")
    st.caption("Exporte da aba 'placas de hoje' no Looker Studio")
    arq_looker = st.file_uploader("Arquivo do Looker", type=["csv"], key="looker")

    st.divider()

    st.subheader("3️⃣ Filtros")
    svc_input  = st.text_input("SVC / Cluster", value="SRJ9", placeholder="ex: SRJ9")
    data_input = st.date_input("Data de operação", value=date.today())

    st.divider()
    processar_btn = st.button("▶️ Processar", use_container_width=True, type="primary")

# ── CONTEÚDO PRINCIPAL ───────────────────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)

# Métricas (atualizam após processar)
df_rel = st.session_state.df_relatorio

total       = len(df_rel)
corretos    = len(df_rel[df_rel["Status"] == "✅ Correto"])        if total else 0
divergentes = len(df_rel[df_rel["Status"].str.contains("Diverg")]) if total else 0
nao_mapeadas= total - corretos - divergentes                        if total else 0

with col1:
    st.markdown(f'<div class="metric-card"><div class="metric-label">Total Envios Extra</div>'
                f'<div class="metric-value">{total}</div></div>', unsafe_allow_html=True)
with col2:
    st.markdown(f'<div class="metric-card"><div class="metric-label">✅ Corretos</div>'
                f'<div class="metric-value" style="color:#155724">{corretos}</div></div>', unsafe_allow_html=True)
with col3:
    st.markdown(f'<div class="metric-card"><div class="metric-label">⚠️ Divergências</div>'
                f'<div class="metric-value" style="color:#856404">{divergentes}</div></div>', unsafe_allow_html=True)
with col4:
    st.markdown(f'<div class="metric-card"><div class="metric-label">❓ Não mapeadas</div>'
                f'<div class="metric-value" style="color:#721c24">{nao_mapeadas}</div></div>', unsafe_allow_html=True)

st.divider()

# ── PROCESSAMENTO ────────────────────────────────────────────────────────
if processar_btn:
    st.session_state.logs = []

    if st.session_state.df_mapa.empty:
        st.error("⚠️ Carregue ao menos um arquivo de mapeamento de rotas na barra lateral.")
    elif arq_looker is None:
        st.error("⚠️ Carregue o CSV do Looker na barra lateral.")
    else:
        with st.spinner("Processando..."):
            df_looker = carregar_looker(arq_looker, svc_input, data_input)
            if df_looker.empty:
                st.warning("Nenhum dado encontrado com os filtros aplicados.")
            else:
                st.session_state.df_relatorio = processar(df_looker, st.session_state.df_mapa)
        st.rerun()

# ── TABELA DE RESULTADOS ─────────────────────────────────────────────────
if not st.session_state.df_relatorio.empty:
    df_show = st.session_state.df_relatorio

    tabs = st.tabs(["📋 Todos", "✅ Corretos", "⚠️ Divergências / Não mapeadas"])

    with tabs[0]:
        st.dataframe(df_show, use_container_width=True, hide_index=True)

    with tabs[1]:
        df_ok = df_show[df_show["Status"] == "✅ Correto"]
        st.dataframe(df_ok, use_container_width=True, hide_index=True)

    with tabs[2]:
        df_prob = df_show[~(df_show["Status"] == "✅ Correto")]
        st.dataframe(df_prob, use_container_width=True, hide_index=True)

    # Download
    st.divider()
    col_dl1, col_dl2 = st.columns(2)
    with col_dl1:
        excel_bytes = to_excel(df_show)
        st.download_button(
            "📥 Baixar Excel completo",
            data=excel_bytes,
            file_name=f"envios_extra_{date.today().strftime('%d%m%Y')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    with col_dl2:
        csv_bytes = df_show.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "📥 Baixar CSV",
            data=csv_bytes,
            file_name=f"envios_extra_{date.today().strftime('%d%m%Y')}.csv",
            mime="text/csv",
            use_container_width=True,
        )

elif not st.session_state.df_mapa.empty:
    st.info("📂 Mapeamento carregado! Agora carregue o CSV do Looker e clique em **Processar**.")
else:
    st.markdown("""
    ### 👋 Como usar
    1. **Barra lateral → CSVs de Mapeamento**: carregue o arquivo de rotas (como `Rotas_SD_28mar.csv`)
    2. **Barra lateral → CSV do Looker**: exporte a tabela "placas de hoje" do Looker Studio
    3. Defina o **SVC** e a **data** desejados
    4. Clique em **▶️ Processar**
    """)

# ── LOG ──────────────────────────────────────────────────────────────────
if st.session_state.logs:
    st.divider()
    with st.expander("🖥️ Log de execução", expanded=False):
        log_html = "<br>".join(st.session_state.logs)
        st.markdown(f'<div class="log-box">{log_html}</div>', unsafe_allow_html=True)

# ── RODAPÉ ───────────────────────────────────────────────────────────────
st.divider()
st.caption(f"🕐 Última atualização: {datetime.now(BRT).strftime('%d/%m/%Y %H:%M:%S')} (Horário de Brasília)")
