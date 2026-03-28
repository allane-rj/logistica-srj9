import streamlit as st
import pandas as pd
import io
from datetime import datetime, date
import pytz

st.set_page_config(page_title="Driver Assignment – Envios Extra", page_icon="🚚", layout="wide")
BRT = pytz.timezone("America/Sao_Paulo")

st.markdown("""
<style>
    [data-testid="stAppViewContainer"] { background: #f4f6fb; }
    .titulo { font-size:2rem; font-weight:800; color:#1a1a2e; letter-spacing:-1px; }
    .subtitulo { color:#666; font-size:.9rem; margin-bottom:1.5rem; }
    .card { background:#fff; border-radius:14px; padding:18px 22px; box-shadow:0 2px 12px rgba(0,0,0,.07); margin-bottom:10px; }
    .card-label { font-size:.72rem; color:#999; text-transform:uppercase; letter-spacing:1px; }
    .card-val { font-size:1.8rem; font-weight:800; color:#1a1a2e; }
    .tip { background:#e8f4fd; border-left:4px solid #2196F3; border-radius:8px; padding:10px 16px; margin-bottom:1rem; font-size:.88rem; }
</style>
""", unsafe_allow_html=True)

def agora():
    return datetime.now(BRT)

def sugestao_horario():
    h = agora().hour
    if h < 6:   return "⏰ Looker ainda não rodou hoje — aguarde após 06h00."
    elif h < 9:  return "🟡 Looker rodou cedo. Verifique se todas as rotas já foram atribuídas."
    elif h < 12: return "🟢 Bom horário! Atribuições do turno da manhã devem estar completas."
    elif h < 17: return "🟢 Dados completos para conferência do turno da tarde."
    else:        return "🔵 Turno completo — ideal para fechamento do dia."

def carregar_mapeamento(arquivos):
    frames = []
    for arq in arquivos:
        try:
            df = pd.read_csv(arq)
            df.columns = df.columns.str.strip()
            rename = {}
            for c in df.columns:
                cl = c.lower()
                if "otimizada" in cl:   rename[c] = "Rota otimizada"
                elif "original" in cl:  rename[c] = "Rota original"
                elif "cluster" in cl:   rename[c] = "Cluster"
                elif "transport" in cl: rename[c] = "Transportadora"
                elif "tipo" in cl or "ve" in cl: rename[c] = "Tipo de veículo"
                elif "spr" in cl:       rename[c] = "SPR"
            df = df.rename(columns=rename)
            if not {"Rota otimizada","Rota original","Transportadora"}.issubset(set(df.columns)):
                st.sidebar.warning(f"'{arq.name}' ignorado — colunas ausentes.")
                continue
            df["_fonte"] = arq.name
            frames.append(df)
        except Exception as e:
            st.sidebar.error(f"Erro em '{arq.name}': {e}")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

def processar(df_looker, df_map):
    # Planejado: rotas Envios Extra no mapeamento
    df_plan = df_map[
        df_map["Transportadora"].str.lower().str.contains("envios extra", na=False)
    ].copy()

    # Join: ROTA do Looker (já é otimizada) x Rota otimizada do mapeamento
    df_map2 = df_map.copy()
    df_map2["_key"] = df_map2["Rota otimizada"].str.strip().str.upper()
    df_looker = df_looker.copy()
    df_looker["_key"] = df_looker["ROTA"].astype(str).str.strip().str.upper()

    merged = df_looker.merge(df_map2, on="_key", how="left")
    df_extra = merged[
        merged["Transportadora"].str.lower().str.contains("envios extra", na=False)
    ].copy()

    def status(row):
        if pd.isna(row.get("Rota otimizada")):
            return "❓ Rota não mapeada"
        vd = str(row.get("VEHICLE_DRIVER","")).strip()
        vr = str(row.get("VEHICLE_ROUTE","")).strip()
        if vd and vr and vd != vr:
            return "⚠️ Veículo diverge do planejado"
        return "✅ Correto"

    df_extra["Status"] = df_extra.apply(status, axis=1)

    rel = pd.DataFrame({
        "SVC":               df_extra.get("SVC", pd.Series(dtype=str)),
        "Cluster":           df_extra.get("Cluster", pd.Series(dtype=str)),
        "Rota (Looker)":     df_extra["ROTA"],
        "Rota Original":     df_extra.get("Rota original", pd.Series(dtype=str)),
        "Driver ID":         df_extra.get("DRIVER_ID", pd.Series(dtype=str)),
        "Motorista":         df_extra.get("NOME", pd.Series(dtype=str)),
        "Placa":             df_extra.get("PLACA", pd.Series(dtype=str)),
        "Nível (LYTY)":      df_extra.get("LYTY", pd.Series(dtype=str)),
        "Career":            df_extra.get("CAREER", pd.Series(dtype=str)),
        "ETA Motorista":     df_extra.get("ETA_DRIVER", pd.Series(dtype=str)),
        "OPS Clock":         df_extra.get("OPS_CLOCK", pd.Series(dtype=str)),
        "Veículo Motorista": df_extra.get("VEHICLE_DRIVER", pd.Series(dtype=str)),
        "Veículo Rota":      df_extra.get("VEHICLE_ROUTE", pd.Series(dtype=str)),
        "Status":            df_extra["Status"],
    })
    return rel, df_plan

def to_excel(df):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="Envios Extra")
        ws = w.sheets["Envios Extra"]
        for col in ws.columns:
            ml = max(len(str(c.value or "")) for c in col) + 4
            ws.column_dimensions[col[0].column_letter].width = min(ml, 42)
    return buf.getvalue()

# Session state
for k, v in [("df_map", pd.DataFrame()), ("df_rel", pd.DataFrame()), ("df_plan", pd.DataFrame())]:
    if k not in st.session_state:
        st.session_state[k] = v

# ── SIDEBAR ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Configuração")
    st.markdown("**1 · CSV de mapeamento de rotas**")
    st.caption("Carregue quantos quiser (SD, outros clusters…)")
    arqs_map = st.file_uploader("Mapeamento", type="csv", accept_multiple_files=True, label_visibility="collapsed")
    if arqs_map:
        df_map = carregar_mapeamento(arqs_map)
        if not df_map.empty:
            st.session_state.df_map = df_map
            n_extra = df_map["Transportadora"].str.lower().str.contains("envios extra", na=False).sum()
            st.success(f"{len(df_map)} rotas carregadas | {n_extra} Envios Extra")

    st.divider()
    st.markdown("**2 · CSV do Looker**")
    st.caption("'Placas Hoje' → três pontinhos → Download CSV")
    arq_looker = st.file_uploader("Looker CSV", type="csv", label_visibility="collapsed")

    st.divider()
    btn = st.button("▶️ Processar", use_container_width=True, type="primary")

# ── CABEÇALHO ─────────────────────────────────────────────────────────────────
st.markdown('<div class="titulo">🚚 Driver Assignment — Envios Extra</div>', unsafe_allow_html=True)
st.markdown(f'<div class="subtitulo">SRJ9 · {agora().strftime("%d/%m/%Y %H:%M:%S")} (Brasília)</div>', unsafe_allow_html=True)
st.markdown(f'<div class="tip">{sugestao_horario()}</div>', unsafe_allow_html=True)

# ── SEÇÃO 1: PREVISÃO (só com mapeamento, sem Looker) ─────────────────────────
if not st.session_state.df_map.empty:
    df_prev = st.session_state.df_map[
        st.session_state.df_map["Transportadora"].str.lower().str.contains("envios extra", na=False)
    ]

    st.markdown("---")
    st.markdown("### 📋 Rotas Envios Extra — O que o Looker deve trazer hoje")
    st.caption("Baseado no seu CSV de planejamento. Estas rotas devem aparecer no Looker com motoristas atribuídos.")

    if df_prev.empty:
        st.warning("Nenhuma rota Envios Extra encontrada no mapeamento carregado.")
    else:
        cols = st.columns(min(len(df_prev), 4))
        for i, (_, row) in enumerate(df_prev.iterrows()):
            with cols[i % 4]:
                st.markdown(f"""
                <div class="card">
                    <div class="card-label">Rota Otimizada</div>
                    <div class="card-val">{row['Rota otimizada']}</div>
                    <hr style="margin:8px 0;border:none;border-top:1px solid #eee;">
                    <div style="font-size:.82rem;color:#444;line-height:1.7;">
                        🔁 Original: <b>{row['Rota original']}</b><br>
                        🚗 {row.get('Tipo de veículo','—')}<br>
                        📍 {row.get('Cluster','—')}<br>
                        📦 SPR: {row.get('SPR','—')}
                    </div>
                </div>
                """, unsafe_allow_html=True)

# ── SEÇÃO 2: RESULTADO DO LOOKER ──────────────────────────────────────────────
if btn:
    if st.session_state.df_map.empty:
        st.error("⚠️ Carregue ao menos um CSV de mapeamento na barra lateral.")
    elif arq_looker is None:
        st.error("⚠️ Carregue o CSV do Looker na barra lateral.")
    else:
        with st.spinner("Cruzando dados Looker × Planejamento..."):
            df_lk = carregar_looker(arq_looker)
            rel, plan = processar(df_lk, st.session_state.df_map)
            st.session_state.df_rel  = rel
            st.session_state.df_plan = plan
        st.rerun()

if not st.session_state.df_rel.empty:
    df_r = st.session_state.df_rel
    st.markdown("---")
    st.markdown("### 📊 Resultado: Looker × Planejamento")

    total    = len(df_r)
    corretos = (df_r["Status"] == "✅ Correto").sum()
    diverg   = total - corretos

    c1, c2, c3 = st.columns(3)
    for col, label, val, cor in [
        (c1, "Total Envios Extra", total, "#1a1a2e"),
        (c2, "✅ Corretos", corretos, "#155724"),
        (c3, "⚠️ Divergências", diverg, "#856404"),
    ]:
        with col:
            st.markdown(f'<div class="card"><div class="card-label">{label}</div>'
                        f'<div class="card-val" style="color:{cor}">{val}</div></div>',
                        unsafe_allow_html=True)

    tab1, tab2, tab3 = st.tabs(["📋 Todos", "✅ Corretos", "⚠️ Divergências"])
    with tab1: st.dataframe(df_r, use_container_width=True, hide_index=True)
    with tab2: st.dataframe(df_r[df_r["Status"]=="✅ Correto"], use_container_width=True, hide_index=True)
    with tab3: st.dataframe(df_r[df_r["Status"]!="✅ Correto"], use_container_width=True, hide_index=True)

    st.divider()
    ca, cb = st.columns(2)
    with ca:
        st.download_button("📥 Baixar Excel", data=to_excel(df_r),
            file_name=f"envios_extra_{date.today().strftime('%d%m%Y')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True)
    with cb:
        st.download_button("📥 Baixar CSV", data=df_r.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"envios_extra_{date.today().strftime('%d%m%Y')}.csv",
            mime="text/csv", use_container_width=True)

elif st.session_state.df_map.empty:
    st.info("👈 Comece carregando o CSV de mapeamento de rotas na barra lateral.")
else:
    st.info("👈 Agora exporte o CSV do Looker, carregue aqui e clique em **▶️ Processar**.")

st.divider()
st.caption(f"🕐 {agora().strftime('%d/%m/%Y %H:%M:%S')} · Horário de Brasília")
