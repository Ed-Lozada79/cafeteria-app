import datetime
import json
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import streamlit as st

# ---------------------------------------------------------
# Configuración de Página
# ---------------------------------------------------------
st.set_page_config(
    page_title="Control Cafetería", page_icon="☕", layout="wide"
)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


@st.cache_resource
def conectar_sheets():
    if "gcp_service_account" in st.secrets:
        creds_dict = dict(st.secrets["gcp_service_account"])
        if "private_key" in creds_dict:
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    else:
        creds = Credentials.from_service_account_file(
            "credentials.json", scopes=SCOPES
        )

    client = gspread.authorize(creds)
    sheet = client.open("Cafeteria_BD")
    return sheet


try:
    sheet = conectar_sheets()
    hoja_consumos = sheet.worksheet("Consumos")
    hoja_usuarios = sheet.worksheet("Usuarios")
except Exception as e:
    st.error(f"❌ Error al conectar con Google Sheets: {e}")
    st.stop()

# ---------------------------------------------------------
# Detección de Parámetros URL (Modo QR vs Modo Admin)
# ---------------------------------------------------------
params = st.query_params
vista_qr = params.get("vista", None)

# Si el QR dirige a ?vista=consulta o ?vista=registro
if vista_qr == "consulta":
    st.sidebar.title("📌 Menú Cliente")
    opciones = ["👤 Consultar Mi Cuenta (Consumidor)"]
elif vista_qr == "registro":
    st.sidebar.title("📌 Menú Cliente")
    opciones = ["➕ Registrar Nuevo Usuario"]
else:
    # Modo completo (Administrador)
    st.sidebar.title("⚙️ Panel de Control")
    opciones = [
        "🛒 Registrar Consumo (Cafetería)",
        "💳 Registrar Abono (Cafetería)",
        "➕ Registrar Nuevo Usuario",
        "👤 Consultar Mi Cuenta (Consumidor)",
        "📱 Generar Códigos QR",
    ]

rol = st.sidebar.radio("Selecciona la vista:", opciones)

# ---------------------------------------------------------
# VISTA 1: REGISTRAR CONSUMO (CAFETERÍA)
# ---------------------------------------------------------
if rol == "🛒 Registrar Consumo (Cafetería)":
    st.header("Registrar Nuevo Pedido")

    df_usuarios = pd.DataFrame(hoja_usuarios.get_all_records())

    if df_usuarios.empty:
        st.warning("⚠️ No hay usuarios registrados en la base de datos.")
    else:
        df_usuarios = df_usuarios[df_usuarios["Nombre"].astype(str).str.strip() != ""]
        df_usuarios_ordenados = df_usuarios.sort_values(by="Nombre", key=lambda col: col.str.lower())

        opciones_usuarios = {
            f"{row['Nombre']} ({row['Area']})": row["Id_Usuario"]
            for _, row in df_usuarios_ordenados.iterrows()
        }

        with st.form("form_consumo", clear_on_submit=True):
            col1, col2 = st.columns(2)

            with col1:
                usuario_seleccionado = st.selectbox(
                    "Selecciona el Consumidor (Nombre - Área):",
                    options=list(opciones_usuarios.keys()),
                )

                id_usuario = opciones_usuarios.get(usuario_seleccionado)
                st.text_input("Id_Usuario / Cédula:", value=str(id_usuario), disabled=True)

            with col2:
                producto = st.text_input("Producto:")
                cantidad = st.number_input("Cantidad:", min_value=1, value=1)
                valor_unitario = st.number_input("Valor Unitario ($):", min_value=0, step=500)
                total_pedido = cantidad * valor_unitario
                st.markdown(f"### Total Pedido: **${total_pedido:,.0f}**")

            btn_guardar = st.form_submit_button("💾 Guardar Consumo")

            if btn_guardar:
                if not id_usuario or not producto or total_pedido <= 0:
                    st.error("Por favor completa el producto y asegúrate que el total sea mayor a 0.")
                else:
                    fecha_actual = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                    nueva_fila = [
                        fecha_actual,
                        str(id_usuario),
                        producto,
                        int(cantidad),
                        float(valor_unitario),
                        float(total_pedido),
                    ]

                    hoja_consumos.insert_row(nueva_fila, index=2)

                    idx = df_usuarios[df_usuarios["Id_Usuario"].astype(str) == str(id_usuario)].index[0]
                    num_fila = idx + 2

                    val_parcial = float(df_usuarios.loc[idx, "Total_Parcial"] or 0) + total_pedido
                    val_abono = float(df_usuarios.loc[idx, "Abono"] or 0)
                    val_general = val_parcial - val_abono

                    hoja_usuarios.update_cell(num_fila, 6, val_parcial)
                    hoja_usuarios.update_cell(num_fila, 8, val_general)

                    st.success(f"✅ ¡Consumo de ${total_pedido:,.0f} registrado exitosamente!")
                    st.cache_resource.clear()

# ---------------------------------------------------------
# VISTA 2: REGISTRAR ABONO (CAFETERÍA)
# ---------------------------------------------------------
elif rol == "💳 Registrar Abono (Cafetería)":
    st.header("Registrar Pago / Abono de Cliente")

    df_usuarios = pd.DataFrame(hoja_usuarios.get_all_records())

    if df_usuarios.empty:
        st.warning("⚠️ No hay usuarios registrados en la base de datos.")
    else:
        df_usuarios = df_usuarios[df_usuarios["Nombre"].astype(str).str.strip() != ""]
        df_usuarios_ordenados = df_usuarios.sort_values(by="Nombre", key=lambda col: col.str.lower())

        opciones_usuarios = {
            f"{row['Nombre']} ({row['Area']})": row["Id_Usuario"]
            for _, row in df_usuarios_ordenados.iterrows()
        }

        with st.form("form_abono", clear_on_submit=True):
            usuario_abono_sel = st.selectbox(
                "Selecciona el Cliente que realiza el abono:",
                options=list(opciones_usuarios.keys()),
            )
            id_usuario_abono = opciones_usuarios.get(usuario_abono_sel)
            monto_abono = st.number_input("Monto abonado ($):", min_value=0, step=1000)

            btn_abono = st.form_submit_button("💰 Registrar Abono")

            if btn_abono:
                if not id_usuario_abono or monto_abono <= 0:
                    st.error("Ingresa un monto mayor a 0.")
                else:
                    idx = df_usuarios[df_usuarios["Id_Usuario"].astype(str) == str(id_usuario_abono)].index[0]
                    num_fila = idx + 2

                    val_parcial = float(df_usuarios.loc[idx, "Total_Parcial"] or 0)
                    val_abono_actual = float(df_usuarios.loc[idx, "Abono"] or 0) + monto_abono
                    val_general = val_parcial - val_abono_actual

                    hoja_usuarios.update_cell(num_fila, 7, val_abono_actual)
                    hoja_usuarios.update_cell(num_fila, 8, val_general)

                    st.success(f"✅ Abono de ${monto_abono:,.0f} registrado para {usuario_abono_sel}.")
                    st.cache_resource.clear()

# ---------------------------------------------------------
# VISTA 3: REGISTRAR NUEVO USUARIO
# ---------------------------------------------------------
elif rol == "➕ Registrar Nuevo Usuario":
    st.header("Crear Nuevo Consumidor en el Sistema")

    df_usuarios = pd.DataFrame(hoja_usuarios.get_all_records())

    with st.form("form_nuevo_usuario", clear_on_submit=True):
        col_u1, col_u2 = st.columns(2)

        with col_u1:
            nuevo_id = st.text_input("Id_Usuario / Cédula / Documento (*):")
            nuevo_nombre = st.text_input("Nombre Completo (*):")
            nueva_area = st.text_input("Área / Departamento:")

        with col_u2:
            nuevo_correo = st.text_input("Correo Electrónico:")
            nuevo_whatsapp = st.text_input("Número de WhatsApp / Celular:")

        btn_crear_usuario = st.form_submit_button("👤 Registrar Usuario")

        if btn_crear_usuario:
            if not nuevo_id.strip() or not nuevo_nombre.strip():
                st.error("⚠️ El 'Id_Usuario' y el 'Nombre Completo' son campos obligatorios.")
            else:
                ids_existentes = (
                    df_usuarios["Id_Usuario"].astype(str).values if not df_usuarios.empty else []
                )

                if str(nuevo_id).strip() in ids_existentes:
                    st.error(f"❌ Ya existe un usuario registrado con el Id_Usuario '{nuevo_id}'.")
                else:
                    nuevo_registro = [
                        str(nuevo_id).strip(),
                        nuevo_nombre.strip(),
                        nueva_area.strip(),
                        nuevo_correo.strip(),
                        nuevo_whatsapp.strip(),
                        0,
                        0,
                        0,
                    ]

                    hoja_usuarios.insert_row(nuevo_registro, index=2)
                    st.success(f"✅ ¡El usuario **{nuevo_nombre}** fue registrado exitosamente!")
                    st.cache_resource.clear()

# ---------------------------------------------------------
# VISTA 4: CONSULTA DEL CONSUMIDOR (SOLO LECTURA)
# ---------------------------------------------------------
elif rol == "👤 Consultar Mi Cuenta (Consumidor)":
    st.header("Consulta de Estado de Cuenta")

    id_consulta = st.text_input("Ingresa tu Id_Usuario / Cédula:")

    if id_consulta:
        df_usuarios = pd.DataFrame(hoja_usuarios.get_all_records())

        if not df_usuarios.empty:
            match_user = df_usuarios[df_usuarios["Id_Usuario"].astype(str) == str(id_consulta)]

            if not match_user.empty:
                usuario_info = match_user.iloc[0]
                st.subheader(f"Bienvenido(a), **{usuario_info['Nombre']}** ({usuario_info['Area']})")

                c1, c2, c3 = st.columns(3)
                c1.metric("🛒 Total Consumido", f"${float(usuario_info['Total_Parcial'] or 0):,.0f}")
                c2.metric("💳 Total Abonado", f"${float(usuario_info['Abono'] or 0):,.0f}")
                c3.metric("🚨 Saldo Pendiente", f"${float(usuario_info['Total_General'] or 0):,.0f}")

                st.markdown("---")
                st.subheader("📋 Detalle de Consumos")

                df_consumos = pd.DataFrame(hoja_consumos.get_all_records())
                if not df_consumos.empty:
                    mis_consumos = df_consumos[df_consumos["Id_Usuario"].astype(str) == str(id_consulta)]
                    if not mis_consumos.empty:
                        tabla_ver = mis_consumos[["Fecha", "Producto", "Cantidad", "Valor", "Total"]].sort_values(
                            by="Fecha", ascending=False
                        )
                        st.dataframe(tabla_ver, use_container_width=True)
                    else:
                        st.info("No tienes consumos detallados registrados.")
            else:
                st.warning("No se encontró ningún usuario con ese número de identificación.")

# ---------------------------------------------------------
# VISTA 5: GENERADOR DE CÓDIGOS QR
# ---------------------------------------------------------
elif rol == "📱 Generar Códigos QR":
    st.header("Generador de Códigos QR para Imprimir")
    st.write("Copia la URL pública de tu aplicación desplegada en Streamlit Cloud y pégala aquí abajo:")

    url_base = st.text_input(
        "URL de tu app en Streamlit Cloud:",
        value="https://cafeteria-app-dw9qrntictwnamwwzpmddb.streamlit.app",  # Cambia por tu URL si es distinta
    )

    if url_base:
        # Asegurar que termine sin diagonal /
        url_base = url_base.rstrip("/")

        url_consulta = f"{url_base}/?vista=consulta"
        url_registro = f"{url_base}/?vista=registro"

        col_qr1, col_qr2 = st.columns(2)

        with col_qr1:
            st.subheader("1. QR - Consulta de Saldo")
            st.write("Imprime este QR para colocarlo en las mesas o mostrador.")
            qr_api_1 = f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data={url_consulta}"
            st.image(qr_api_1)
            st.code(url_consulta)

        with col_qr2:
            st.subheader("2. QR - Registro de Nuevos Usuarios")
            st.write("Imprime este QR para que nuevos clientes se registren.")
            qr_api_2 = f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data={url_registro}"
            st.image(qr_api_2)
            st.code(url_registro)