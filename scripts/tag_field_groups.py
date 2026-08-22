"""One-off: insert `group:` lines into specs/data_dictionary.yaml per field.

Groups (clinical sequence): paciente, diagnostico, tratamiento, seguimiento.
Run once; kept in scripts/ for provenance.
"""

from __future__ import annotations

import pathlib
import re

PATH = pathlib.Path(__file__).resolve().parent.parent / "specs" / "data_dictionary.yaml"

GROUPS: dict[str, str] = {}


def _g(group: str, *ids: str) -> None:
    for fid in ids:
        GROUPS[fid] = group


_g("paciente", "historia_clinica", "nombre", "fecha_nacimiento", "edad", "sexo",
   "institucion", "medico", "fecha_registro", "ecog", "tabaquismo")
_g("diagnostico",
   "cie10_subcodigo", "fecha_diagnostico", "localizacion", "lateralidad", "tamano",
   "forma_presentacion", "histologia", "tipo_tumor", "grado", "grado_who",
   "grado_isup", "isup", "gleason", "invasion_muscular", "cis_asociado",
   "sindrome_cushing", "ki67", "tnm_t", "tnm_n", "tnm_m", "tnm_s",
   "estadio_igcccg", "imdc", "trombosis_venosa", "extension_local",
   "extension_extraprost", "invasion_vs", "psa_diagnostico", "afp", "bhcg", "ldh",
   "gammagrafia", "psma_pet", "pet_ct", "estudios_extension", "tac_torax",
   "tac_abdomen", "tac_torax_abdomen", "tac_uro", "tac_general",
   "tac_abdomen_pelvis", "tac_rmn_pelvis", "cistoscopia")
_g("tratamiento", "procedimiento", "fecha_procedimiento", "derivacion",
   "terapia_sistemica")
_g("seguimiento", "estado_actual", "psa_post", "psa_seguimiento", "afp_post",
   "bhcg_post", "recurrencia_previa", "num_recurrencias",
   "cistoscopia_seguimiento", "proximo_seguimiento", "observaciones")

text = PATH.read_text(encoding="utf-8")

field_starts = list(re.finditer(r"^([ ]*)- id: (\w+)[ ]*$", text, re.M))
missing: set[str] = set()
out = []
last = 0
for m in field_starts:
    indent, fid = m.group(1), m.group(2)
    out.append(text[last:m.end()])
    last = m.end()
    group = GROUPS.get(fid)
    if group is None:
        missing.add(fid)
        continue
    nxt = text[m.end():m.end() + 40]
    if not nxt.startswith(f"\n{indent}  code:"):
        raise SystemExit(f"unexpected layout after id {fid!r}: {nxt!r}")
    out.append(f"\n{indent}  group: {group}")
out.append(text[last:])
PATH.write_text("".join(out), encoding="utf-8")

print(f"tagged fields; ungrouped (must be none beyond known set): {sorted(missing)}")
