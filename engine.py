"""
Mock Log Forge - generation engine (no GUI code here).
Can also be used from the command line:  python engine.py project.json CommonSecurityLog out.json
"""
import ipaddress
import json
import os
import random
import re
import sys
import uuid
from datetime import datetime, timedelta, timezone

TYPES = ["string", "datetime", "int", "long", "real", "bool", "dynamic", "guid"]

GEN_SUGGESTIONS = [
    "", "timestamp", "ref:TimeGenerated", "ref:Timestamp",
    "user.upn", "user.name", "user.sam", "user.domain", "user.sid", "user.objectId",
    "device.name", "device.fqdn", "device.ip", "device.mac", "device.os", "device.mdeId", "device.public_ip",
    "const:", "choice:a|b|c", "choice:allow*9|deny*1", "int:1-100", "pool:",
    "guid", "ip:public", "ip:private", "mac", "hex:64", "template:",
]

GEN_HELP = """GENERATOR CHEAT SHEET
(empty)              -> null
timestamp            -> ordered log time (same value in every timestamp column of a row)
ref:Column           -> copy value of another column in the same row
user.<attr>          -> attribute of the user picked for this row   (user.upn, user.sam ...)
device.<attr>        -> attribute of that user's device             (device.name, device.ip ...)
const:value          -> fixed value (const:443 becomes a number, const:true a bool)
choice:a|b|c         -> random pick;  weights: choice:allow*9|deny*1
int:min-max          -> random integer, e.g. int:49152-65535
pool:name            -> random value from a pool (Entities tab -> Pools)
guid / mac / hex:64  -> random GUID / MAC / hex string (hex:64 = SHA256-looking)
ip:public|ip:private -> random IP
template:text        -> text with placeholders {user.x} {device.x} {row.Column} {pool.name} {ts}
                        e.g. template:{user.domain}\\{user.sam}
                        JSON is parsed automatically -> great for 'dynamic' columns
"""


# ---------------------------------------------------------------- time helpers
def parse_time(s):
    s = (s or "").strip()
    if not s:
        return datetime.now(timezone.utc) - timedelta(hours=1)
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def fmt_time(dt):
    dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


# ---------------------------------------------------------------- schema I/O
def load_schemas(folder):
    out = {}
    if not os.path.isdir(folder):
        os.makedirs(folder, exist_ok=True)
    for f in sorted(os.listdir(folder)):
        if f.lower().endswith(".json"):
            with open(os.path.join(folder, f), encoding="utf-8") as fh:
                s = json.load(fh)
            out[s["table"]] = s
    return out


def save_schema(folder, schema):
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{schema['table']}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(schema, fh, indent=2, ensure_ascii=False)
    return path


def default_gen(name, typ):
    """Smart default generator for a column, used when importing a schema."""
    n = name.lower()
    if typ == "datetime" and n in ("timegenerated", "timestamp"):
        return "timestamp" if n == "timegenerated" else "ref:TimeGenerated"
    if n == "type":
        return ""
    if "upn" in n or "userprincipalname" in n:
        return "user.upn"
    if n in ("accountname", "targetusername", "sourceusername", "initiatingprocessaccountname"):
        return "user.sam"
    if n in ("accountdomain", "targetdomainname"):
        return "user.domain"
    if n in ("accountsid",):
        return "user.sid"
    if n in ("devicename", "computer", "sourcehostname", "workstationname"):
        return "device.name"
    if n in ("deviceid",):
        return "device.mdeId"
    if n in ("sourceip", "localip", "ipaddress"):
        return "device.ip"
    if typ == "guid":
        return "guid"
    return ""


def parse_learn_paste(text):
    """Parse the column table copied from a Microsoft Learn table-reference page.
    Accepts tab separated, markdown pipe tables, or 'Name Type Description' lines."""
    cols, seen = [], set()
    for line in text.splitlines():
        line = line.strip()
        if not line or set(line) <= set("|-: "):
            continue
        parts = [p for p in re.split(r"\t+|\s*\|\s*|\s{2,}", line) if p]
        if len(parts) < 2 or parts[1].lower() not in TYPES:
            parts = line.split()
        if len(parts) < 2:
            continue
        name, typ = parts[0].strip(), parts[1].strip().lower()
        if typ not in TYPES or name.lower() in ("column", "name") or name in seen:
            continue
        seen.add(name)
        cols.append({"name": name, "type": typ, "gen": default_gen(name, typ)})
    return cols


# ---------------------------------------------------------------- project helpers
def parse_pools(text):
    pools = {}
    for line in text.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            vals = [x.strip() for x in v.split(",") if x.strip()]
            if k.strip():
                pools[k.strip()] = vals
    return pools


def pools_to_text(pools):
    return "\n".join(f"{k} = {', '.join(v)}" for k, v in pools.items())


# ---------------------------------------------------------------- generator
TPL_RE = re.compile(r"\{(user|device|row|pool)\.([^{}\s]+)\}|\{ts\}")


class LogGenerator:
    def __init__(self, project, schema):
        self.p = project
        self.schema = schema
        seed = str(project.get("seed", "")).strip()
        self.rng = random.Random(int(seed) if seed.lstrip("-").isdigit() else (seed or None))
        ents = project.get("entities", {})
        self.users = {u["id"]: u for u in ents.get("users", [])}
        self.devices = {d["id"]: d for d in ents.get("devices", [])}
        self.relations = project.get("relations", {})
        self.pools = project.get("pools", {})
        self._rr_user = {}
        self._rr_dev = {}

    # ---- entity picking -------------------------------------------------
    def pick_user(self, batch):
        allowed = [u.strip() for u in batch.get("users", []) if u.strip() in self.users]
        pool = allowed or list(self.users)
        if not pool:
            return None
        if self.p.get("user_pick", "random") == "round-robin" or allowed:
            # explicit list in a batch is walked in order -> exact control (user1,user1,user2)
            key = batch.get("name", "")
            i = self._rr_user.get(key, 0)
            self._rr_user[key] = i + 1
            return pool[i % len(pool)]
        weights = [float(self.users[u].get("weight", 1) or 1) for u in pool]
        return self.rng.choices(pool, weights=weights)[0]

    def pick_device(self, uid):
        rule = self.relations.get(uid) if uid else None
        devs = [d for d in (rule or {}).get("devices", []) if d in self.devices]
        mode = (rule or {}).get("mode", "random")
        if not devs:
            devs = list(self.devices)
            mode = "random"
        if not devs:
            return None
        if mode == "fixed":
            return devs[0]
        if mode == "round-robin":
            i = self._rr_dev.get(uid, 0)
            self._rr_dev[uid] = i + 1
            return devs[i % len(devs)]
        return self.rng.choice(devs)

    # ---- value generators ----------------------------------------------
    def _rand_ip(self, public):
        while True:
            ip = ipaddress.IPv4Address(self.rng.getrandbits(32))
            if public and ip.is_global and not ip.is_multicast:
                return str(ip)
            if not public:
                return f"10.{self.rng.randint(0, 255)}.{self.rng.randint(0, 255)}.{self.rng.randint(1, 254)}"

    def _template(self, text, ctx):
        def rep(m):
            if m.group(0) == "{ts}":
                return fmt_time(ctx["ts"])
            kind, attr = m.group(1), m.group(2)
            if kind == "pool":
                vals = self.pools.get(attr) or [""]
                return str(self.rng.choice(vals))
            src = ctx["row"] if kind == "row" else (ctx[kind] or {})
            v = src.get(attr)
            return "" if v is None else str(v)
        out = TPL_RE.sub(rep, text)
        try:
            return json.loads(out)
        except (ValueError, TypeError):
            return out

    def evaluate(self, expr, ctx):
        expr = (expr or "").strip()
        if not expr:
            return None
        if expr == "timestamp":
            return fmt_time(ctx["ts"])
        if expr.startswith("user."):
            return (ctx["user"] or {}).get(expr[5:])
        if expr.startswith("device."):
            return (ctx["device"] or {}).get(expr[7:])
        if expr == "guid":
            return str(uuid.UUID(int=self.rng.getrandbits(128), version=4))
        if expr == "mac":
            return "-".join(f"{self.rng.randint(0, 255):02X}" for _ in range(6))
        if expr == "ip:public":
            return self._rand_ip(True)
        if expr == "ip:private":
            return self._rand_ip(False)
        head, _, arg = expr.partition(":")
        if head == "const":
            try:
                return json.loads(arg)
            except ValueError:
                return arg
        if head == "choice":
            vals, weights = [], []
            for part in arg.split("|"):
                v, _, w = part.rpartition("*") if "*" in part else (part, "", "1")
                vals.append(v)
                weights.append(float(w or 1))
            v = self.rng.choices(vals, weights=weights)[0]
            try:
                return json.loads(v)
            except ValueError:
                return v
        if head == "int":
            a, b = re.match(r"\s*(-?\d+)\s*-\s*(-?\d+)", arg).groups()
            return self.rng.randint(int(a), int(b))
        if head == "pool":
            vals = self.pools.get(arg.strip())
            return self.rng.choice(vals) if vals else None
        if head == "hex":
            n = int(arg or 32)
            return "".join(self.rng.choice("0123456789abcdef") for _ in range(n))
        if head == "template":
            return self._template(arg, ctx)
        return expr  # unknown -> literal text

    @staticmethod
    def coerce(v, typ):
        if v is None or v == "":
            return None if v is None else v
        try:
            if typ in ("int", "long"):
                return int(v)
            if typ == "real":
                return float(v)
            if typ == "bool":
                return v if isinstance(v, bool) else str(v).lower() in ("true", "1", "yes")
            if typ == "dynamic" and isinstance(v, str):
                return json.loads(v)
            if typ in ("string", "guid") and not isinstance(v, (str, dict, list)):
                return str(v).lower() if isinstance(v, bool) else str(v)
        except (ValueError, TypeError):
            pass
        return v

    # ---- main ----------------------------------------------------------
    def generate(self):
        batches = self.p.get("batches") or [{"name": "default", "count": 10, "users": [], "overrides": {}}]
        plan = []
        for b in batches:
            plan += [b] * int(b.get("count", 0))
        if self.p.get("shuffle", True):
            self.rng.shuffle(plan)

        ts = parse_time(self.p.get("start_time"))
        lo = float(self.p.get("interval_min", 5))
        hi = float(self.p.get("interval_max", 120))
        cols = self.schema["columns"]
        rows = []
        for i, b in enumerate(plan):
            if i:
                ts += timedelta(seconds=self.rng.uniform(lo, max(lo, hi)))
            uid = self.pick_user(b)
            did = self.pick_device(uid)
            types = {c["name"]: c.get("type", "string") for c in cols}
            gens = {c["name"]: c.get("gen", "") for c in cols}
            # overrides only apply to columns that exist in this table's schema
            gens.update({k: v for k, v in b.get("overrides", {}).items() if k in types})
            ctx = {"ts": ts, "user": self.users.get(uid), "device": self.devices.get(did), "row": {}}
            row = ctx["row"]
            deferred = []
            names = [c["name"] for c in cols]
            for name in names:
                g = gens.get(name, "")
                row[name] = None
                if g.startswith("ref:") or "{row." in g:
                    deferred.append(name)
                else:
                    row[name] = self.coerce(self.evaluate(g, ctx), types.get(name, "string"))
            for name in deferred:
                g = gens[name]
                v = row.get(g[4:].strip()) if g.startswith("ref:") else self.evaluate(g, ctx)
                row[name] = self.coerce(v, types.get(name, "string"))
            if self.p.get("drop_nulls"):
                row = {k: v for k, v in row.items() if v is not None}
            rows.append(dict(row))
        return rows


def generate_to_file(project, schema, path):
    rows = LogGenerator(project, schema).generate()
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=2, ensure_ascii=False)
    return rows


if __name__ == "__main__":  # CLI: python engine.py project.json TableName out.json
    if len(sys.argv) != 4:
        print("usage: python engine.py project.json TableName output.json")
        sys.exit(1)
    base = os.path.dirname(os.path.abspath(__file__))
    with open(sys.argv[1], encoding="utf-8") as fh:
        proj = json.load(fh)
    sch = load_schemas(os.path.join(base, "schemas"))[sys.argv[2]]
    print(f"wrote {len(generate_to_file(proj, sch, sys.argv[3]))} rows -> {sys.argv[3]}")
