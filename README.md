# Wizard of Logz

Mock log generator for Microsoft Sentinel / Defender XDR tables. Output is a JSON array,
so you can use it for logs ingestion.

## Run
```
git fetch https://github.com/batamladen/Wizard-of-Logz.git
```


```
python app.py
```
You need Python 3.9 or newer. Tkinter comes with the standard Windows installer, so there's nothing to pip install.

## Pre-Made Example Project for Clearance
An pre made project was already made for clearer understanding what goes where. Once the app loads you can hit *load project* and select example_project.json from the `wizardoflogz` folder.

Later when you create your projects, you can save them by clicking *Save Project* and open it whenever.

## Tabs
- **Generate**: start time, min/max gap between logs, seed, and batches (for example 17 legit + 3 exfil).
  Hit Generate to preview, then Save .json.
- **Schema**: columns for the selected table and the generator for each one. You can add, edit, reorder and delete columns,
  and *Import from Learn* lets you paste the column table from the Microsoft Learn table reference page.
  *New table…* is for custom `_CL` tables. Click *Save schema* to write the changes to `schemas/<Table>.json`.
- **Entities**: users and devices with any attributes you want (key = value), plus value pools.
- **Relations**: user → device rules (fixed / random / round-robin) and the relations graph
  (users → devices → IP → subnet). It also shows which columns in the current table come from user/device attributes.

## Generator cheat sheet
| Generator | Result |
|---|---|
| *(empty)* | null |
| `timestamp` | ordered log time |
| `ref:TimeGenerated` | copies another column from the same row |
| `user.upn`, `device.ip`, ... | an attribute of the row's user/device (follows the relations) |
| `const:443` | fixed value (JSON-typed) |
| `choice:allow*9\|deny*1` | weighted random pick |
| `int:49152-65535` | random integer |
| `pool:malicious_ips` | random value from a pool |
| `guid`, `mac`, `hex:64`, `ip:public`, `ip:private` | random values |
| `template:{user.domain}\{user.sam}` | text with placeholders `{user.x} {device.x} {row.Col} {pool.x} {ts}`; JSON gets parsed (good for dynamic columns) |

## Batches
A batch gives you N rows with optional **overrides** (`Column = generator`) that replace the schema generator.
If a batch has a user list like `user1, user1, user2`, that exact order is used.
When *Mix batches* is on, the batches are shuffled into one timeline.

## CLI
```
python engine.py project.json CommonSecurityLog out.json
```

## Notes
- The bundled schemas are trimmed to the core columns. Use *Import from Learn* to bring in the full column lists.
- The reserved `Type` column is left out on purpose because it can't be ingested.
- Entities are shared across tables, so user1/LAPTOP1 stays consistent across CSL, DeviceNetworkEvents, SigninLogs and the rest.
