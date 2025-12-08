import streamlit as st #libreria para la aplicacion web
import pandas as pd #libreria para la lectura de los .xlsx
import gspread #libreria para el acceso a google sheets
from datetime import datetime, timedelta # libreria para establecer la hora
import matplotlib.pyplot as plt # libreria para generar los graficos
import numpy as np # libreria para calculos matematicos avanzados

st.set_page_config(
    layout="wide", 
    page_title="Inventario B&M", 
    page_icon="📦",
    initial_sidebar_state="collapsed"
)

st.markdown("""
    <style>
    .main {
        background-color: #f8f9fa;
    }
    h1 {
        color: #1f77b4;
        text-align: center;
        font-family: 'Helvetica', sans-serif;
    }
    h3 {
        color: #4a4a4a;
        border-bottom: 2px solid #e0e0e0;
        padding-bottom: 10px;
    }
    .stButton>button {
        width: 100%;
        border-radius: 8px;
        font-weight: bold;
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.5rem;
    }
    /* NUEVO: Estilo para el login */
    .login-container {
        padding: 30px; 
        border-radius: 10px; 
        background-color: white; 
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        max-width: 400px;
        margin: auto;
    }
    </style>
    """, unsafe_allow_html=True)

USUARIOS = {
    "admin": {"pass": "admin123", "rol": "administrador"},
    "empleado": {"pass": "user123", "rol": "empleado"}
}

def check_login():
    """Verifica credenciales y asigna estado de sesión"""
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
        st.session_state.rol = None
        st.session_state.usuario_actual = None

    if not st.session_state.logged_in:
        st.markdown("<br><br>", unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1, 2, 1])
        with c2:
            st.markdown("<h2 style='text-align: center;'>🔐 Iniciar Sesión</h2>", unsafe_allow_html=True)
            with st.form("login_form"):
                user = st.text_input("Usuario")
                password = st.text_input("Contraseña", type="password")
                submit = st.form_submit_button("Ingresar", type="primary")
                
                if submit:
                    if user in USUARIOS and USUARIOS[user]["pass"] == password:
                        st.session_state.logged_in = True
                        st.session_state.usuario_actual = user
                        st.session_state.rol = USUARIOS[user]["rol"]
                        st.rerun()
                    else:
                        st.error("Usuario o contraseña incorrectos")
        return False
    return True
    
if not check_login():
    st.stop()

with st.sidebar:
    st.write(f"👤 **{st.session_state.usuario_actual}**")
    st.write(f"🔑 **Rol:** {st.session_state.rol}")
    if st.button("Cerrar Sesión"):
        st.session_state.logged_in = False
        st.session_state.rol = None
        st.rerun()


st.title("📦 Sistema de Gestión de Inventario B&M")
st.markdown("---")

GOOGLE_SHEET_ID = "1Zu-Dq6UCYRKMTWNsxj8FsMzzpAdtvl-qb40CVEmwl44"

INVENTARIO_WS = 'inventario'
STOCK_MINIMO_WS = 'stock_minimo'
MOVIMIENTOS_WS = 'movimientos'

inventario_headers = ["codigo", "nombre", "marca", "cantidad", "fecha_vencimiento", "precio_costo", "precio_venta"]
stock_minimo_headers = ['codigo', 'stock_min']
movimientos_headers = ["timestamp", "tipo", "codigo", "nombre", "cantidad", "fecha_vencimiento", "precio_costo", "precio_venta"]

inventario = {}
stock_minimo = {}
movimientos = []

@st.cache_resource(ttl=3600)
def obtener_conexion():
    """Conecta con Google Sheets usando st.secrets"""
    try:
        credentials = dict(st.secrets["gcp_service_account"])
        
        if "private_key" in credentials:
            credentials["private_key"] = credentials["private_key"].replace("\\n", "\n")
        
        gc = gspread.service_account_from_dict(credentials)
        sh = gc.open_by_key(GOOGLE_SHEET_ID)
        return sh
    except Exception as e:
        st.error(f"Error de conexión: {e}. \n\nPosibles causas:\n1. El bot no tiene permiso de 'Editor' en la hoja.\n2. La API de Google Sheets no está habilitada en Google Cloud.")
        st.stop()

def check_worksheets(sh):
    """Asegura que las pestañas existan y tengan headers"""
    try:
        titulos_actuales = [ws.title for ws in sh.worksheets()]
        
        if INVENTARIO_WS not in titulos_actuales:
            ws = sh.add_worksheet(title=INVENTARIO_WS, rows=100, cols=10)
            ws.append_row(inventario_headers)
            
        if STOCK_MINIMO_WS not in titulos_actuales:
            ws = sh.add_worksheet(title=STOCK_MINIMO_WS, rows=100, cols=5)
            ws.append_row(stock_minimo_headers)
            
        if MOVIMIENTOS_WS not in titulos_actuales:
            ws = sh.add_worksheet(title=MOVIMIENTOS_WS, rows=100, cols=10)
            ws.append_row(movimientos_headers)
    except Exception as e:
        st.error(f"Error verificando pestañas: {e}")

def normalizar_fecha(fecha_obj) -> str:
    if not fecha_obj: return ""
    try:
        if isinstance(fecha_obj, str):
            fecha_obj = fecha_obj.strip()
            if ' ' in fecha_obj: fecha_obj = fecha_obj.split(' ')[0]
            if 'T' in fecha_obj: fecha_obj = fecha_obj.split('T')[0]
            return fecha_obj
        
        if hasattr(fecha_obj, 'strftime'):
            return fecha_obj.strftime("%Y-%m-%d")
        
        return str(fecha_obj).split(' ')[0]
    except: return ""

def _convertir_a_numero(valor, por_defecto=0):
    if valor is None or valor == '': return por_defecto
    try: return int(valor)
    except (ValueError, TypeError):
        try: return float(valor)
        except (ValueError, TypeError): return por_defecto

def stock_total(codigo: str) -> int:
    return sum(l["cantidad"] for l in inventario.get(codigo, []))

def ordenar_lotes_fifo(lotes):
    def clave(l):
        fv = l.get("fecha_vencimiento", "")
        if not fv:
            return (datetime.max, 1)
        try:
            return (datetime.fromisoformat(fv), 0)
        except Exception:
            return (datetime.max, 1)
    return sorted(lotes, key=clave)

def _escribir_sheet(ws_name, headers, datos):
    """Sobreescribe una pestaña completa con nuevos datos"""
    try:
        sh = obtener_conexion()
        ws = sh.worksheet(ws_name)
        ws.clear()
        ws.append_row(headers)
        if datos:
            datos_limpios = []
            for fila in datos:
                fila_expandida = list(fila) + ["" for _ in range(len(headers) - len(fila))]
                fila_str = [str(celda) if celda is not None else "" for celda in fila_expandida[:len(headers)]]
                datos_limpios.append(fila_str)

            ws.append_rows(datos_limpios, value_input_option='USER_ENTERED')
    except Exception as e:
        st.error(f"Error guardando en {ws_name}: {e}")

def cargar_todo():
    """Carga datos desde Sheets a memoria. Se ejecuta en cada run de Streamlit."""
    inventario.clear()
    stock_minimo.clear()
    movimientos.clear()
    
    sh = obtener_conexion()
    check_worksheets(sh)
    
    try:
        ws_inv = sh.worksheet(INVENTARIO_WS)
        vals_inv = ws_inv.get_all_values()
        if len(vals_inv) > 1:
            for fila in vals_inv[1:]: # Saltar header
                fila += [""] * (len(inventario_headers) - len(fila))
                codigo, nombre, marca, cant, fv, pc, pv = fila[:len(inventario_headers)]
                
                if not codigo: continue
                
                lote = {
                    'nombre': nombre,
                    'marca': marca,
                    'cantidad': _convertir_a_numero(cant),
                    'fecha_vencimiento': normalizar_fecha(fv),
                    'precio_costo': _convertir_a_numero(pc),
                    'precio_venta': _convertir_a_numero(pv)
                }
                
                if codigo not in inventario: inventario[codigo] = []
                inventario[codigo].append(lote)
    except Exception as e: st.error(f"Error leyendo inventario: {e}")

    try:
        ws_min = sh.worksheet(STOCK_MINIMO_WS)
        vals_min = ws_min.get_all_values()
        if len(vals_min) > 1:
            for fila in vals_min[1:]:
                if fila and fila[0]:
                    stock_minimo[fila[0]] = _convertir_a_numero(fila[1] if len(fila)>1 else 0)
    except Exception as e: st.error(f"Error leyendo stock minimo: {e}")

    try:
        ws_mov = sh.worksheet(MOVIMIENTOS_WS)
        vals_mov = ws_mov.get_all_values()
        if len(vals_mov) > 1:
            for fila in vals_mov[1:]:
                movimientos.append(fila[:len(movimientos_headers)])
    except Exception as e: st.error(f"Error leyendo movimientos: {e}")
    
    st.session_state['data_loaded'] = True
    
def guardar_inventario():
    filas = []
    for codigo, lotes in inventario.items():
        for d in lotes:
            filas.append([
                codigo, d.get('nombre',""), d.get('marca',""), d.get('cantidad',0),
                d.get('fecha_vencimiento',""), d.get('precio_costo',0), d.get('precio_venta',0)
            ])
    _escribir_sheet(INVENTARIO_WS, inventario_headers, filas)

def guardar_stock_minimo():
    filas = [[k, v] for k, v in stock_minimo.items()]
    _escribir_sheet(STOCK_MINIMO_WS, stock_minimo_headers, filas)

def registrar_movimiento(tipo, codigo, nombre, cantidad, fecha_vencimiento, precio_costo, precio_venta):
    nueva_fila = [
        (datetime.now() - timedelta(hours=3)).isoformat(timespec="seconds"),
        tipo,
        str(codigo),
        nombre,
        cantidad,
        fecha_vencimiento or "",
        precio_costo if precio_costo is not None else 0,
        precio_venta if precio_venta is not None else 0,
    ]
    try:
        sh = obtener_conexion()
        ws = sh.worksheet(MOVIMIENTOS_WS)
        fila_str = [str(x) for x in nueva_fila]
        ws.append_row(fila_str)
        movimientos.append(nueva_fila) 
    except Exception as e:
        st.error(f"Error registrando movimiento: {e}")
        
if 'data_loaded' not in st.session_state:
    cargar_todo()
else:
    cargar_todo()

tab1, tab2, tab3, tab4, tab5, tab6 = None, None, None, None, None, None

if st.session_state.rol == "administrador":
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📥 Entrada", "📤 Salida", "📋 Inventario", 
        "📊 Historial", "📉 Stock Mínimo", "⏰ Vencimientos"
    ])
else:
    tab1, tab2 = st.tabs(["📥 Entrada", "📤 Salida"])

with tab1:
    st.subheader("📥 Registro de Entradas")
    
    if 'reset_counter' not in st.session_state:
        st.session_state.reset_counter = 0

    input_key = f"entrada_input_{st.session_state.reset_counter}"
    
    col_search, _ = st.columns([1, 1])
    with col_search:
        entrada = st.text_input("🔍 Escanee código o escriba 'buscar': ", key=input_key)
    
    codigo_seleccionado = None
    
    if entrada:
        if entrada.lower() == 'buscar':
            productos_lista = []
            for codigo, lotes in inventario.items():
                if lotes:
                    base = lotes[0]
                    nombre = base.get('nombre') or 'N/A'
                    marca = base.get('marca') or 'N/A'
                    productos_lista.append((codigo, nombre, marca))
                
            productos_lista.sort(key=lambda x: x[1])

            opciones = [f"{i+1}) {nombre} - {marca} (Código: {codigo})" 
                                            for i, (codigo, nombre, marca) in enumerate(productos_lista)]
            
            opciones.insert(0, "Cancelar")
            seleccion = st.selectbox("Seleccione un producto", opciones)

            if seleccion == 'Cancelar':
                codigo_seleccionado = None
            else:
                idx = opciones.index(seleccion) - 1
                codigo_seleccionado = productos_lista[idx][0]
                st.success(f"✅ Seleccionado: {productos_lista[idx][1]}")
        else:
            codigo_seleccionado = entrada

    if codigo_seleccionado:
        es_nuevo = codigo_seleccionado not in inventario
        no_tiene_min = codigo_seleccionado not in stock_minimo or stock_minimo[codigo_seleccionado] is None
        
        st.markdown("---")
        if es_nuevo:
            st.info(f"🆕 El código **{codigo_seleccionado}** es nuevo. Complete los datos.")
        else:
            base = inventario[codigo_seleccionado][0]
            st.success(f"📦 Editando: **{base.get('nombre')}** ({base.get('marca')})")
        
        with st.form("form_entrada", clear_on_submit = True):
            c1, c2 = st.columns(2)
            
            nombre_def = '' if es_nuevo else inventario[codigo_seleccionado][0].get('nombre', '')
            marca_def = '' if es_nuevo else inventario[codigo_seleccionado][0].get('marca', '')
            pc_def = 0 if es_nuevo else inventario[codigo_seleccionado][0].get('precio_costo', 0)
            pv_def = 0 if es_nuevo else inventario[codigo_seleccionado][0].get('precio_venta', 0)
            cant_min_def = 0 if no_tiene_min else stock_minimo[codigo_seleccionado]
            
            with c1:
                st.markdown("**Datos del Producto**")
                nombre = st.text_input("Nombre", value = nombre_def, disabled = not es_nuevo)
                marca = st.text_input("Marca", value = marca_def, disabled = not es_nuevo)
                cantidad = st.number_input("Cantidad a ingresar", min_value = 0, value = 1, step = 1)
                
            with c2:
                st.markdown("**Precios y Alertas**")
                precio_costo = st.number_input("Precio Costo", min_value = 0, value = int(pc_def), disabled = not es_nuevo)
                precio_venta = st.number_input("Precio Venta", min_value = 0, value = int(pv_def), disabled = not es_nuevo)
                cant_min = st.number_input("Stock Mínimo", min_value = 0, value = int(cant_min_def))
            
            st.markdown("**Vencimiento**")
            col_venc1, col_venc2 = st.columns(2)
            with col_venc1:
                aplica_vencimiento = st.checkbox("¿Tiene fecha de vencimiento?", value = True)
            with col_venc2:
                fecha_vencimiento = st.date_input("Fecha Vencimiento", value = datetime.now().date())

            st.markdown("<br>", unsafe_allow_html=True)
            submitted = st.form_submit_button("💾 Guardar Entrada", type="primary")

            if submitted:
                fv = normalizar_fecha(fecha_vencimiento) if aplica_vencimiento else ""

                if es_nuevo:
                    lote = {
                        'nombre': nombre, 'marca': marca, 'cantidad': cantidad,
                        'fecha_vencimiento': fv, 'precio_costo': precio_costo, 'precio_venta': precio_venta
                    }
                    inventario[codigo_seleccionado] = [lote]
                    stock_minimo[codigo_seleccionado] = cant_min
                    mensaje = f'Producto {nombre} creado con éxito'
                else:
                    lotes = inventario[codigo_seleccionado]
                    lote_existente = next((l for l in lotes if l.get("fecha_vencimiento", "") == fv), None)

                    if lote_existente:
                        lote_existente['cantidad'] += cantidad
                        mensaje = f"Se agregaron {cantidad} unidades al lote existente ({fv})"
                    else:
                        lotes.append({
                            'nombre': nombre, 'marca': marca, 'cantidad': cantidad,
                            'fecha_vencimiento': fv, 'precio_costo': precio_costo, 'precio_venta': precio_venta
                        })
                        stock_minimo[codigo_seleccionado] = cant_min
                        mensaje = f"Se creó un nuevo lote con {cantidad} unidades ({fv})"

                guardar_inventario()
                guardar_stock_minimo()
                registrar_movimiento("entrada", codigo_seleccionado, nombre, cantidad, fv, precio_costo, precio_venta)
                st.success(mensaje) 
                st.session_state.reset_counter += 1
                st.rerun()

with tab2:
    st.subheader("📤 Registro de Salidas")
    
    if "lista" not in st.session_state:
        st.session_state.lista = {}
    
    if "producto_pendiente_salida" not in st.session_state:
        st.session_state.producto_pendiente_salida = None

    def procesar_codigo_escaneado():
        codigo_leido = st.session_state.input_salida_codigo
        if not codigo_leido: return
        
        # Limpiar input inmediatamente para UX
        st.session_state.input_salida_codigo = ""
        codigo = codigo_leido.strip()
        
        if codigo not in inventario:
            st.toast(f"❌ El código {codigo} no existe")
            return

        # Establecer producto pendiente para mostrar el formulario de cantidad
        st.session_state.producto_pendiente_salida = codigo

    # Input de escaneo
    st.text_input("🔢 Escanee código para agregar a salida:", 
                  key="input_salida_codigo", 
                  on_change=procesar_codigo_escaneado)

    # Bloque de selección de cantidad si hay un producto pendiente
    if st.session_state.producto_pendiente_salida:
        cod_pend = st.session_state.producto_pendiente_salida
        
        if cod_pend in inventario:
            lotes = inventario[cod_pend]
            nombre_prod = lotes[0]['nombre']
            marca_prod = lotes[0]['marca']
            stock_disp_total = stock_total(cod_pend)
            en_lista = st.session_state.lista.get(cod_pend, 0)
            stock_real_disp = stock_disp_total - en_lista

            st.info(f"🛒 Seleccionando cantidad para: **{nombre_prod}** ({marca_prod})")
            st.write(f"Stock total: {stock_disp_total} | En carrito: {en_lista} | **Disponible: {stock_real_disp}**")

            if stock_real_disp <= 0:
                st.error("⚠️ Sin stock disponible para agregar más.")
                if st.button("Cancelar selección"):
                    st.session_state.producto_pendiente_salida = None
                    st.rerun()
            else:
                with st.form("form_cantidad_salida"):
                    col_cant, col_btn = st.columns([1,1])
                    with col_cant:
                        cantidad_selec = st.number_input("Cantidad:", min_value=1, max_value=int(stock_real_disp), value=1, step=1)
                    with col_btn:
                        st.markdown("<br>", unsafe_allow_html=True)
                        b_agregar = st.form_submit_button("➕ Agregar al Carrito", type="primary")
                        b_cancelar = st.form_submit_button("❌ Cancelar")

                    if b_agregar:
                        if cod_pend in st.session_state.lista:
                            st.session_state.lista[cod_pend] += cantidad_selec
                        else:
                            st.session_state.lista[cod_pend] = cantidad_selec
                        
                        st.toast(f"✅ Agregado: {cantidad_selec} de {nombre_prod}")
                        st.session_state.producto_pendiente_salida = None
                        st.rerun()
                    
                    if b_cancelar:
                        st.session_state.producto_pendiente_salida = None
                        st.rerun()
        else:
             st.error("El producto ya no existe en el inventario.")
             st.session_state.producto_pendiente_salida = None

    st.divider()
    
    c_lista, c_resumen = st.columns([2, 1])
    
    with c_lista:
        st.markdown("### 🛒 Carrito de Salida")
        if not st.session_state.lista:
            st.info("El carrito está vacío.")
        else:
            for codigo, cant_lista in st.session_state.lista.items():
                if codigo in inventario:
                    nombre = inventario[codigo][0]['nombre']
                    marca = inventario[codigo][0]['marca']
                    st.markdown(f"- **{nombre}** ({marca}): `{cant_lista}` unidades")
    
    with c_resumen:
        if st.session_state.lista:
            total_items = sum(st.session_state.lista.values())
            st.metric("Total Items", total_items)
            
            if st.button("🚀 Confirmar Salida", type="primary"):
                for codigo_prod, cantidad_sacar in st.session_state.lista.items():
                    if codigo_prod not in inventario: continue

                    lotes_a_modificar = ordenar_lotes_fifo(inventario[codigo_prod])
                    restante = cantidad_sacar
                    nombre_prod = lotes_a_modificar[0]['nombre']

                    lotes_finales = []
                    for l in lotes_a_modificar:
                        if restante > 0:
                            toma = min(l['cantidad'], restante)
                            l['cantidad'] -= toma
                            restante -= toma
                            registrar_movimiento("salida", codigo_prod, nombre_prod, toma, l.get('fecha_vencimiento',''), l.get('precio_costo'), l.get('precio_venta'))
                        if l['cantidad'] > 0:
                            lotes_finales.append(l)
                    
                    if not lotes_finales:
                        if codigo_prod in inventario: del inventario[codigo_prod]
                    else:
                        inventario[codigo_prod] = lotes_finales
                
                guardar_inventario()
                st.session_state.lista = {}
                st.success("Salidas registradas correctamente!")
                st.rerun() 

if tab3:
    with tab3:
        st.subheader("📋 Inventario Completo")
        
        try:
            sh = obtener_conexion()
            ws_inv = sh.worksheet(INVENTARIO_WS)
            data = ws_inv.get_all_values()
            
            if len(data) > 1:
                df_inv = pd.DataFrame(data[1:], columns=data[0])
                df_inv['cantidad'] = df_inv['cantidad'].apply(_convertir_a_numero)
            else:
                st.warning("Inventario vacío.")
                df_inv = pd.DataFrame(columns=inventario_headers)

            c_search, c_metric1, c_metric2 = st.columns([2, 1, 1])
            with c_search:
                busqueda = st.text_input("🔍 Buscar en inventario:", key="search_inv", placeholder="Nombre, Marca o Código...")
            
            if busqueda:
                busqueda_lower = busqueda.lower()
                filtro = (df_inv['codigo'].astype(str).str.contains(busqueda_lower, case=False, na=False)) | \
                        (df_inv['nombre'].astype(str).str.contains(busqueda_lower, case=False, na=False)) | \
                        (df_inv['marca'].astype(str).str.contains(busqueda_lower, case=False, na=False))
                df_filtrado = df_inv[filtro]
            else:
                df_filtrado = df_inv

            with c_metric1:
                st.metric("Total Productos", len(df_filtrado))
            with c_metric2:
                total_stock_view = df_filtrado['cantidad'].sum() if not df_filtrado.empty else 0
                st.metric("Stock Total Unidades", total_stock_view)
            
            st.dataframe(
                df_filtrado, 
                use_container_width=True,
                height=500,
                hide_index=True,
                column_config={
                    'codigo': st.column_config.TextColumn("Código"),
                    'nombre': st.column_config.TextColumn("Nombre"),
                    'marca': st.column_config.TextColumn("Marca"),
                    "fecha_vencimiento": st.column_config.TextColumn("Vencimiento", width="medium"),
                    "cantidad": st.column_config.NumberColumn("Stock", format="%d"),
                    "precio_costo": st.column_config.NumberColumn("Costo", format="$%d"),
                    "precio_venta": st.column_config.NumberColumn("Venta", format="$%d"),
                }
            )
            
        except Exception as e:
            st.error(f"Error cargando inventario: {e}")

    with tab4:
        st.subheader("📊 Historial de Movimientos")
        
        with st.expander("🛠️ Filtros de Búsqueda", expanded=True):
            col_izq, col_der = st.columns(2)

            with col_izq:
                productos_lista = []
                for codigo, lotes in inventario.items():
                    if lotes:
                        base = lotes[0]
                        nombre = base.get('nombre') or 'N/A'
                        marca = base.get('marca') or 'N/A'
                        productos_lista.append((codigo, nombre, marca))
                productos_lista.sort(key=lambda x: x[1])

                opciones = [f"{i+1}) {nombre} - {marca} (Código: {codigo})" for i, (codigo, nombre, marca) in enumerate(productos_lista)]
                opciones.insert(0, "Cancelar")
                opciones.insert(1, 'Todos los productos')
                seleccion = st.selectbox("Producto:", opciones, key="mov_prod_sel")

                codigo_seleccionado = None
                if seleccion != 'Cancelar' and seleccion != 'Todos los productos':
                    idx = opciones.index(seleccion) - 2
                    codigo_seleccionado = productos_lista[idx][0]
                
                tipo_movimiento = st.selectbox("Tipo:", ["Todos", "entrada", "salida"], key="tipo_movimiento")

            with col_der:
                c_f1, c_f2 = st.columns(2)
                with c_f1: fecha_inicio = st.date_input("Desde:", key="mov_f_ini")
                with c_f2: fecha_fin = st.date_input("Hasta:", key="mov_f_fin")
                
                st.markdown("<br>", unsafe_allow_html=True)
                btn_filtrar = st.button("🔎 Buscar Movimientos", type="primary")

        if btn_filtrar:
            if not movimientos:
                st.info("No hay movimientos registrados.")
            else:
                try:
                    df = pd.DataFrame(movimientos, columns=movimientos_headers)
                    df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
                    
                    fecha_inicio = pd.to_datetime(fecha_inicio)
                    fecha_fin = pd.to_datetime(fecha_fin) + pd.Timedelta(days=1)
                    
                    df_filtrado = df.loc[(df["timestamp"] >= fecha_inicio) & (df["timestamp"] < fecha_fin)].copy()
                    df_filtrado['cantidad'] = df_filtrado['cantidad'].apply(_convertir_a_numero)

                    if tipo_movimiento != "Todos":
                        df_filtrado = df_filtrado[df_filtrado['tipo'] == tipo_movimiento]

                    if codigo_seleccionado is not None:
                        df_filtrado = df_filtrado[df_filtrado['codigo'] == codigo_seleccionado]

                    c_graf, c_tabla = st.columns([1, 1])
                    
                    with c_graf:
                        if tipo_movimiento == "Todos" or tipo_movimiento == "entrada":
                            df_e = df_filtrado[df_filtrado['tipo'] == 'entrada']
                            if not df_e.empty:
                                fig, ax = plt.subplots(figsize=(6, 4))
                                ax.scatter(df_e["timestamp"], df_e["cantidad"], alpha=0.7, color='green')
                                ax.set_title("Entradas")
                                ax.tick_params(axis='x', rotation=45)
                                st.pyplot(fig)
                        
                        if tipo_movimiento == "Todos" or tipo_movimiento == "salida":
                            df_s = df_filtrado[df_filtrado['tipo'] == 'salida']
                            if not df_s.empty:
                                fig2, ax2 = plt.subplots(figsize=(6, 4))
                                ax2.scatter(df_s["timestamp"], df_s["cantidad"], alpha=0.7, color='red')
                                ax2.set_title("Salidas")
                                ax2.tick_params(axis='x', rotation=45)
                                st.pyplot(fig2)

                    with c_tabla:
                        df_filtrado['fecha'] = df_filtrado['timestamp'].dt.date
                        df_filtrado['hora'] = df_filtrado['timestamp'].dt.time
                        
                        st.dataframe(
                            df_filtrado[["fecha", "hora", "tipo", "nombre", "cantidad"]],
                            hide_index=True,
                            use_container_width=True
                        )
                except Exception as e:
                    st.error(f"Error procesando datos: {e}")

    with tab5:
        st.subheader("📉 Niveles de Stock")

        data_rows = []
        for c, lotes in inventario.items():
            if lotes:
                base = lotes[0]
                data_rows.append({
                    'codigo': c, 'nombre': base.get('nombre'), 'stock_total_calc': stock_total(c)
                })
        df_inv_sin_lotes = pd.DataFrame(data_rows)
        
        df_stock_min = pd.DataFrame(list(stock_minimo.items()), columns=['codigo', 'stock_min'])
        df_stock_min['stock_min'] = df_stock_min['stock_min'].apply(_convertir_a_numero)
        
        if not df_inv_sin_lotes.empty:
            df_reporte = pd.merge(df_stock_min, df_inv_sin_lotes, on='codigo', how='outer')
            df_reporte['stock_total_calc'] = df_reporte['stock_total_calc'].fillna(0).astype(int)
            df_reporte['stock_min'] = df_reporte['stock_min'].fillna(0).astype(int)
            df_reporte['nombre'] = df_reporte['nombre'].fillna('Sin nombre')
            df_reporte = df_reporte.dropna(subset=['codigo'])
            df_reporte = df_reporte.drop_duplicates(subset=['codigo'])

            def semaforo(fila):
                total = fila['stock_total_calc']
                minimo = fila['stock_min']
                if total <= minimo: return "🔴 Crítico"
                elif total <= 1.5*minimo: return "🟡 Advertencia"
                else: return "🟢 Óptimo"

            df_reporte['Estado'] = df_reporte.apply(semaforo, axis = 1)
            df_reporte = df_reporte.sort_values(by=['Estado', 'stock_total_calc'])

            c_crit, c_warn, c_ok = st.columns(3)
            with c_crit: st.metric("🔴 Estado Crítico", len(df_reporte[df_reporte['Estado'] == "🔴 Crítico"]))
            with c_warn: st.metric("🟡 Advertencia", len(df_reporte[df_reporte['Estado'] == "🟡 Advertencia"]))
            with c_ok: st.metric("🟢 Óptimo", len(df_reporte[df_reporte['Estado'] == "🟢 Óptimo"]))

            busqueda = st.text_input("🔍 Buscar código en reporte:", key="search_stock_min")
            if busqueda:
                df_reporte = df_reporte[df_reporte['codigo'].astype(str).str.contains(busqueda, case=False, na=False)]
            
            st.dataframe(
                df_reporte, 
                use_container_width=True,
                hide_index=True,
                column_config={
                    'codigo': "Código", 'nombre': "Nombre", "stock_min": "Minimo",
                    'stock_total_calc': "Actual", 'Estado': "Estado"
                }
            )
        else:
            st.warning("Sin datos de inventario.")
            
    with tab6:
        st.subheader("⏰ Alertas de Vencimiento")
        
        with st.expander("⚙️ Configuración de Alertas", expanded=True):
            col_v1, col_v2, col_v3 = st.columns(3)
            alerta_critica = col_v1.slider("Días Críticos (🔴)", 0, 60, 3)
            alerta_adv = col_v2.slider("Días Advertencia (🟡)", 0, 90, 7)
            alerta_preventiva = col_v3.slider("Días Preventivos (🟠)", 0, 120, 12)

        hoy = datetime.now().date()
        alertas = []

        for codigo, lotes in inventario.items():
            for lote in lotes:
                fv = lote.get("fecha_vencimiento")
                estado = None
                if fv:
                    try:
                        fv_date = datetime.strptime(fv, "%Y-%m-%d").date()
                        dias_restantes = (fv_date - hoy).days

                        if dias_restantes < 0: estado = 'Vencido ❌'
                        elif dias_restantes <= alerta_critica: estado = 'Alerta Crítica 🔴'
                        elif  dias_restantes <= alerta_adv: estado = 'Alerta Advertencia 🟡'
                        elif dias_restantes <= alerta_preventiva: estado = 'Alerta Preventiva 🟠'

                        if estado:
                            alertas.append({
                                'Estado': estado, 'Fecha': fv, 'Días': dias_restantes,
                                'Nombre': lote['nombre'], 'Cantidad': lote['cantidad'], 'Código': codigo
                            })
                    except: pass

        if alertas:
            df_alertas = pd.DataFrame(alertas).sort_values(by='Días')
            st.dataframe(
                df_alertas, 
                use_container_width=True, 
                hide_index=True,
                column_config={
                    "Días": st.column_config.NumberColumn("Días Restantes", format="%d"),
                    "Fecha": st.column_config.DateColumn("Vencimiento")
                }
            )
        else:
            st.success("✅ No hay productos próximos a vencer según los rangos seleccionados.")
