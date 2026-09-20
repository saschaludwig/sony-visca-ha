"""Known Sony VISCA camera models and CAM_VersionInq lookups."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CameraModel:
    """A camera model shown in the UI and stored in config."""

    key: str
    name: str
    visca_id: str | None = None
    inquiry_group: str = "1a"


# Display names only. visca_id is the 16-bit CAM_VersionInq model code.
CAMERA_MODELS: tuple[CameraModel, ...] = (
    CameraModel("other", "Other / generic", inquiry_group="1a"),
    CameraModel("other_all", "Other / all features", inquiry_group="1a"),
    CameraModel("brc_am7", "BRC-AM7", "051F", "6"),
    CameraModel("brc_h780", "BRC-H780", "051B", "2"),
    CameraModel("brc_h800", "BRC-H800", "051A", "2"),
    CameraModel("brc_x400", "BRC-X400", "051C", "1a"),
    CameraModel("brc_x401", "BRC-X401", "051D", "1a"),
    CameraModel("brc_x1000", "BRC-X1000", "0519", "2"),
    CameraModel("ilme_fr7", "ILME-FR7", "051E", "4"),
    CameraModel("ilme_fr7k", "ILME-FR7K", "051E", "4"),
    CameraModel("srg_120dh", "SRG-120DH", "0511", "3a"),
    CameraModel("srg_201m2", "SRG-201M2", "061A", "1a"),
    CameraModel("srg_201se", "SRG-201SE", "0516", "3b"),
    CameraModel("srg_280she", "SRG-280SHE", "0605", "3c"),
    CameraModel("srg_300h", "SRG-300H", "0513", "3d"),
    CameraModel("srg_300se", "SRG-300SE", "0516", "3b"),
    CameraModel("srg_301se", "SRG-301SE", "0516", "3b"),
    CameraModel("srg_360she", "SRG-360SHE", "0604", "3c"),
    CameraModel("srg_a12", "SRG-A12", "0622", "5"),
    CameraModel("srg_a40", "SRG-A40", "0621", "5"),
    CameraModel("srg_h40uh", "SRG-H40UH", "0620", "1b"),
    CameraModel("srg_hd1m2", "SRG-HD1M2", "061B", "1a"),
    CameraModel("srg_x40uh", "SRG-X40UH", "061F", "1b"),
    CameraModel("srg_x120", "SRG-X120", "0618", "1a"),
    CameraModel("srg_x400", "SRG-X400", "0617", "1a"),
    CameraModel("srg_x402", "SRG-X402", "061C", "1a"),
)

MODEL_BY_KEY: dict[str, CameraModel] = {model.key: model for model in CAMERA_MODELS}

# Previous config values used VISCA model hex IDs.
LEGACY_MODEL_KEYS: dict[str, str] = {
    "other_min": "other",
    "0511": "srg_120dh",
    "0513": "srg_300h",
    "0516a": "srg_201se",
    "0516b": "srg_300se",
    "0516c": "srg_301se",
    "0519": "brc_x1000",
    "051A": "brc_h800",
    "051B": "brc_h780",
    "051C": "brc_x400",
    "051D": "brc_x401",
    "051E": "ilme_fr7",
    "051Ek": "ilme_fr7k",
    "051F": "brc_am7",
    "0604": "srg_360she",
    "0605": "srg_280she",
    "0617": "srg_x400",
    "0618": "srg_x120",
    "061A": "srg_201m2",
    "061B": "srg_hd1m2",
    "061C": "srg_x402",
    "061F": "srg_x40uh",
    "0620": "srg_h40uh",
    "0621": "srg_a40",
    "0622": "srg_a12",
}

GENERIC_MODEL_KEY = "other"
GENERIC_ALL_MODEL_KEY = "other_all"
GENERIC_KEYS = frozenset({GENERIC_MODEL_KEY, GENERIC_ALL_MODEL_KEY})


def inquiry_group_for_model(stored: str | None) -> str:
    """Return the inquiry-block group for a stored model key."""
    return MODEL_BY_KEY[resolve_model_key(stored)].inquiry_group


def resolve_model_key(stored: str | None) -> str:
    """Normalize a stored model key, including legacy hex IDs."""
    if not stored:
        return GENERIC_MODEL_KEY
    if stored in MODEL_BY_KEY:
        return stored
    return LEGACY_MODEL_KEYS.get(stored, GENERIC_MODEL_KEY)


def model_display_name(stored: str | None) -> str:
    """Return the UI name for a stored model key."""
    return MODEL_BY_KEY[resolve_model_key(stored)].name


def models_for_visca_id(visca_id: str) -> list[CameraModel]:
    """Return known cameras that share a CAM_VersionInq model code."""
    code = visca_id.upper()
    return [model for model in CAMERA_MODELS if model.visca_id == code]


def selectable_models(candidates: list[CameraModel] | None = None) -> list[CameraModel]:
    """Models offered in a dropdown, with generic last."""
    if candidates:
        items = list(candidates)
        if not any(item.key == GENERIC_MODEL_KEY for item in items):
            items.append(MODEL_BY_KEY[GENERIC_MODEL_KEY])
        return items
    return [model for model in CAMERA_MODELS if model.key not in GENERIC_KEYS] + [
        MODEL_BY_KEY[GENERIC_MODEL_KEY],
        MODEL_BY_KEY[GENERIC_ALL_MODEL_KEY],
    ]
