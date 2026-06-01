import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import io
from datetime import date
from concurrent.futures import ThreadPoolExecutor

st.set_page_config(page_title="AROMATO", page_icon="🌸", layout="wide")

# ── ავტორიზაცია ───────────────────────────────────────────────
def check_login():
    if st.session_state.get("logged_in"):
        return True
    st.markdown("""
    <style>
    .login-box{max-width:380px;margin:80px auto;padding:40px;
        background:linear-gradient(135deg,#1e293b,#0f172a);
        border:1px solid #334155;border-radius:16px;text-align:center}
    </style>
    <div class="login-box">
        <h2 style="color:#f1f5f9;margin-bottom:8px">🌸 AROMATO</h2>
        <p style="color:#94a3b8;margin-bottom:24px">შეიყვანეთ სახელი და პაროლი</p>
    </div>""", unsafe_allow_html=True)

    with st.form("login_form"):
        username = st.text_input("მომხმარებელი")
        password = st.text_input("პაროლი", type="password")
        submit   = st.form_submit_button("შესვლა", use_container_width=True, type="primary")

    if submit:
        users = st.secrets.get("users", {})
        if username in users and users[username] == password:
            st.session_state["logged_in"]  = True
            st.session_state["username"]   = username
            st.rerun()
        else:
            st.error("❌ არასწორი სახელი ან პაროლი")
    return False

if not check_login():
    st.stop()

URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_KEY"]
HEADERS = {
    "apikey": KEY,
    "Authorization": f"Bearer {KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

# ── Connection pool — ერთი session მთელი სესიისთვის ──────────
@st.cache_resource
def get_session():
    s = requests.Session()
    s.headers.update(HEADERS)
    adapter = requests.adapters.HTTPAdapter(
        pool_connections=4, pool_maxsize=8, max_retries=2
    )
    s.mount("https://", adapter)
    return s

def sb_get(table, params=None):
    r = get_session().get(f"{URL}/rest/v1/{table}", params=params)
    return r.json() if r.ok else []

def sb_post(table, data):
    r = get_session().post(f"{URL}/rest/v1/{table}", json=data)
    return r.ok

def sb_patch(table, match_col, match_val, data):
    r = get_session().patch(f"{URL}/rest/v1/{table}",
                            params={match_col: f"eq.{match_val}"}, json=data)
    return r.ok

def sb_delete(table, row_id):
    r = get_session().delete(f"{URL}/rest/v1/{table}",
                             params={"id": f"eq.{row_id}"})
    return r.ok

def sb_get_parallel(calls):
    """calls = list of (table, params). Returns results in same order."""
    def fetch(args):
        return sb_get(*args)
    with ThreadPoolExecutor(max_workers=len(calls)) as ex:
        return list(ex.map(fetch, calls))

@st.cache_data(ttl=300)
def load_catalog():
    data = sb_get("katalogi", {"select": "dasaxeleba", "order": "dasaxeleba"})
    return [r["dasaxeleba"] for r in data] if data else []

@st.cache_data(ttl=60)
def load_stock():
    return sb_get("satskhob", {"select": "*"})

@st.cache_data(ttl=30)
def load_today_sales():
    return sb_get("gayidvebi", {
        "select": "tarixi,dasaxeleba,raodenoba,ghirebuleba,gadakhdis_metodi",
        "tarixi": f"eq.{date.today()}",
        "order": "created_at.desc"
    })

def date_filter(start, end):
    """PostgREST date range params — handles all combinations."""
    p = {"select": "tarixi,dasaxeleba,raodenoba"}
    if start and end:
        p["and"] = f"(tarixi.gte.{start},tarixi.lte.{end})"
    elif start:
        p["tarixi"] = f"gte.{start}"
    elif end:
        p["tarixi"] = f"lte.{end}"
    return p

# ── ნავიგაცია ─────────────────────────────────────────────────
st.sidebar.title("🌸 AROMATO")
st.sidebar.caption(f"👤 {st.session_state.get('username','')}")
page = st.sidebar.radio("გვერდი", ["გაყიდვა", "შესყიდვა", "საწყობი", "აღწერა", "ჟურნალი", "რეპორტები"])
if st.sidebar.button("🚪 გამოსვლა", use_container_width=True):
    st.session_state.clear()
    st.rerun()

st.sidebar.divider()
with st.sidebar.expander("➕ ახალი პროდუქტი"):
    new_product = st.text_input("დასახელება", key="new_prod_input", placeholder="მაგ. DIOR SAUVAGE")
    if st.button("დამატება", key="new_prod_btn", use_container_width=True, type="primary"):
        if new_product.strip():
            ok = sb_post("katalogi", {"dasaxeleba": new_product.strip().upper()})
            if ok:
                st.success("✅ დაემატა!")
                st.cache_data.clear()
            else:
                st.error("უკვე არსებობს ან შეცდომა")
        else:
            st.warning("შეიყვანეთ დასახელება")

# ════════════════════════════════════════════════════════════════
# 1. გაყიდვა
# ════════════════════════════════════════════════════════════════
if page == "გაყიდვა":
    st.title("🛍️ გაყიდვა")
    catalog = load_catalog()

    with st.form("sale_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            tarixi     = st.date_input("თარიღი", value=date.today())
            dasaxeleba = st.selectbox("დასახელება", catalog)
        with col2:
            raodenoba        = st.number_input("რაოდენობა", min_value=1, value=1, step=1)
            ghirebuleba      = st.number_input("ღირებულება (₾)", min_value=0.0, step=0.5, format="%.2f")
            gadakhdis_metodi = st.selectbox("გადახდის მეთოდი", ["თიბისი", "საქართველო", "ნაღდი"])

        submitted = st.form_submit_button("✅ შენახვა", use_container_width=True, type="primary")

    if submitted:
        ok = sb_post("gayidvebi", {
            "tarixi": str(tarixi),
            "dasaxeleba": dasaxeleba,
            "raodenoba": int(raodenoba),
            "ghirebuleba": float(ghirebuleba),
            "gadakhdis_metodi": gadakhdis_metodi
        })
        if ok:
            st.success(f"✅ {dasaxeleba} — {int(raodenoba)} ცალი შენახულია!")
            load_today_sales.clear()
        else:
            st.error("შეცდომა. სცადეთ თავიდან.")

    st.subheader("📋 დღევანდელი გაყიდვები")
    data = load_today_sales()
    if data:
        df = pd.DataFrame(data)
        df.columns = ["თარიღი", "დასახელება", "რაოდენობა", "ღირებულება", "გადახდის მეთოდი"]
        st.dataframe(df, use_container_width=True, hide_index=True)
        total = sum(float(r.get("ghirebuleba") or 0) for r in data)
        st.metric("დღის ჯამი", f"{total:.2f} ₾")
    else:
        st.info("დღეს გაყიდვები არ არის")

# ════════════════════════════════════════════════════════════════
# 2. შესყიდვა
# ════════════════════════════════════════════════════════════════
elif page == "შესყიდვა":
    st.title("📦 შესყიდვა")
    catalog = load_catalog()

    with st.form("purchase_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            tarixi     = st.date_input("თარიღი", value=date.today())
            dasaxeleba = st.selectbox("დასახელება", catalog)
        with col2:
            raodenoba = st.number_input("რაოდენობა", min_value=1, value=1, step=1)

        submitted = st.form_submit_button("✅ შენახვა", use_container_width=True, type="primary")

    if submitted:
        ok = sb_post("shesyidvebi", {
            "tarixi": str(tarixi),
            "dasaxeleba": dasaxeleba,
            "raodenoba": int(raodenoba)
        })
        if ok:
            st.success(f"✅ {dasaxeleba} — {int(raodenoba)} ცალი შენახულია!")
        else:
            st.error("შეცდომა.")

    st.subheader("📋 ბოლო შესყიდვები")
    data = sb_get("shesyidvebi", {
        "select": "tarixi,dasaxeleba,raodenoba",
        "order": "created_at.desc",
        "limit": "20"
    })
    if data:
        df = pd.DataFrame(data)
        df.columns = ["თარიღი", "დასახელება", "რაოდენობა"]
        st.dataframe(df, use_container_width=True, hide_index=True)

# ════════════════════════════════════════════════════════════════
# 3. საწყობი
# ════════════════════════════════════════════════════════════════
elif page == "საწყობი":
    st.title("🏪 საწყობი")

    filter_date = st.date_input("📅 ფილტრის თარიღი (ცარიელი = ახლა)", value=None)

    # ყველა საჭირო მონაცემი parallel-ად
    cat_data, stock_data, sold_data, purch_data = sb_get_parallel([
        ("katalogi",    {"select": "dasaxeleba", "order": "dasaxeleba"}),
        ("satskhob",    {"select": "*"}),
        ("gayidvebi",   date_filter(None, filter_date)),
        ("shesyidvebi", date_filter(None, filter_date)),
    ])
    stock_map  = {r["dasaxeleba"]: r.get("satarto_nashti", 0) for r in stock_data}
    stock_ids  = {r["dasaxeleba"]: r["id"] for r in stock_data}

    aghwera_dates = [r.get("aghwera_tarixi") for r in stock_data if r.get("aghwera_tarixi")]
    aghwera_start = min(aghwera_dates) if aghwera_dates else None

    # თუ აღწერის თარიღი გვაქვს — გადავფილტროთ
    if aghwera_start:
        sold_data  = [r for r in sold_data  if r["tarixi"] >= str(aghwera_start)]
        purch_data = [r for r in purch_data if r["tarixi"] >= str(aghwera_start)]

    sold_map  = {}
    for r in sold_data:
        sold_map[r["dasaxeleba"]] = sold_map.get(r["dasaxeleba"], 0) + r["raodenoba"]

    purch_map = {}
    for r in purch_data:
        purch_map[r["dasaxeleba"]] = purch_map.get(r["dasaxeleba"], 0) + r["raodenoba"]

    rows = []
    for r in cat_data:
        name    = r["dasaxeleba"]
        start   = stock_map.get(name, 0)
        bought  = purch_map.get(name, 0)
        sold    = sold_map.get(name, 0)
        current = start + bought - sold
        rows.append({
            "დასახელება": name,
            "სასტარტო":   start,
            "შეყიდული":   bought,
            "გაყიდული":   sold,
            "ნაშთი":      current
        })

    df = pd.DataFrame(rows)

    # სასტარტო ნაშთის შეცვლა
    with st.expander("✏️ სასტარტო ნაშთების რედაქტირება"):
        st.caption("შეიყვანეთ აღწერის თარიღი და ნაშთები → შენახვა")

        # აღწერის თარიღი — ერთი მთელი სიისთვის
        cur_aghwera = None
        if stock_data:
            dates = [r.get("aghwera_tarixi") for r in stock_data if r.get("aghwera_tarixi")]
            if dates:
                cur_aghwera = pd.to_datetime(dates[0]).date()
        aghwera_date = st.date_input(
            "📅 აღწერის თარიღი (ერთი ყველასთვის)",
            value=cur_aghwera or date.today()
        )

        stock_df = pd.DataFrame([
            {"დასახელება": r["dasaxeleba"], "სასტარტო ნაშთი": int(stock_map.get(r["dasaxeleba"], 0))}
            for r in cat_data
        ])
        edited_stock = st.data_editor(
            stock_df,
            use_container_width=True,
            hide_index=True,
            disabled=["დასახელება"],
            column_config={
                "სასტარტო ნაშთი": st.column_config.NumberColumn("სასტარტო ნაშთი", min_value=0, step=1)
            },
            key="stock_editor"
        )
        if st.button("💾 სასტარტო ნაშთების შენახვა", type="primary", use_container_width=True):
            saved = 0
            for _, row in edited_stock.iterrows():
                name = row["დასახელება"]
                val  = int(row["სასტარტო ნაშთი"])
                payload = {"satarto_nashti": val, "aghwera_tarixi": str(aghwera_date)}
                if name in stock_ids:
                    sb_patch("satskhob", "dasaxeleba", name, payload)
                else:
                    sb_post("satskhob", {"dasaxeleba": name, **payload})
                saved += 1
            st.success(f"✅ შენახულია: {saved} პროდუქტი (აღწერის თარიღი: {aghwera_date})")
            load_stock.clear()
            st.rerun()

    col_f1, col_f2 = st.columns(2)
    with col_f1:
        show_positive = st.checkbox("მხოლოდ ნაშთიანი (0-ზე მეტი)", value=False)
    with col_f2:
        show_negative = st.checkbox("მხოლოდ უარყოფითი ნაშთი", value=False)

    if show_positive:
        display_df = df[df["ნაშთი"] > 0]
    elif show_negative:
        display_df = df[df["ნაშთი"] < 0]
    else:
        display_df = df

    title = f"ნაშთი {filter_date}-მდე" if filter_date else "მიმდინარე ნაშთი"
    st.subheader(f"📊 {title}")
    st.dataframe(display_df, use_container_width=True, hide_index=True)

# ════════════════════════════════════════════════════════════════
# 4. აღწერა
# ════════════════════════════════════════════════════════════════
elif page == "აღწერა":
    st.title("📋 საწყობის აღწერა")
    st.caption("ჩაატარეთ ფიზიკური დათვლა — სისტემა გაჩვენებთ სხვაობას")

    cat_data   = sb_get("katalogi", {"select": "dasaxeleba", "order": "dasaxeleba"})
    stock_data = sb_get("satskhob", {"select": "*"})
    stock_map  = {r["dasaxeleba"]: r.get("satarto_nashti", 0) for r in stock_data}
    stock_ids  = {r["dasaxeleba"]: r["id"] for r in stock_data}

    aghwera_tarixi = st.date_input("📅 აღწერის თარიღი", value=date.today())

    # გამოვთვალოთ მოსალოდნელი ნაშთი ამ თარიღისთვის
    aghwera_dates = [r.get("aghwera_tarixi") for r in stock_data if r.get("aghwera_tarixi")]
    aghwera_start = min(aghwera_dates) if aghwera_dates else None

    sold_data  = sb_get("gayidvebi",   date_filter(aghwera_start, str(aghwera_tarixi)))
    purch_data = sb_get("shesyidvebi", date_filter(aghwera_start, str(aghwera_tarixi)))

    sold_map  = {}
    for r in sold_data:
        sold_map[r["dasaxeleba"]] = sold_map.get(r["dasaxeleba"], 0) + r["raodenoba"]
    purch_map = {}
    for r in purch_data:
        purch_map[r["dasaxeleba"]] = purch_map.get(r["dasaxeleba"], 0) + r["raodenoba"]

    # ცხრილი — მოსალოდნელი + ფაქტობრივი (user შეიყვანს)
    rows = []
    for r in cat_data:
        name     = r["dasaxeleba"]
        start    = stock_map.get(name, 0)
        bought   = purch_map.get(name, 0)
        sold     = sold_map.get(name, 0)
        expected = start + bought - sold
        rows.append({"დასახელება": name, "მოსალოდნელი": expected, "ფაქტობრივი": 0})

    df_aghwera = pd.DataFrame(rows)

    # არსებული აღწერა ამ თარიღისთვის (თუ უკვე შეიყვანეს)
    prev = sb_get("aghwera", {"select": "*", "tarixi": f"eq.{aghwera_tarixi}"})
    if prev:
        prev_map = {r["dasaxeleba"]: r["factobrivi_nashti"] for r in prev}
        df_aghwera["ფაქტობრივი"] = df_aghwera["დასახელება"].map(lambda n: prev_map.get(n, 0))

    edited_agh = st.data_editor(
        df_aghwera,
        use_container_width=True,
        hide_index=True,
        disabled=["დასახელება", "მოსალოდნელი"],
        column_config={
            "ფაქტობრივი": st.column_config.NumberColumn("ფაქტობრივი (დათვლილი)", min_value=0, step=1),
            "მოსალოდნელი": st.column_config.NumberColumn("მოსალოდნელი (სისტემა)"),
        },
        key="aghwera_editor"
    )

    if st.button("💾 შენახვა და შედარება", type="primary", use_container_width=True):
        # წავშალოთ ძველი ჩანაწერები ამ თარიღისთვის
        if prev:
            for p in prev:
                sb_delete("aghwera", p["id"])
        # ჩავწეროთ ახალი
        for _, row in edited_agh.iterrows():
            sb_post("aghwera", {
                "tarixi":             str(aghwera_tarixi),
                "dasaxeleba":         row["დასახელება"],
                "factobrivi_nashti":  int(row["ფაქტობრივი"]),
            })
        st.success("✅ შენახულია!")
        st.rerun()

    # შედარება — სხვაობა
    st.subheader("📊 შედარება")
    edited_agh["სხვაობა"] = edited_agh["ფაქტობრივი"] - edited_agh["მოსალოდნელი"]
    diff_df = edited_agh[edited_agh["სხვაობა"] != 0].copy()

    if diff_df.empty:
        st.success("✅ ყველა პროდუქტი ემთხვევა!")
    else:
        st.warning(f"⚠️ {len(diff_df)} პროდუქტი არ ემთხვევა")

        def color_diff(row):
            if row["სხვაობა"] > 0:
                return [""] * 3 + ["color: green; font-weight: bold"]
            else:
                return [""] * 3 + ["color: red; font-weight: bold"]

        st.dataframe(
            diff_df[["დასახელება", "მოსალოდნელი", "ფაქტობრივი", "სხვაობა"]]
            .style.apply(color_diff, axis=1),
            use_container_width=True,
            hide_index=True
        )

        # სასტარტო ნაშთის განახლება
        if st.button("🔄 სასტარტო ნაშთის განახლება ფაქტობრივი დათვლით", use_container_width=True):
            for _, row in edited_agh.iterrows():
                name = row["დასახელება"]
                val  = int(row["ფაქტობრივი"])
                payload = {"satarto_nashti": val, "aghwera_tarixi": str(aghwera_tarixi)}
                if name in stock_ids:
                    sb_patch("satskhob", "dasaxeleba", name, payload)
                else:
                    sb_post("satskhob", {"dasaxeleba": name, **payload})
            st.success("✅ სასტარტო ნაშთი განახლებულია ფაქტობრივი მონაცემებით!")
            st.rerun()

# ════════════════════════════════════════════════════════════════
# 5. ჟურნალი
# ════════════════════════════════════════════════════════════════
elif page == "ჟურნალი":
    st.title("📖 ჟურნალი")
    tab1, tab2 = st.tabs(["გაყიდვები", "შესყიდვები"])
    catalog = load_catalog()

    # ── გაყიდვები ────────────────────────────────────────────
    with tab1:
        c1, c2 = st.columns(2)
        with c1:
            d_from = st.date_input("დან", value=date.today().replace(day=1), key="gf")
        with c2:
            d_to   = st.date_input("მდე", value=date.today(), key="gt")

        data = sb_get("gayidvebi", {
            "select": "id,tarixi,dasaxeleba,raodenoba,ghirebuleba,gadakhdis_metodi",
            "tarixi": f"gte.{d_from}",
            "order": "tarixi.desc"
        })
        data = [r for r in data if r["tarixi"] <= str(d_to)]

        if data:
            df_orig = pd.DataFrame(data)
            ids     = df_orig["id"].tolist()
            df_edit = df_orig[["tarixi","dasaxeleba","raodenoba","ghirebuleba","gadakhdis_metodi"]].copy()
            df_edit.columns = ["თარიღი","დასახელება","რაოდენობა","ღირებულება","გადახდის მეთოდი"]
            df_edit["თარიღი"] = pd.to_datetime(df_edit["თარიღი"]).dt.date
            df_edit["წაშლა"] = False

            edited = st.data_editor(
                df_edit,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "დასახელება":    st.column_config.SelectboxColumn("დასახელება", options=catalog),
                    "გადახდის მეთოდი": st.column_config.SelectboxColumn("გადახდის მეთოდი", options=["თიბისი","საქართველო","ნაღდი"]),
                    "თარიღი":        st.column_config.DateColumn("თარიღი"),
                    "ღირებულება":    st.column_config.NumberColumn("ღირებულება", format="%.2f"),
                    "რაოდენობა":     st.column_config.NumberColumn("რაოდენობა", min_value=1),
                    "წაშლა":         st.column_config.CheckboxColumn("🗑️"),
                },
                key="sale_editor"
            )

            if st.button("💾 ცვლილებების შენახვა", key="save_sales", type="primary", use_container_width=True):
                saved = 0
                for i, row in edited.iterrows():
                    if not row["წაშლა"]:
                        sb_patch("gayidvebi", "id", ids[i], {
                            "tarixi":           str(row["თარიღი"]),
                            "dasaxeleba":       row["დასახელება"],
                            "raodenoba":        int(row["რაოდენობა"]),
                            "ghirebuleba":      float(row["ღირებულება"] or 0),
                            "gadakhdis_metodi": row["გადახდის მეთოდი"],
                        })
                        saved += 1
                st.success(f"✅ შენახულია: {saved}")
                st.rerun()

            # ── წაშლა ────────────────────────────────────────
            with st.expander("🗑️ ჩანაწერის წაშლა"):
                labels = [
                    f"{r['tarixi']} | {r['dasaxeleba']} | {r['raodenoba']} ც. | {r.get('ghirebuleba',0)} ₾"
                    for r in data
                ]
                sel_del = st.selectbox("აირჩიეთ ჩანაწერი", labels, key="del_sale_sel")
                del_idx = labels.index(sel_del)
                del_id  = ids[del_idx]
                if st.button("🗑️ წაშლა", key="del_sale_btn", type="primary", use_container_width=True):
                    if sb_delete("gayidvebi", del_id):
                        st.success("წაიშალა!")
                        st.rerun()

            total = sum(float(r.get("ghirebuleba") or 0) for r in data)
            st.metric("პერიოდის ჯამი", f"{total:.2f} ₾")

            # Excel გადმოწერა
            output = io.BytesIO()
            export_df = pd.DataFrame(data)[["tarixi","dasaxeleba","raodenoba","ghirebuleba","gadakhdis_metodi"]]
            export_df.columns = ["თარიღი","დასახელება","რაოდენობა","ღირებულება","გადახდის მეთოდი"]
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                export_df.to_excel(writer, index=False, sheet_name="გაყიდვები")
            st.download_button(
                label="📥 Excel-ად გადმოწერა",
                data=output.getvalue(),
                file_name=f"gayidvebi_{d_from}_{d_to}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        else:
            st.info("ჩანაწერი არ არის")

    # ── შესყიდვები ───────────────────────────────────────────
    with tab2:
        c1, c2 = st.columns(2)
        with c1:
            p_from = st.date_input("დან", value=date.today().replace(day=1), key="pf")
        with c2:
            p_to   = st.date_input("მდე", value=date.today(), key="pt")

        data2 = sb_get("shesyidvebi", {
            "select": "id,tarixi,dasaxeleba,raodenoba",
            "tarixi": f"gte.{p_from}",
            "order": "tarixi.desc"
        })
        data2 = [r for r in data2 if r["tarixi"] <= str(p_to)]

        if data2:
            df2_orig = pd.DataFrame(data2)
            ids2     = df2_orig["id"].tolist()
            df2_edit = df2_orig[["tarixi","dasaxeleba","raodenoba"]].copy()
            df2_edit.columns = ["თარიღი","დასახელება","რაოდენობა"]
            df2_edit["თარიღი"] = pd.to_datetime(df2_edit["თარიღი"]).dt.date
            df2_edit["წაშლა"] = False

            edited2 = st.data_editor(
                df2_edit,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "დასახელება": st.column_config.SelectboxColumn("დასახელება", options=catalog),
                    "თარიღი":     st.column_config.DateColumn("თარიღი"),
                    "რაოდენობა":  st.column_config.NumberColumn("რაოდენობა", min_value=1),
                    "წაშლა":      st.column_config.CheckboxColumn("🗑️"),
                },
                key="purch_editor"
            )

            if st.button("💾 ცვლილებების შენახვა", key="save_purch", type="primary", use_container_width=True):
                saved = 0
                for i, row in edited2.iterrows():
                    if not row["წაშლა"]:
                        sb_patch("shesyidvebi", "id", ids2[i], {
                            "tarixi":     str(row["თარიღი"]),
                            "dasaxeleba": row["დასახელება"],
                            "raodenoba":  int(row["რაოდენობა"]),
                        })
                        saved += 1
                st.success(f"✅ შენახულია: {saved}")
                st.rerun()

            # ── წაშლა ────────────────────────────────────────
            with st.expander("🗑️ ჩანაწერის წაშლა"):
                labels2 = [
                    f"{r['tarixi']} | {r['dasaxeleba']} | {r['raodenoba']} ც."
                    for r in data2
                ]
                sel_del2 = st.selectbox("აირჩიეთ ჩანაწერი", labels2, key="del_purch_sel")
                del_idx2 = labels2.index(sel_del2)
                del_id2  = ids2[del_idx2]
                if st.button("🗑️ წაშლა", key="del_purch_btn", type="primary", use_container_width=True):
                    if sb_delete("shesyidvebi", del_id2):
                        st.success("წაიშალა!")
                        st.rerun()
        else:
            st.info("ჩანაწერი არ არის")

# ════════════════════════════════════════════════════════════════
# 6. რეპორტები
# ════════════════════════════════════════════════════════════════
elif page == "რეპორტები":
    st.title("📊 რეპორტები")

    col1, col2 = st.columns(2)
    with col1:
        r_from = st.date_input("დან", value=date.today().replace(day=1), key="rf")
    with col2:
        r_to   = st.date_input("მდე", value=date.today(), key="rt")

    data = sb_get("gayidvebi", {
        "select": "tarixi,dasaxeleba,raodenoba,ghirebuleba,gadakhdis_metodi",
        "tarixi": f"gte.{r_from}",
        "order":  "tarixi"
    })
    data = [r for r in data if r["tarixi"] <= str(r_to)]

    if not data:
        st.info("არჩეულ პერიოდში გაყიდვები არ არის")
    else:
        df = pd.DataFrame(data)
        df["ghirebuleba"] = pd.to_numeric(df["ghirebuleba"], errors="coerce").fillna(0)
        df["tarixi"]      = pd.to_datetime(df["tarixi"])

        COLORS  = ["#6366f1", "#f59e0b", "#10b981"]
        CMAP    = {"თიბისი": "#6366f1", "საქართველო": "#f59e0b", "ნაღდი": "#10b981"}
        BG      = "rgba(0,0,0,0)"
        FONT    = dict(family="sans-serif", size=13, color="#e2e8f0")

        total    = df["ghirebuleba"].sum()
        tbc_sum  = df[df["gadakhdis_metodi"]=="თიბისი"]["ghirebuleba"].sum()
        geo_sum  = df[df["gadakhdis_metodi"]=="საქართველო"]["ghirebuleba"].sum()
        cash_sum = df[df["gadakhdis_metodi"]=="ნაღდი"]["ghirebuleba"].sum()

        # ── Responsive CSS ────────────────────────────────────
        st.markdown("""
        <style>
        [data-testid="metric-container"]{
            background:linear-gradient(135deg,#1e293b,#0f172a);
            border:1px solid #334155;border-radius:12px;
            padding:14px;
        }
        [data-testid="stMetricValue"]{font-size:1.4rem;font-weight:700}

        /* მობილური — მეტრიკები 2x2 */
        @media (max-width: 640px){
            [data-testid="stMetricValue"]{font-size:1.1rem}
            [data-testid="metric-container"]{padding:10px}
            [data-testid="stHorizontalBlock"]{flex-wrap:wrap}
            [data-testid="stHorizontalBlock"] > div{
                min-width:48% !important;
                flex:1 1 48% !important;
            }
            /* სათაური პატარა */
            h1{font-size:1.4rem !important}
            h2{font-size:1.1rem !important}
            /* sidebar ვიწრო */
            section[data-testid="stSidebar"]{min-width:200px !important}
        }
        </style>""", unsafe_allow_html=True)

        m1,m2,m3,m4 = st.columns(4)
        m1.metric("სულ ბრუნვა",    f"{total:,.2f} ₾")
        m2.metric("💳 თიბისი",      f"{tbc_sum:,.2f} ₾")
        m3.metric("🏦 საქართველო", f"{geo_sum:,.2f} ₾")
        m4.metric("💵 ნაღდი",       f"{cash_sum:,.2f} ₾")

        st.markdown("<br>", unsafe_allow_html=True)

        # მობილურზე ერთი სვეტი, დესქტოპზე — ორი
        col_a, col_b = st.columns([1, 1])

        # ── დონატი — თანხა ────────────────────────────────────
        with col_a:
            pie_df = df.groupby("gadakhdis_metodi")["ghirebuleba"].sum().reset_index()
            pie_df.columns = ["მეთოდი","თანხა"]
            fig1 = go.Figure(go.Pie(
                labels=pie_df["მეთოდი"],
                values=pie_df["თანხა"],
                hole=0.55,
                marker=dict(colors=COLORS, line=dict(color="#0f172a", width=3)),
                textinfo="label+percent",
                textfont=dict(size=13, color="#e2e8f0"),
                hovertemplate="<b>%{label}</b><br>%{value:,.2f} ₾<br>%{percent}<extra></extra>",
                pull=[0.04]*len(pie_df)
            ))
            fig1.add_annotation(text=f"<b>{total:,.0f}</b><br>₾",
                                x=0.5, y=0.5, showarrow=False,
                                font=dict(size=18, color="#f1f5f9"))
            fig1.update_layout(
                title=dict(text="გადახდის მეთოდი — თანხა", font=dict(size=14, color="#f1f5f9"), x=0.5),
                paper_bgcolor=BG, plot_bgcolor=BG, font=FONT,
                showlegend=True,
                legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5,
                            font=dict(color="#cbd5e1", size=11)),
                margin=dict(t=40, b=50, l=10, r=10), height=320
            )
            st.plotly_chart(fig1, use_container_width=True)

        # ── დონატი — ცალები ───────────────────────────────────
        with col_b:
            cnt_df = df.groupby("gadakhdis_metodi")["raodenoba"].sum().reset_index()
            cnt_df.columns = ["მეთოდი","ცალი"]
            total_cnt = cnt_df["ცალი"].sum()
            fig2 = go.Figure(go.Pie(
                labels=cnt_df["მეთოდი"],
                values=cnt_df["ცალი"],
                hole=0.55,
                marker=dict(colors=COLORS, line=dict(color="#0f172a", width=3)),
                textinfo="label+percent",
                textfont=dict(size=13, color="#e2e8f0"),
                hovertemplate="<b>%{label}</b><br>%{value} ც.<br>%{percent}<extra></extra>",
                pull=[0.04]*len(cnt_df)
            ))
            fig2.add_annotation(text=f"<b>{total_cnt}</b><br>ცალი",
                                x=0.5, y=0.5, showarrow=False,
                                font=dict(size=18, color="#f1f5f9"))
            fig2.update_layout(
                title=dict(text="გადახდის მეთოდი — ცალები", font=dict(size=14, color="#f1f5f9"), x=0.5),
                paper_bgcolor=BG, plot_bgcolor=BG, font=FONT,
                showlegend=True,
                legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5,
                            font=dict(color="#cbd5e1", size=11)),
                margin=dict(t=40, b=50, l=10, r=10), height=320
            )
            st.plotly_chart(fig2, use_container_width=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # ── ბარ — დღიური გაყიდვები ────────────────────────────
        daily = df.groupby(["tarixi","gadakhdis_metodi"])["ghirebuleba"].sum().reset_index()
        daily.columns = ["თარიღი","მეთოდი","თანხა"]
        fig3 = px.bar(daily, x="თარიღი", y="თანხა", color="მეთოდი",
                      color_discrete_map=CMAP, barmode="stack",
                      labels={"თანხა":"₾","თარიღი":""},
                      template="plotly_dark")
        fig3.update_traces(marker_line_width=0, opacity=0.9)
        fig3.update_layout(
            title=dict(text="დღიური გაყიდვები — გადახდის მეთოდი",
                       font=dict(size=14, color="#f1f5f9"), x=0.5),
            paper_bgcolor=BG, plot_bgcolor="rgba(15,23,42,0.6)",
            legend=dict(title="", orientation="h", yanchor="bottom", y=1.02,
                        xanchor="right", x=1, font=dict(color="#cbd5e1", size=11)),
            xaxis=dict(gridcolor="#1e293b", tickfont=dict(color="#94a3b8", size=10)),
            yaxis=dict(gridcolor="#1e293b", tickfont=dict(color="#94a3b8", size=10), ticksuffix=" ₾"),
            margin=dict(t=50, b=20, l=10, r=10), height=300
        )
        st.plotly_chart(fig3, use_container_width=True)

        # ── TOP 10 ────────────────────────────────────────────
        top = df.groupby("dasaxeleba").agg(
            თანხა=("ghirebuleba","sum"),
            ცალი=("raodenoba","sum")
        ).nlargest(10, "თანხა").reset_index()
        top.columns = ["პროდუქტი","თანხა","ცალი"]
        top["label"] = top.apply(lambda r: f"{r['ცალი']} ც. / {r['თანხა']:,.0f} ₾", axis=1)

        fig4 = px.bar(top, x="თანხა", y="პროდუქტი", orientation="h",
                      text="label", template="plotly_dark",
                      color="თანხა", color_continuous_scale=["#312e81","#6366f1","#a5b4fc"],
                      custom_data=["ცალი"])
        fig4.update_traces(
            textposition="outside",
            marker_line_width=0, opacity=0.9,
            hovertemplate="<b>%{y}</b><br>თანხა: %{x:,.2f} ₾<br>ცალი: %{customdata[0]}<extra></extra>"
        )
        fig4.update_layout(
            title=dict(text="TOP 10 — ყველაზე გაყიდვადი პროდუქტი",
                       font=dict(size=14, color="#f1f5f9"), x=0.5),
            paper_bgcolor=BG, plot_bgcolor="rgba(15,23,42,0.6)",
            coloraxis_showscale=False,
            xaxis=dict(gridcolor="#1e293b", tickfont=dict(color="#94a3b8", size=10), ticksuffix=" ₾"),
            yaxis=dict(gridcolor="#1e293b", tickfont=dict(color="#94a3b8", size=9),
                       categoryorder="total ascending"),
            margin=dict(t=40, b=10, l=10, r=90), height=370
        )
        st.plotly_chart(fig4, use_container_width=True)
