"""
Presupuesto Maestro - single-file prototype
Cumple gran parte de la especificación: GUI tkinter, persistencia JSON, calculos con Decimal,
validaciones, export CSV, logging. Está pensado como punto de partida; puede refactorizarse
hacia la estructura en paquetes solicitada.

Ejecución: python run.py

Nota: este archivo es un prototipo monolítico para acelerar entrega. Recomiendo separar en
módulos: models.py, validators.py, persistence.py, gui.py y tests/ como en la especificación.

"""
from __future__ import annotations
import json
import uuid
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, getcontext
from dataclasses import dataclass, asdict, field
from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path
import logging
import tempfile
import shutil
import csv

# GUI
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

# Logging
LOG_DIR = Path('logs')
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    filename=LOG_DIR / 'app.log',
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s'
)

# Decimal config
getcontext().prec = 28
TWOPLACES = Decimal('0.01')

DATA_DIR = Path('data')
DATA_DIR.mkdir(exist_ok=True)
DATA_FILE = DATA_DIR / 'products.json'

# --- Validators ---

def to_decimal(value: Any, field_name: str) -> Decimal:
    if value is None or (isinstance(value, str) and value.strip() == ""):
        raise ValueError(f"Campo {field_name} inválido. Ingrese un número válido con punto decimal, ej: 123.45")
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"Campo {field_name} inválido. Ingrese un número válido con punto decimal, ej: 123.45")
    # quantize to 2 decimals
    return d.quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def validate_required(value: Any, field_name: str) -> None:
    if value is None or (isinstance(value, str) and value.strip() == ""):
        raise ValueError(f"El campo {field_name} es obligatorio.")

# --- Models & Calculations ---

@dataclass
class Product:
    id: str
    producto: str
    unidades_vender: Decimal
    costo_unitario: Decimal
    precio_unitario: Decimal
    inventario_inicial: Decimal = Decimal('0')
    inventario_final: Decimal = Decimal('0')
    costo_venta: Optional[Decimal] = None
    material_por_unidad: Decimal = Decimal('0')
    inv_mat_inicial: Decimal = Decimal('0')
    inv_mat_final: Decimal = Decimal('0')
    precio_compra_material: Decimal = Decimal('0')
    horas_por_unidad: Decimal = Decimal('0')
    costo_por_hora: Decimal = Decimal('0')
    costos_fijos: Decimal = Decimal('0')
    costos_variables: Decimal = Decimal('0')
    gastos_fijos: Decimal = Decimal('0')
    gastos_variables_venta: Decimal = Decimal('0')
    costos_administracion: Decimal = Decimal('0')
    precio_venta: Decimal = Decimal('0')
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Product':
        # Convert and validate required fields
        validate_required(data.get('producto'), 'producto')
        validate_required(data.get('unidades_vender'), 'unidades_vender')
        validate_required(data.get('costo_unitario'), 'costo_unitario')
        validate_required(data.get('precio_unitario'), 'precio_unitario')

        def gd(key, default='0'):
            return to_decimal(data.get(key, default), key)

        pid = data.get('id') or str(uuid.uuid4())
        return cls(
            id=pid,
            producto=str(data.get('producto')),
            unidades_vender=gd('unidades_vender'),
            costo_unitario=gd('costo_unitario'),
            precio_unitario=gd('precio_unitario'),
            inventario_inicial=gd('inventario_inicial'),
            inventario_final=gd('inventario_final'),
            costo_venta=(to_decimal(data['costo_venta'], 'costo_venta') if data.get('costo_venta') not in (None, '') else None),
            material_por_unidad=gd('material_por_unidad'),
            inv_mat_inicial=gd('inv_mat_inicial'),
            inv_mat_final=gd('inv_mat_final'),
            precio_compra_material=gd('precio_compra_material'),
            horas_por_unidad=gd('horas_por_unidad'),
            costo_por_hora=gd('costo_por_hora'),
            costos_fijos=gd('costos_fijos'),
            costos_variables=gd('costos_variables'),
            gastos_fijos=gd('gastos_fijos'),
            gastos_variables_venta=gd('gastos_variables_venta'),
            costos_administracion=gd('costos_administracion'),
            precio_venta=gd('precio_venta')
        )

    def to_json_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # Convert Decimal to str for monetary fields
        for k, v in d.items():
            if isinstance(v, Decimal):
                d[k] = format(v, 'f')
        return d


def calculate_all(p: Product) -> Dict[str, Optional[Decimal]]:
    # All calculations with Decimal, quantize at the end
    out: Dict[str, Optional[Decimal]] = {}
    unidades_vender = p.unidades_vender
    precio_unitario = p.precio_unitario
    costo_unitario = p.costo_unitario

    total_ventas = (unidades_vender * precio_unitario).quantize(TWOPLACES)
    out['total_ventas'] = total_ventas

    unidades_producir = (unidades_vender + p.inventario_final - p.inventario_inicial)
    out['presupuesto_produccion'] = unidades_producir.quantize(TWOPLACES)

    material_a_consumir = (unidades_producir * p.material_por_unidad).quantize(TWOPLACES)
    out['material_a_consumir'] = material_a_consumir

    compras_de_materiales = (material_a_consumir + p.inv_mat_final - p.inv_mat_inicial).quantize(TWOPLACES)
    out['compras_de_materiales'] = compras_de_materiales

    costo_MOD_unitario = (p.horas_por_unidad * p.costo_por_hora).quantize(TWOPLACES)
    out['costo_MOD_unitario'] = costo_MOD_unitario

    costo_MOD_total = (costo_MOD_unitario * unidades_producir).quantize(TWOPLACES)
    out['costo_MOD_total'] = costo_MOD_total

    CIF_total = (p.costos_fijos + p.costos_variables).quantize(TWOPLACES)
    out['CIF_total'] = CIF_total

    costo_produccion_total = ((material_a_consumir * p.precio_compra_material) + costo_MOD_total + CIF_total).quantize(TWOPLACES)
    out['costo_produccion_total'] = costo_produccion_total

    costo_produccion_unitario = (costo_produccion_total / unidades_producir).quantize(TWOPLACES) if unidades_producir > 0 else None
    out['costo_produccion_unitario'] = costo_produccion_unitario

    gastos_totales = (p.gastos_fijos + p.gastos_variables_venta + p.costos_administracion).quantize(TWOPLACES)
    out['gastos_totales'] = gastos_totales

    inventario_final_valor = (p.inventario_final * costo_unitario).quantize(TWOPLACES)
    out['inventario_final_valor'] = inventario_final_valor

    # estado_resultados_proyectado = total_ventas - costo_venta - gastos_totales
    costo_venta_val = p.costo_venta if p.costo_venta is not None else (costo_produccion_total)
    estado_resultados_proyectado = (total_ventas - costo_venta_val - gastos_totales).quantize(TWOPLACES)
    out['estado_resultados_proyectado'] = estado_resultados_proyectado

    # costo_variable_unitario = costos_variables / unidades_producir
    if unidades_producir > 0:
        costo_variable_unitario = (p.costos_variables / unidades_producir).quantize(TWOPLACES)
        try:
            punto_equilibrio_unidades = (p.costos_fijos / (precio_unitario - costo_variable_unitario)).quantize(TWOPLACES)
        except (InvalidOperation, ZeroDivisionError):
            punto_equilibrio_unidades = None
    else:
        costo_variable_unitario = None
        punto_equilibrio_unidades = None

    out['costo_variable_unitario'] = costo_variable_unitario
    out['punto_equilibrio_unidades'] = punto_equilibrio_unidades

    utilidad_neta = (total_ventas - costo_venta_val - gastos_totales).quantize(TWOPLACES)
    out['utilidad_neta'] = utilidad_neta

    return out

# --- Persistence ---

def _ensure_datafile():
    if not DATA_FILE.exists():
        DATA_FILE.write_text(json.dumps({"products": []}, indent=2, ensure_ascii=False))


def save_product(product_dict: Dict[str, Any], path: Path = DATA_FILE) -> None:
    _ensure_datafile()
    tmp = Path(tempfile.mkstemp(prefix='prod_', suffix='.tmp')[1])
    try:
        with open(path, 'r', encoding='utf8') as f:
            content = json.load(f)
    except Exception:
        content = {"products": []}
    # replace or append
    prods: List[Dict[str, Any]] = content.get('products', [])
    found = False
    for i, pr in enumerate(prods):
        if pr.get('id') == product_dict.get('id'):
            prods[i] = product_dict
            found = True
            break
    if not found:
        prods.append(product_dict)
    content['products'] = prods
    # atomic write
    with open(tmp, 'w', encoding='utf8') as f:
        json.dump(content, f, indent=2, ensure_ascii=False)
    shutil.move(str(tmp), str(path))
    logging.info(f"Producto {product_dict.get('producto')} guardado (id={product_dict.get('id')}).")


def load_all_products(path: Path = DATA_FILE) -> List[Dict[str, Any]]:
    _ensure_datafile()
    try:
        with open(path, 'r', encoding='utf8') as f:
            content = json.load(f)
        return content.get('products', [])
    except Exception as e:
        logging.error(f"No se pudo cargar products.json: {e}")
        return []


def update_product(product_id: str, new_dict: Dict[str, Any], path: Path = DATA_FILE) -> None:
    save_product(new_dict, path)

# --- Reports / Exports ---

def export_products_csv(products: List[Dict[str, Any]], filepath: Path) -> None:
    # Flatten and write
    if not products:
        return
    keys = list(products[0].keys())
    with open(filepath, 'w', newline='', encoding='utf8') as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        for p in products:
            writer.writerow(p)
    logging.info(f"Export CSV: {filepath}")

# --- GUI ---

class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title('PRESUPUESTO MAESTRO')
        root.geometry('900x600')
        self.style = ttk.Style(root)
        # Main frame
        main = ttk.Frame(root, padding=12)
        main.pack(fill='both', expand=True)

        title = ttk.Label(main, text='PRESUPUESTO MAESTRO', anchor='center', font=('Helvetica', 16, 'bold'))
        title.pack(pady=6)

        btn_frame = ttk.Frame(main)
        btn_frame.pack(pady=8)

        ttk.Button(btn_frame, text='Agregar un nuevo producto', command=self.open_add).grid(row=0, column=0, padx=6, pady=6)
        ttk.Button(btn_frame, text='Ver productos agregados', command=self.open_view).grid(row=0, column=1, padx=6, pady=6)
        ttk.Button(btn_frame, text='Editar productos', command=self.open_edit).grid(row=0, column=2, padx=6, pady=6)
        ttk.Button(btn_frame, text='Salir', command=self.on_exit).grid(row=0, column=3, padx=6, pady=6)

    def open_add(self):
        ProductForm(self.root, mode='add')

    def open_view(self):
        ProductList(self.root, editable=False)

    def open_edit(self):
        ProductList(self.root, editable=True)

    def on_exit(self):
        self.root.quit()


# Form for add/edit
class ProductForm:
    FIELDS = [
        ('producto', 'Producto', ''),
        ('unidades_vender', 'Unidades a vender', '1000'),
        ('costo_unitario', 'Costo unitario', '0.00'),
        ('precio_unitario', 'Precio unitario', '0.00'),
        ('inventario_inicial', 'Inventario inicial', '0'),
        ('inventario_final', 'Inventario final', '0'),
        ('costo_venta', 'Costo de venta (opcional)', ''),
        ('material_por_unidad', 'Material por unidad', '0.00'),
        ('inv_mat_inicial', 'Inventario material inicial', '0'),
        ('inv_mat_final', 'Inventario material final', '0'),
        ('precio_compra_material', 'Precio compra material', '0.00'),
        ('horas_por_unidad', 'Horas por unidad', '0.00'),
        ('costo_por_hora', 'Costo por hora', '0.00'),
        ('costos_fijos', 'Costos fijos', '0.00'),
        ('costos_variables', 'Costos variables', '0.00'),
        ('gastos_fijos', 'Gastos fijos', '0.00'),
        ('gastos_variables_venta', 'Gastos variables de venta', '0.00'),
        ('costos_administracion', 'Costos administración', '0.00'),
        ('precio_venta', 'Precio venta', '0.00')
    ]

    def __init__(self, parent, mode='add', seed: Optional[Dict[str, Any]] = None):
        self.top = tk.Toplevel(parent)
        self.top.title('Agregar/Editar Producto')
        self.mode = mode
        self.seed = seed or {}
        self.entries: Dict[str, tk.Entry] = {}
        self.error_labels: Dict[str, ttk.Label] = {}
        frm = ttk.Frame(self.top, padding=12)
        frm.pack(fill='both', expand=True)

        left = ttk.Frame(frm)
        left.grid(row=0, column=0, sticky='n')
        right = ttk.Frame(frm)
        right.grid(row=0, column=1, sticky='n')

        for i, (key, label, example) in enumerate(self.FIELDS):
            parent_col = left if i < 10 else right
            r = i if i < 10 else i - 10
            ttk.Label(parent_col, text=label).grid(row=r*2, column=0, sticky='w')
            e = ttk.Entry(parent_col)
            e.grid(row=r*2+1, column=0, sticky='we', padx=2, pady=2)
            val = self.seed.get(key, example)
            e.insert(0, str(val))
            e.bind('<FocusOut>', lambda ev, k=key: self._validate_field(k))
            self.entries[key] = e
            err = ttk.Label(parent_col, text='', foreground='red')
            err.grid(row=r*2+2, column=0, sticky='w')
            self.error_labels[key] = err

        btns = ttk.Frame(frm)
        btns.grid(row=1, column=0, columnspan=2, pady=8)
        ttk.Button(btns, text='Guardar', command=self.on_save).grid(row=0, column=0, padx=6)
        ttk.Button(btns, text='Limpiar', command=self.on_clear).grid(row=0, column=1, padx=6)
        ttk.Button(btns, text='Cancelar', command=self.top.destroy).grid(row=0, column=2, padx=6)

    def _validate_field(self, key: str):
        v = self.entries[key].get()
        # Basic: if field is numeric attempt to_decimal
        numeric_fields = {f[0] for f in self.FIELDS if f[0] != 'producto'}
        if key in numeric_fields:
            if v.strip() == '':
                # optional
                self.error_labels[key].config(text='')
                return True
            try:
                to_decimal(v, key)
                self.error_labels[key].config(text='')
                return True
            except ValueError as e:
                self.error_labels[key].config(text=str(e))
                return False
        else:
            if key == 'producto' and v.strip() == '':
                self.error_labels[key].config(text=f'El campo {key} es obligatorio.')
                return False
            self.error_labels[key].config(text='')
            return True

    def on_clear(self):
        for e in self.entries.values():
            e.delete(0, 'end')

    def on_save(self):
        # Validate all
        try:
            data = {}
            for key in [f[0] for f in self.FIELDS]:
                val = self.entries[key].get().strip()
                if key == 'producto':
                    validate_required(val, 'producto')
                    data['producto'] = val
                else:
                    if val == '':
                        data[key] = ''
                    else:
                        data[key] = val
            # build product
            if self.seed.get('id'):
                data['id'] = self.seed['id']
            p = Product.from_dict(data)
        except ValueError as e:
            messagebox.showerror('Error', str(e))
            return

        results = calculate_all(p)
        # Show summary modal
        SummaryModal(self.top, p, results, on_confirm=lambda: self._confirm_save(p))

    def _confirm_save(self, p: Product):
        if messagebox.askyesno('Confirmar', '¿Guardar producto y resultados?'):
            save_product(p.to_json_dict())
            messagebox.showinfo('Producto guardado', 'Producto guardado correctamente.')
            self.top.destroy()


class SummaryModal:
    def __init__(self, parent, product: Product, results: Dict[str, Optional[Decimal]], on_confirm):
        top = tk.Toplevel(parent)
        top.title('Resumen de Cálculos')
        frm = ttk.Frame(top, padding=8)
        frm.pack(fill='both', expand=True)
        ttk.Label(frm, text=f"Producto: {product.producto}", font=('Helvetica', 12, 'bold')).pack()
        tree = ttk.Treeview(frm, columns=('valor',), show='headings')
        tree.heading('valor', text='Valor')
        tree.pack(fill='both', expand=True)
        for k, v in results.items():
            tree.insert('', 'end', values=(f"{k}: {v}" ,))
        btns = ttk.Frame(frm)
        btns.pack(pady=6)
        ttk.Button(btns, text='Aceptar', command=lambda: (on_confirm(), top.destroy())).grid(row=0, column=0, padx=6)
        ttk.Button(btns, text='Cerrar', command=top.destroy).grid(row=0, column=1, padx=6)


class ProductList:
    def __init__(self, parent, editable: bool = False):
        top = tk.Toplevel(parent)
        top.title('Productos')
        frm = ttk.Frame(top, padding=8)
        frm.pack(fill='both', expand=True)
        cols = ('id', 'producto', 'unidades_vender', 'precio_unitario', 'total_ventas', 'created_at')
        self.tree = ttk.Treeview(frm, columns=cols, show='headings')
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=120)
        self.tree.pack(side='left', fill='both', expand=True)
        scrollbar = ttk.Scrollbar(frm, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side='left', fill='y')

        right = ttk.Frame(frm, padding=8)
        right.pack(side='right', fill='y')
        ttk.Button(right, text='Exportar seleccionado (CSV)', command=self.export_selected).pack(pady=4)
        ttk.Button(right, text='Exportar todo (CSV)', command=self.export_all).pack(pady=4)
        ttk.Button(right, text='Volver', command=top.destroy).pack(pady=4)
        if editable:
            ttk.Button(right, text='Editar selección', command=self.edit_selected).pack(pady=4)
        self.load()
        self.tree.bind('<Double-1>', lambda e: self.show_detail())

    def load(self):
        for r in self.tree.get_children():
            self.tree.delete(r)
        products = load_all_products()
        for p in products:
            try:
                unidades = p.get('unidades_vender', '')
                pu = p.get('precio_unitario', '')
                total = ''
                if unidades != '' and pu != '':
                    total = str(Decimal(str(unidades)) * Decimal(str(pu)))
            except Exception:
                total = ''
            self.tree.insert('', 'end', values=(p.get('id'), p.get('producto'), p.get('unidades_vender'), p.get('precio_unitario'), total, p.get('created_at')))

    def get_selected_product(self) -> Optional[Dict[str, Any]]:
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning('Atención', 'Seleccione un producto')
            return None
        row = self.tree.item(sel[0])['values']
        pid = row[0]
        products = load_all_products()
        for p in products:
            if p.get('id') == pid:
                return p
        return None

    def show_detail(self):
        p = self.get_selected_product()
        if not p:
            return
        prod = Product.from_dict(p)
        results = calculate_all(prod)
        SummaryModal(self.tree, prod, results, on_confirm=lambda: None)

    def export_selected(self):
        p = self.get_selected_product()
        if not p:
            return
        path = Path(simpledialog.askstring('Exportar', 'Ingrese ruta del CSV (ej: producto.csv)'))
        if not path:
            return
        export_products_csv([p], path)
        messagebox.showinfo('Exportado', f'Exportado a {path}')

    def export_all(self):
        path_str = simpledialog.askstring('Exportar', 'Ingrese ruta del CSV para todo (ej: productos.csv)')
        if not path_str:
            return
        path = Path(path_str)
        products = load_all_products()
        export_products_csv(products, path)
        messagebox.showinfo('Exportado', f'Exportado a {path}')

    def edit_selected(self):
        p = self.get_selected_product()
        if not p:
            return
        ProductForm(self.tree, mode='edit', seed=p)

# --- Main entry ---

def main():
    root = tk.Tk()
    app = App(root)
    root.mainloop()

if __name__ == '__main__':
    main()
