"""
Mock Log Forge - GUI
Run:  python app.py      (only needs standard Python 3.9+ with tkinter, no pip installs)
"""
import copy
import json
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

from engine import (TYPES, GEN_HELP, GEN_SUGGESTIONS, LogGenerator, load_schemas, save_schema,
                    parse_learn_paste, parse_pools, pools_to_text)

BASE = os.path.dirname(os.path.abspath(__file__))
SCHEMA_DIR = os.path.join(BASE, "schemas")
DEFAULT_PROJECT = os.path.join(BASE, "project.json")

C = dict(bg="#16171d", panel="#1f2129", panel2="#262833", fg="#e8e8ef", muted="#8e94a8",
         accent="#7c5cff", accent_h="#6747f5", green="#22c55e", amber="#f59e0b", line="#343747",
         user="#7c5cff", device="#0ea5e9", net="#22c55e", subnet="#f59e0b")
FONT = ("Segoe UI", 10)
MONO = ("Consolas", 10)

MODES = ["fixed", "random", "round-robin"]


# ====================================================================== styling
def apply_style(root):
    s = ttk.Style(root)
    s.theme_use("clam")
    s.configure(".", background=C["bg"], foreground=C["fg"], fieldbackground=C["panel"],
                bordercolor=C["line"], lightcolor=C["line"], darkcolor=C["line"], font=FONT)
    s.configure("TFrame", background=C["bg"])
    s.configure("Card.TFrame", background=C["panel"])
    s.configure("TLabel", background=C["bg"], foreground=C["fg"])
    s.configure("Card.TLabel", background=C["panel"])
    s.configure("Muted.TLabel", foreground=C["muted"])
    s.configure("Title.TLabel", font=("Segoe UI", 15, "bold"))
    s.configure("TNotebook", background=C["bg"], borderwidth=0)
    s.configure("TNotebook.Tab", background=C["panel"], foreground=C["muted"], padding=(16, 7), borderwidth=0)
    s.map("TNotebook.Tab", background=[("selected", C["accent"])], foreground=[("selected", "white")])
    s.configure("Treeview", background=C["panel"], fieldbackground=C["panel"], foreground=C["fg"],
                rowheight=25, borderwidth=0)
    s.configure("Treeview.Heading", background=C["panel2"], foreground=C["muted"], relief="flat")
    s.map("Treeview", background=[("selected", C["accent"])], foreground=[("selected", "white")])
    s.configure("TButton", background=C["panel2"], foreground=C["fg"], padding=(10, 5), borderwidth=0)
    s.map("TButton", background=[("active", C["line"])])
    s.configure("Accent.TButton", background=C["accent"], foreground="white", font=("Segoe UI", 10, "bold"))
    s.map("Accent.TButton", background=[("active", C["accent_h"])])
    s.configure("TEntry", fieldbackground=C["panel"], foreground=C["fg"], insertcolor=C["fg"])
    s.configure("TCombobox", fieldbackground=C["panel"], foreground=C["fg"], background=C["panel2"],
                arrowcolor=C["fg"], selectbackground=C["panel"], selectforeground=C["fg"])
    s.map("TCombobox", fieldbackground=[("readonly", C["panel"])], foreground=[("readonly", C["fg"])])
    s.configure("TCheckbutton", background=C["bg"], foreground=C["fg"])
    s.map("TCheckbutton", background=[("active", C["bg"])])
    s.configure("TLabelframe", background=C["bg"], bordercolor=C["line"])
    s.configure("TLabelframe.Label", background=C["bg"], foreground=C["muted"])
    s.configure("Vertical.TScrollbar", background=C["panel2"], troughcolor=C["panel"], arrowcolor=C["fg"])
    root.option_add("*TCombobox*Listbox.background", C["panel"])
    root.option_add("*TCombobox*Listbox.foreground", C["fg"])
    root.option_add("*TCombobox*Listbox.selectBackground", C["accent"])


def make_text(parent, height=10, mono=True):
    t = tk.Text(parent, height=height, bg=C["panel"], fg=C["fg"], insertbackground=C["fg"],
                relief="flat", font=MONO if mono else FONT, wrap="none", padx=8, pady=6,
                selectbackground=C["accent"], highlightthickness=1, highlightbackground=C["line"])
    return t


def make_tree(parent, cols, widths, height=10):
    frame = ttk.Frame(parent)
    tree = ttk.Treeview(frame, columns=cols, show="headings", height=height, selectmode="browse")
    for c, w in zip(cols, widths):
        tree.heading(c, text=c)
        tree.column(c, width=w, anchor="w", stretch=True)
    sb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=sb.set)
    tree.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")
    return frame, tree


def kv_to_text(d):
    return "\n".join(f"{k} = {json.dumps(v) if not isinstance(v, str) else v}" for k, v in d.items())


def text_to_kv(text):
    out = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip()
        if not k:
            continue
        try:
            out[k] = json.loads(v) if v and v[0] in "[{0123456789-tfn" and v not in ("-",) else v
        except ValueError:
            out[k] = v
    return out


class Dialog(tk.Toplevel):
    """Small modal dialog base."""

    def __init__(self, master, title):
        super().__init__(master)
        self.title(title)
        self.configure(bg=C["bg"])
        self.transient(master)
        self.result = None
        self.body = ttk.Frame(self, padding=14)
        self.body.pack(fill="both", expand=True)
        bar = ttk.Frame(self, padding=(14, 0, 14, 14))
        bar.pack(fill="x")
        ttk.Button(bar, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(bar, text="OK", style="Accent.TButton", command=self._ok).pack(side="right", padx=6)

    def run(self):
        self.update_idletasks()
        try:
            self.wait_visibility()
            self.grab_set()
        except tk.TclError:
            pass
        self.wait_window()
        return self.result

    def _ok(self):
        try:
            self.result = self.collect()
        except Exception as e:  # noqa
            messagebox.showerror("Invalid input", str(e), parent=self)
            return
        self.destroy()

    def collect(self):
        return None


# ====================================================================== dialogs
# kind -> (separator, default example value, value suggestions, explanation)
GEN_KINDS = {
    "(null)":    (None, "", [], "No value. The column will be null."),
    "timestamp": (None, "", [], "Ordered log time (same value in every timestamp column of the row)."),
    "ref":       (":", "TimeGenerated", ["TimeGenerated", "Timestamp"], "Copy another column of the same row.  e.g. ref:TimeGenerated"),
    "user":      (".", "upn", ["upn", "name", "sam", "domain", "sid", "objectId", "isLocalAdmin"], "Attribute of the row's user (Entities tab).  e.g. user.upn"),
    "device":    (".", "name", ["name", "fqdn", "ip", "mac", "os", "mdeId", "public_ip", "subnet"], "Attribute of the user's device (follows Relations).  e.g. device.ip"),
    "const":     (":", "example", [], "Always the same value.  e.g. const:Palo Alto Networks   const:443"),
    "choice":    (":", "allow*9|deny*1", [], "Random pick from a list, separated by |.  *N = weight.  e.g. choice:TCP*8|UDP*2"),
    "int":       (":", "1-100", [], "Random whole number in a range.  e.g. int:49152-65535"),
    "pool":      (":", "legit_ips", [], "Random value from a pool (Entities tab -> Pools).  e.g. pool:malicious_ips"),
    "ip":        (":", "public", ["public", "private"], "Random IP address.  e.g. ip:public"),
    "guid":      (None, "", [], "Random GUID."),
    "mac":       (None, "", [], "Random MAC address."),
    "hex":       (":", "64", ["32", "40", "64"], "Random hex string. 64 = SHA256, 40 = SHA1, 32 = MD5.  e.g. hex:64"),
    "template":  (":", "{user.domain}\\{user.sam}", [], "Text with placeholders {user.x} {device.x} {row.Column} {pool.x} {ts}"),
}


def split_gen(g):
    g = (g or "").strip()
    if not g:
        return "(null)", ""
    if g in ("timestamp", "guid", "mac"):
        return g, ""
    for k in ("user", "device"):
        if g.startswith(k + "."):
            return k, g[len(k) + 1:]
    head, sep, rest = g.partition(":")
    if sep and head in GEN_KINDS:
        return head, rest
    return "const", g  # unknown text -> treat as constant


def join_gen(kind, value):
    sep = GEN_KINDS[kind][0]
    if kind == "(null)":
        return ""
    return kind if sep is None else f"{kind}{sep}{value.strip()}"


class ColumnDialog(Dialog):
    def __init__(self, master, col=None):
        super().__init__(master, "Column")
        col = col or {"name": "", "type": "string", "gen": ""}
        b = self.body
        b.columnconfigure(1, weight=1)

        ttk.Label(b, text="Name").grid(row=0, column=0, sticky="w", pady=3)
        self.name = ttk.Entry(b, width=50)
        self.name.insert(0, col["name"])
        self.name.grid(row=0, column=1, columnspan=2, sticky="we")

        ttk.Label(b, text="Type").grid(row=1, column=0, sticky="w", pady=3)
        self.typ = ttk.Combobox(b, values=TYPES, state="readonly", width=20)
        self.typ.set(col.get("type", "string"))
        self.typ.grid(row=1, column=1, sticky="w")

        ttk.Label(b, text="Generator").grid(row=2, column=0, sticky="w", pady=(10, 3))
        kind, value = split_gen(col.get("gen", ""))
        self.kind = ttk.Combobox(b, values=list(GEN_KINDS), state="readonly", width=12)
        self.kind.set(kind)
        self.kind.grid(row=2, column=1, sticky="w", pady=(10, 3))
        self.value = ttk.Combobox(b, width=48)
        self.value.set(value)
        self.value.grid(row=2, column=2, sticky="we", padx=(6, 0), pady=(10, 3))

        self.help = ttk.Label(b, text="", style="Muted.TLabel", wraplength=560, justify="left")
        self.help.grid(row=3, column=1, columnspan=2, sticky="w", pady=(2, 0))
        self.result_lbl = ttk.Label(b, text="", font=MONO)
        self.result_lbl.grid(row=4, column=1, columnspan=2, sticky="w", pady=(8, 0))

        self.kind.bind("<<ComboboxSelected>>", lambda e: self._on_kind(changed=True))
        self.value.bind("<KeyRelease>", lambda e: self._preview())
        self.value.bind("<<ComboboxSelected>>", lambda e: self._preview())
        self._on_kind(changed=False)
        self.name.focus_set()

    def _pool_names(self):
        try:
            return list(self.master.project.get("pools", {}))
        except AttributeError:
            return []

    def _on_kind(self, changed):
        k = self.kind.get()
        sep, example, sugg, text = GEN_KINDS[k]
        if k == "pool":
            sugg = self._pool_names() or sugg
        self.value.configure(values=sugg, state="disabled" if sep is None else "normal")
        if changed:
            self.value.set("" if sep is None else example)
        self.help.config(text=text)
        self._preview()

    def _preview(self):
        g = join_gen(self.kind.get(), self.value.get())
        self.result_lbl.config(text=f"Result:  {g or '∅ (null)'}")

    def collect(self):
        n = self.name.get().strip()
        if not n:
            raise ValueError("Column name is required")
        k = self.kind.get()
        if GEN_KINDS[k][0] is not None and not self.value.get().strip():
            raise ValueError(f"'{k}' needs a value, e.g. {GEN_KINDS[k][1]}")
        return {"name": n, "type": self.typ.get(), "gen": join_gen(k, self.value.get())}


class EntityDialog(Dialog):
    def __init__(self, master, kind, ent):
        super().__init__(master, f"{kind} entity")
        ttk.Label(self.body, text="One attribute per line:  key = value   ('id' is required and must be unique)",
                  style="Muted.TLabel").pack(anchor="w")
        self.txt = make_text(self.body, height=14)
        self.txt.configure(width=70)
        self.txt.pack(fill="both", expand=True, pady=6)
        self.txt.insert("1.0", kv_to_text(ent))

    def collect(self):
        d = text_to_kv(self.txt.get("1.0", "end"))
        if not str(d.get("id", "")).strip():
            raise ValueError("'id' is required")
        d["id"] = str(d["id"])
        return d


class BatchDialog(Dialog):
    def __init__(self, master, batch):
        super().__init__(master, "Batch")
        b = self.body
        ttk.Label(b, text="Name").grid(row=0, column=0, sticky="w", pady=3)
        self.name = ttk.Entry(b, width=40)
        self.name.insert(0, batch.get("name", ""))
        self.name.grid(row=0, column=1, sticky="we")
        ttk.Label(b, text="Count").grid(row=1, column=0, sticky="w", pady=3)
        self.count = ttk.Entry(b, width=10)
        self.count.insert(0, str(batch.get("count", 10)))
        self.count.grid(row=1, column=1, sticky="w")
        ttk.Label(b, text="Users (ids, comma)").grid(row=2, column=0, sticky="w", pady=3)
        self.users = ttk.Entry(b, width=40)
        self.users.insert(0, ", ".join(batch.get("users", [])))
        self.users.grid(row=2, column=1, sticky="we")
        ttk.Label(b, text="empty = all users.  'user1, user1, user2' = exactly that order, repeated.",
                  style="Muted.TLabel").grid(row=3, column=1, sticky="w")
        ttk.Label(b, text="Overrides  (Column = generator)").grid(row=4, column=0, columnspan=2, sticky="w",
                                                                  pady=(10, 2))
        self.ov = make_text(b, height=9)
        self.ov.configure(width=70)
        self.ov.grid(row=5, column=0, columnspan=2, sticky="nsew")
        self.ov.insert("1.0", "\n".join(f"{k} = {v}" for k, v in batch.get("overrides", {}).items()))

    def collect(self):
        ov = {}
        for line in self.ov.get("1.0", "end").splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                if k.strip():
                    ov[k.strip()] = v.strip()
        return {"name": self.name.get().strip() or "batch", "count": int(self.count.get()),
                "users": [u.strip() for u in self.users.get().split(",") if u.strip()], "overrides": ov}


class RelationDialog(Dialog):
    def __init__(self, master, uid, rule, device_ids):
        super().__init__(master, f"Devices for {uid}")
        ttk.Label(self.body, text="Mode").grid(row=0, column=0, sticky="w")
        self.mode = ttk.Combobox(self.body, values=MODES + ["(no rule - any device)"], state="readonly", width=28)
        self.mode.set(rule.get("mode", "fixed") if rule else "(no rule - any device)")
        self.mode.grid(row=0, column=1, sticky="w", pady=4)
        ttk.Label(self.body, text="fixed = always the FIRST selected device\nrandom = random from selected\n"
                                  "round-robin = cycle through selected", style="Muted.TLabel",
                  justify="left").grid(row=1, column=1, sticky="w")
        ttk.Label(self.body, text="Devices").grid(row=2, column=0, sticky="nw", pady=6)
        self.lb = tk.Listbox(self.body, selectmode="multiple", height=10, bg=C["panel"], fg=C["fg"],
                             selectbackground=C["accent"], relief="flat", exportselection=False)
        self.ids = device_ids
        chosen = (rule or {}).get("devices", [])
        # keep chosen order first so "fixed" picks the intended first device
        ordered = chosen + [d for d in device_ids if d not in chosen]
        self.ids = [d for d in ordered if d in device_ids]
        for i, d in enumerate(self.ids):
            self.lb.insert("end", d)
            if d in chosen:
                self.lb.selection_set(i)
        self.lb.grid(row=2, column=1, sticky="we", pady=6)

    def collect(self):
        m = self.mode.get()
        if m not in MODES:
            return {"_delete": True}
        devs = [self.ids[i] for i in self.lb.curselection()]
        if not devs:
            raise ValueError("Select at least one device (or choose 'no rule')")
        return {"mode": m, "devices": devs}


# ====================================================================== main app
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Mock Log Forge")
        self.geometry("1280x800")
        self.minsize(1050, 650)
        self.configure(bg=C["bg"])
        apply_style(self)

        self.schemas = load_schemas(SCHEMA_DIR)
        self.project_path = DEFAULT_PROJECT
        self.project = self._load_project(DEFAULT_PROJECT)
        self.rows = []

        self._header()
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.tab_gen = ttk.Frame(nb, padding=10)
        self.tab_schema = ttk.Frame(nb, padding=10)
        self.tab_ent = ttk.Frame(nb, padding=10)
        self.tab_rel = ttk.Frame(nb, padding=10)
        nb.add(self.tab_gen, text="  Generate  ")
        nb.add(self.tab_schema, text="  Schema  ")
        nb.add(self.tab_ent, text="  Entities  ")
        nb.add(self.tab_rel, text="  Relations  ")
        nb.bind("<<NotebookTabChanged>>", lambda e: self.draw_graph())

        self._build_generate()
        self._build_schema()
        self._build_entities()
        self._build_relations()
        self.load_into_ui()

    # ------------------------------------------------------------------ project I/O
    @staticmethod
    def _load_project(path):
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        return {"table": "", "start_time": "", "interval_min": 10, "interval_max": 120, "user_pick": "random",
                "seed": "", "shuffle": True, "drop_nulls": False,
                "entities": {"users": [], "devices": []}, "relations": {}, "pools": {},
                "batches": [{"name": "default", "count": 20, "users": [], "overrides": {}}]}

    def _header(self):
        h = ttk.Frame(self, padding=(14, 12))
        h.pack(fill="x")
        ttk.Label(h, text="⚡ Mock Log Forge", style="Title.TLabel").pack(side="left")
        self.proj_lbl = ttk.Label(h, text="", style="Muted.TLabel")
        self.proj_lbl.pack(side="left", padx=14)
        ttk.Button(h, text="Save project", command=self.save_project).pack(side="right")
        ttk.Button(h, text="Save as…", command=lambda: self.save_project(ask=True)).pack(side="right", padx=4)
        ttk.Button(h, text="Open project…", command=self.open_project).pack(side="right")
        self.table_var = tk.StringVar()
        self.table_cb = ttk.Combobox(h, textvariable=self.table_var, state="readonly", width=28)
        self.table_cb.pack(side="right", padx=(4, 18))
        self.table_cb.bind("<<ComboboxSelected>>", lambda e: self.on_table_change())
        ttk.Label(h, text="Table:").pack(side="right")

    def load_into_ui(self):
        p = self.project
        self.table_cb["values"] = sorted(self.schemas)
        t = p.get("table") if p.get("table") in self.schemas else (sorted(self.schemas) or [""])[0]
        self.table_var.set(t)
        for var, key in ((self.v_start, "start_time"), (self.v_imin, "interval_min"),
                         (self.v_imax, "interval_max"), (self.v_seed, "seed")):
            var.set(str(p.get(key, "")))
        self.v_pick.set(p.get("user_pick", "random"))
        self.v_shuffle.set(bool(p.get("shuffle", True)))
        self.v_dropnull.set(bool(p.get("drop_nulls", False)))
        self.pools_txt.delete("1.0", "end")
        self.pools_txt.insert("1.0", pools_to_text(p.get("pools", {})))
        self.proj_lbl.config(text=os.path.basename(self.project_path))
        self.refresh_batches()
        self.refresh_entities()
        self.refresh_relations()
        self.on_table_change()

    def sync_from_ui(self):
        p = self.project
        p["table"] = self.table_var.get()
        p["start_time"] = self.v_start.get().strip()
        p["interval_min"] = float(self.v_imin.get() or 0)
        p["interval_max"] = float(self.v_imax.get() or 0)
        p["seed"] = self.v_seed.get().strip()
        p["user_pick"] = self.v_pick.get()
        p["shuffle"] = self.v_shuffle.get()
        p["drop_nulls"] = self.v_dropnull.get()
        p["pools"] = parse_pools(self.pools_txt.get("1.0", "end"))

    def save_project(self, ask=False):
        try:
            self.sync_from_ui()
        except ValueError as e:
            messagebox.showerror("Invalid settings", str(e))
            return
        if ask:
            path = filedialog.asksaveasfilename(defaultextension=".json", initialdir=BASE,
                                                filetypes=[("Project", "*.json")])
            if not path:
                return
            self.project_path = path
        with open(self.project_path, "w", encoding="utf-8") as fh:
            json.dump(self.project, fh, indent=2, ensure_ascii=False)
        self.proj_lbl.config(text=os.path.basename(self.project_path) + "  ✓ saved")

    def open_project(self):
        path = filedialog.askopenfilename(initialdir=BASE, filetypes=[("Project", "*.json")])
        if path:
            self.project_path = path
            self.project = self._load_project(path)
            self.load_into_ui()

    def schema(self):
        return self.schemas.get(self.table_var.get())

    def on_table_change(self):
        self.project["table"] = self.table_var.get()
        self.refresh_columns()
        self.draw_graph()

    # ================================================================== GENERATE tab
    def _build_generate(self):
        f = self.tab_gen
        left = ttk.Frame(f)
        left.pack(side="left", fill="y", padx=(0, 12))
        right = ttk.Frame(f)
        right.pack(side="left", fill="both", expand=True)

        box = ttk.LabelFrame(left, text=" Timeline & picking ", padding=10)
        box.pack(fill="x")
        self.v_start, self.v_imin, self.v_imax = tk.StringVar(), tk.StringVar(), tk.StringVar()
        self.v_seed, self.v_pick = tk.StringVar(), tk.StringVar()
        self.v_shuffle, self.v_dropnull = tk.BooleanVar(), tk.BooleanVar()
        rows = [("Start time (UTC ISO)", ttk.Entry(box, textvariable=self.v_start, width=26)),
                ("Gap min (sec)", ttk.Entry(box, textvariable=self.v_imin, width=10)),
                ("Gap max (sec)", ttk.Entry(box, textvariable=self.v_imax, width=10)),
                ("User picking", ttk.Combobox(box, textvariable=self.v_pick, values=["random", "round-robin"],
                                              state="readonly", width=14)),
                ("Seed (optional)", ttk.Entry(box, textvariable=self.v_seed, width=10))]
        for i, (lbl, w) in enumerate(rows):
            ttk.Label(box, text=lbl).grid(row=i, column=0, sticky="w", pady=3)
            w.grid(row=i, column=1, sticky="w", padx=(8, 0))
        ttk.Checkbutton(box, text="Mix batches together (shuffle)", variable=self.v_shuffle).grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Checkbutton(box, text="Drop null/empty columns", variable=self.v_dropnull).grid(
            row=6, column=0, columnspan=2, sticky="w")
        ttk.Label(box, text="Same seed = same output every time.", style="Muted.TLabel").grid(
            row=7, column=0, columnspan=2, sticky="w", pady=(6, 0))

        bb = ttk.LabelFrame(left, text=" Batches (e.g. legit + malicious) ", padding=10)
        bb.pack(fill="both", expand=True, pady=10)
        fr, self.batch_tree = make_tree(bb, ("Name", "Count", "Users", "Overrides"), (90, 50, 110, 70), 8)
        fr.pack(fill="both", expand=True)
        self.batch_tree.bind("<Double-1>", lambda e: self.edit_batch())
        btns = ttk.Frame(bb)
        btns.pack(fill="x", pady=(6, 0))
        ttk.Button(btns, text="+ Add", command=lambda: self.edit_batch(new=True)).pack(side="left")
        ttk.Button(btns, text="Edit", command=self.edit_batch).pack(side="left", padx=4)
        ttk.Button(btns, text="Delete", command=self.delete_batch).pack(side="left")

        act = ttk.Frame(left)
        act.pack(fill="x")
        ttk.Button(act, text="▶  Generate", style="Accent.TButton", command=self.generate).pack(fill="x")
        ttk.Button(act, text="💾  Save .json", command=self.save_json).pack(fill="x", pady=(6, 0))

        self.status = ttk.Label(right, text="Pick a table, then Generate.", style="Muted.TLabel")
        self.status.pack(anchor="w")
        self.preview = make_text(right, height=30)
        self.preview.pack(fill="both", expand=True, pady=(6, 0))

    def refresh_batches(self):
        self.batch_tree.delete(*self.batch_tree.get_children())
        for i, b in enumerate(self.project.get("batches", [])):
            self.batch_tree.insert("", "end", iid=str(i), values=(
                b.get("name"), b.get("count"), ", ".join(b.get("users", [])) or "(all)",
                len(b.get("overrides", {}))))

    def edit_batch(self, new=False):
        batches = self.project.setdefault("batches", [])
        sel = self.batch_tree.selection()
        if not new and not sel:
            return
        idx = None if new else int(sel[0])
        cur = {"name": "batch", "count": 5, "users": [], "overrides": {}} if new else batches[idx]
        res = BatchDialog(self, copy.deepcopy(cur)).run()
        if res:
            if new:
                batches.append(res)
            else:
                batches[idx] = res
            self.refresh_batches()

    def delete_batch(self):
        sel = self.batch_tree.selection()
        if sel:
            del self.project["batches"][int(sel[0])]
            self.refresh_batches()

    def generate(self):
        sch = self.schema()
        if not sch:
            messagebox.showwarning("No table", "Select a table first.")
            return
        try:
            self.sync_from_ui()
            self.rows = LogGenerator(self.project, sch).generate()
        except Exception as e:  # noqa
            messagebox.showerror("Generation failed", f"{type(e).__name__}: {e}")
            return
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", json.dumps(self.rows, indent=2, ensure_ascii=False))
        span = ""
        if self.rows:
            tcol = next((c["name"] for c in sch["columns"] if c.get("gen") == "timestamp"), None)
            if tcol:
                span = f"   |   {self.rows[0].get(tcol)}  →  {self.rows[-1].get(tcol)}"
        self.status.config(text=f"{len(self.rows)} rows for {sch['table']}{span}")

    def save_json(self):
        if not self.rows:
            self.generate()
            if not self.rows:
                return
        path = filedialog.asksaveasfilename(defaultextension=".json", initialdir=BASE,
                                            initialfile=f"{self.table_var.get()}_mock.json",
                                            filetypes=[("JSON", "*.json")])
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(self.rows, fh, indent=2, ensure_ascii=False)
            self.status.config(text=f"Saved {len(self.rows)} rows → {path}")

    # ================================================================== SCHEMA tab
    def _build_schema(self):
        f = self.tab_schema
        top = ttk.Frame(f)
        top.pack(fill="x", pady=(0, 6))
        self.schema_src = ttk.Label(top, text="", style="Muted.TLabel")
        self.schema_src.pack(side="left")
        fr, self.col_tree = make_tree(f, ("#", "Column", "Type", "Generator"), (40, 230, 90, 600), 18)
        fr.pack(fill="both", expand=True)
        self.col_tree.bind("<Double-1>", lambda e: self.edit_column())
        b = ttk.Frame(f)
        b.pack(fill="x", pady=(8, 0))
        for txt, cmd in (("+ Add", lambda: self.edit_column(new=True)), ("Edit", self.edit_column),
                         ("Delete", self.delete_column), ("▲", lambda: self.move_column(-1)),
                         ("▼", lambda: self.move_column(1))):
            ttk.Button(b, text=txt, command=cmd).pack(side="left", padx=(0, 4))
        ttk.Button(b, text="Save schema", style="Accent.TButton", command=self.save_current_schema).pack(
            side="right")
        ttk.Button(b, text="New table…", command=self.new_table).pack(side="right", padx=4)
        ttk.Button(b, text="Import from Learn (paste)…", command=self.import_learn).pack(side="right")
        ttk.Button(b, text="Reload from disk", command=self.reload_schemas).pack(side="right", padx=4)

    def refresh_columns(self):
        self.col_tree.delete(*self.col_tree.get_children())
        sch = self.schema()
        if not sch:
            return
        self.schema_src.config(text=f"{sch['table']}  —  {len(sch['columns'])} columns   "
                                    f"source: {sch.get('source', 'custom')}")
        for i, c in enumerate(sch["columns"]):
            self.col_tree.insert("", "end", iid=str(i), values=(i + 1, c["name"], c.get("type", ""),
                                                                c.get("gen", "") or "∅ (null)"))

    def edit_column(self, new=False):
        sch = self.schema()
        if not sch:
            return
        sel = self.col_tree.selection()
        if not new and not sel:
            return
        idx = None if new else int(sel[0])
        res = ColumnDialog(self, None if new else dict(sch["columns"][idx])).run()
        if res:
            if new:
                pos = (idx if idx is not None else (int(sel[0]) if sel else len(sch["columns"]) - 1)) + 1
                sch["columns"].insert(pos, res)
            else:
                sch["columns"][idx] = res
            self.refresh_columns()
            self.draw_graph()

    def delete_column(self):
        sel = self.col_tree.selection()
        if sel:
            del self.schema()["columns"][int(sel[0])]
            self.refresh_columns()

    def move_column(self, d):
        sel = self.col_tree.selection()
        if not sel:
            return
        cols, i = self.schema()["columns"], int(sel[0])
        j = i + d
        if 0 <= j < len(cols):
            cols[i], cols[j] = cols[j], cols[i]
            self.refresh_columns()
            self.col_tree.selection_set(str(j))

    def save_current_schema(self):
        sch = self.schema()
        if sch:
            path = save_schema(SCHEMA_DIR, sch)
            self.schema_src.config(text=f"✓ saved → {path}")

    def reload_schemas(self):
        self.schemas = load_schemas(SCHEMA_DIR)
        self.table_cb["values"] = sorted(self.schemas)
        self.on_table_change()

    def new_table(self):
        name = simpledialog.askstring("New table", "Table name (e.g. MyApp_CL):", parent=self)
        if not name:
            return
        self.schemas[name] = {"table": name, "source": "custom", "columns": [
            {"name": "TimeGenerated", "type": "datetime", "gen": "timestamp"}]}
        self.table_cb["values"] = sorted(self.schemas)
        self.table_var.set(name)
        self.on_table_change()

    def import_learn(self):
        d = Dialog(self, "Import columns from Microsoft Learn")
        ttk.Label(d.body, text="Open the table reference page on Microsoft Learn, copy the Columns table "
                               "(Column | Type | Description) and paste it here.", style="Muted.TLabel",
                  wraplength=620).pack(anchor="w")
        txt = make_text(d.body, height=18)
        txt.configure(width=90)
        txt.pack(fill="both", expand=True, pady=6)
        d.collect = lambda: parse_learn_paste(txt.get("1.0", "end"))
        cols = d.run()
        if not cols:
            if cols is not None:
                messagebox.showinfo("Import", "No columns recognised in the pasted text.")
            return
        sch = self.schema()
        ans = messagebox.askyesnocancel(
            "Import", f"Found {len(cols)} columns.\n\nYes = REPLACE all columns of {sch['table']}\n"
                      f"No = only ADD the missing ones")
        if ans is None:
            return
        if ans:
            sch["columns"] = cols
        else:
            have = {c["name"] for c in sch["columns"]}
            sch["columns"] += [c for c in cols if c["name"] not in have]
        self.refresh_columns()

    # ================================================================== ENTITIES tab
    def _build_entities(self):
        f = self.tab_ent
        top = ttk.Frame(f)
        top.pack(fill="both", expand=True)
        self.ent_trees = {}
        for kind in ("users", "devices"):
            box = ttk.LabelFrame(top, text=f" {kind.capitalize()} ", padding=8)
            box.pack(side="left", fill="both", expand=True, padx=(0, 8) if kind == "users" else 0)
            holder = ttk.Frame(box)
            holder.pack(fill="both", expand=True)
            self.ent_trees[kind] = holder
            b = ttk.Frame(box)
            b.pack(fill="x", pady=(6, 0))
            ttk.Button(b, text="+ Add", command=lambda k=kind: self.edit_entity(k, new=True)).pack(side="left")
            ttk.Button(b, text="Edit", command=lambda k=kind: self.edit_entity(k)).pack(side="left", padx=4)
            ttk.Button(b, text="Duplicate", command=lambda k=kind: self.edit_entity(k, dup=True)).pack(side="left")
            ttk.Button(b, text="Delete", command=lambda k=kind: self.delete_entity(k)).pack(side="left", padx=4)

        pb = ttk.LabelFrame(f, text=" Value pools   (name = value1, value2, ...)   → use with pool:name ",
                            padding=8)
        pb.pack(fill="x", pady=(10, 0))
        self.pools_txt = make_text(pb, height=6)
        self.pools_txt.pack(fill="x")

    def refresh_entities(self):
        ents = self.project.setdefault("entities", {"users": [], "devices": []})
        self._etree = getattr(self, "_etree", {})
        for kind, holder in self.ent_trees.items():
            for w in holder.winfo_children():
                w.destroy()
            items = ents.setdefault(kind, [])
            keys = ["id"] + sorted({k for e in items for k in e if k != "id"})
            fr, tree = make_tree(holder, keys, [110] + [120] * (len(keys) - 1), 14)
            fr.pack(fill="both", expand=True)
            tree.bind("<Double-1>", lambda e, k=kind: self.edit_entity(k))
            for i, e in enumerate(items):
                tree.insert("", "end", iid=str(i), values=[e.get(k, "") for k in keys])
            self._etree[kind] = tree

    def edit_entity(self, kind, new=False, dup=False):
        items = self.project["entities"][kind]
        sel = self._etree[kind].selection()
        if not new and not sel:
            return
        if new:
            template = {k: "" for k in (items[0] if items else {"id": ""})}
            template["id"] = f"{kind[:-1]}{len(items) + 1}"
            cur = template
        else:
            cur = copy.deepcopy(items[int(sel[0])])
            if dup:
                cur["id"] = cur["id"] + "_copy"
        res = EntityDialog(self, kind[:-1].capitalize(), cur).run()
        if not res:
            return
        others = [e["id"] for j, e in enumerate(items) if new or dup or j != int(sel[0])]
        if res["id"] in others:
            messagebox.showerror("Duplicate id", f"id '{res['id']}' already exists")
            return
        if new or dup:
            items.append(res)
        else:
            old_id = items[int(sel[0])]["id"]
            items[int(sel[0])] = res
            self._rename_in_relations(kind, old_id, res["id"])
        self.refresh_entities()
        self.refresh_relations()

    def _rename_in_relations(self, kind, old, new):
        if old == new:
            return
        rel = self.project.setdefault("relations", {})
        if kind == "users" and old in rel:
            rel[new] = rel.pop(old)
        if kind == "devices":
            for r in rel.values():
                r["devices"] = [new if d == old else d for d in r.get("devices", [])]

    def delete_entity(self, kind):
        sel = self._etree[kind].selection()
        if not sel:
            return
        e = self.project["entities"][kind].pop(int(sel[0]))
        rel = self.project.setdefault("relations", {})
        if kind == "users":
            rel.pop(e["id"], None)
        else:
            for r in rel.values():
                r["devices"] = [d for d in r.get("devices", []) if d != e["id"]]
        self.refresh_entities()
        self.refresh_relations()

    # ================================================================== RELATIONS tab
    def _build_relations(self):
        f = self.tab_rel
        left = ttk.Frame(f)
        left.pack(side="left", fill="y", padx=(0, 10))
        ttk.Label(left, text="User → device rules", style="Muted.TLabel").pack(anchor="w")
        fr, self.rel_tree = make_tree(left, ("User", "Mode", "Devices"), (90, 90, 190), 16)
        fr.pack(fill="both", expand=True, pady=4)
        self.rel_tree.bind("<Double-1>", lambda e: self.edit_relation())
        ttk.Button(left, text="Edit rule for selected user", command=self.edit_relation).pack(fill="x")
        legend = ("Legend\n━━  fixed (always same device)\n╍╍  random from list\n"
                  "┅┅  round-robin\n···  no rule → any device")
        ttk.Label(left, text=legend, style="Muted.TLabel", font=MONO, justify="left").pack(anchor="w", pady=10)

        right = ttk.Frame(f)
        right.pack(side="left", fill="both", expand=True)
        self.bind_lbl = ttk.Label(right, text="", style="Muted.TLabel", wraplength=800, justify="left")
        self.bind_lbl.pack(anchor="w")
        cf = ttk.Frame(right)
        cf.pack(fill="both", expand=True, pady=(6, 0))
        self.canvas = tk.Canvas(cf, bg=C["panel"], highlightthickness=0)
        sb = ttk.Scrollbar(cf, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=sb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.canvas.bind("<Configure>", lambda e: self.draw_graph())

    def refresh_relations(self):
        self.rel_tree.delete(*self.rel_tree.get_children())
        rel = self.project.setdefault("relations", {})
        for u in self.project["entities"].get("users", []):
            r = rel.get(u["id"])
            self.rel_tree.insert("", "end", iid=u["id"], values=(
                u["id"], r["mode"] if r else "—", ", ".join(r["devices"]) if r else "(any device)"))
        self.draw_graph()

    def edit_relation(self):
        sel = self.rel_tree.selection()
        if not sel:
            return
        uid = sel[0]
        dev_ids = [d["id"] for d in self.project["entities"].get("devices", [])]
        res = RelationDialog(self, uid, self.project["relations"].get(uid), dev_ids).run()
        if res is None:
            return
        if res.get("_delete"):
            self.project["relations"].pop(uid, None)
        else:
            self.project["relations"][uid] = res
        self.refresh_relations()

    def _bindings(self):
        """Which columns of the current table are fed by user.* / device.* attributes."""
        b = {"user": [], "device": []}
        sch = self.schema()
        if not sch:
            return b
        import re
        for c in sch["columns"]:
            g = c.get("gen", "")
            for kind in ("user", "device"):
                if g.startswith(kind + ".") or re.search(r"\{" + kind + r"\.", g):
                    b[kind].append(c["name"])
        return b

    def draw_graph(self):
        cv = getattr(self, "canvas", None)
        if cv is None:
            return
        cv.delete("all")
        users = self.project.get("entities", {}).get("users", [])
        devices = self.project.get("entities", {}).get("devices", [])
        rel = self.project.get("relations", {})
        b = self._bindings()
        self.bind_lbl.config(text=f"Table {self.table_var.get()}:   USER columns → {', '.join(b['user']) or '—'}"
                                  f"\n                         DEVICE columns → {', '.join(b['device']) or '—'}")
        W = max(cv.winfo_width(), 700)
        has_subnet = any(d.get("subnet") for d in devices)
        xs = [W * 0.14, W * 0.42, W * 0.66, W * 0.88] if has_subnet else [W * 0.17, W * 0.5, W * 0.83]
        nw, nh, gap, top = 150, 42, 18, 60

        def header(x, txt, color):
            cv.create_text(x, 25, text=txt, fill=color, font=("Segoe UI", 10, "bold"))

        def node(x, y, title, sub, color):
            cv.create_rectangle(x - nw / 2, y - nh / 2, x + nw / 2, y + nh / 2, fill=C["panel2"],
                                outline=color, width=2)
            cv.create_rectangle(x - nw / 2, y - nh / 2, x - nw / 2 + 5, y + nh / 2, fill=color, outline=color)
            cv.create_text(x + 2, y - 8, text=title, fill=C["fg"], font=("Segoe UI", 10, "bold"))
            cv.create_text(x + 2, y + 9, text=sub[:24], fill=C["muted"], font=("Segoe UI", 8))

        header(xs[0], "USERS", C["user"])
        header(xs[1], "DEVICES", C["device"])
        header(xs[2], "IP", C["net"])
        if has_subnet:
            header(xs[3], "SUBNET", C["subnet"])

        upos = {u["id"]: top + i * (nh + gap) for i, u in enumerate(users)}
        dpos = {d["id"]: top + i * (nh + gap) for i, d in enumerate(devices)}
        ips = list(dict.fromkeys(d.get("ip", "") for d in devices if d.get("ip")))
        ipos = {ip: top + i * (nh + gap) for i, ip in enumerate(ips)}
        subnets = list(dict.fromkeys(d.get("subnet", "") for d in devices if d.get("subnet")))
        spos = {s: top + i * (nh + gap) for i, s in enumerate(subnets)}

        # edges first (under nodes)
        for u in users:
            r = rel.get(u["id"])
            y1 = upos[u["id"]]
            if not r:
                for d in devices:
                    cv.create_line(xs[0] + nw / 2, y1, xs[1] - nw / 2, dpos[d["id"]], fill=C["line"],
                                   dash=(1, 4))
                continue
            style = {"fixed": None, "random": (6, 4), "round-robin": (2, 3)}.get(r["mode"])
            color = {"fixed": C["user"], "random": C["amber"], "round-robin": C["green"]}.get(r["mode"])
            devs = r["devices"][:1] if r["mode"] == "fixed" else r["devices"]
            for did in devs:
                if did in dpos:
                    kw = {"dash": style} if style else {}
                    cv.create_line(xs[0] + nw / 2, y1, xs[1] - nw / 2, dpos[did], fill=color, width=2,
                                   smooth=True, arrow="last", arrowshape=(8, 10, 4), **kw)
        for d in devices:
            if d.get("ip") in ipos:
                cv.create_line(xs[1] + nw / 2, dpos[d["id"]], xs[2] - nw / 2, ipos[d["ip"]], fill=C["device"],
                               width=2, arrow="last", arrowshape=(8, 10, 4))
            if has_subnet and d.get("subnet") in spos and d.get("ip") in ipos:
                cv.create_line(xs[2] + nw / 2, ipos[d["ip"]], xs[3] - nw / 2, spos[d["subnet"]],
                               fill=C["net"], width=2, arrow="last", arrowshape=(8, 10, 4))

        for u in users:
            node(xs[0], upos[u["id"]], u["id"], u.get("upn") or u.get("name", ""), C["user"])
        for d in devices:
            node(xs[1], dpos[d["id"]], d.get("name") or d["id"], d.get("os", ""), C["device"])
        for ip in ips:
            node(xs[2], ipos[ip], ip, "", C["net"])
        for s in subnets:
            node(xs[3], spos[s], s, "", C["subnet"])
        h = top + max(len(users), len(devices), len(ips), 1) * (nh + gap) + 20
        cv.configure(scrollregion=(0, 0, W, h))


if __name__ == "__main__":
    App().mainloop()
