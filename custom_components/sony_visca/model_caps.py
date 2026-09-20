"""Model capability sets."""

from __future__ import annotations

from .models import GENERIC_ALL_MODEL_KEY, GENERIC_MODEL_KEY, MODEL_BY_KEY, resolve_model_key

FAMILY_X400_CORE = frozenset({"051C", "051D"})
FAMILY_X400_SRG = frozenset({"061A", "061B", "0618", "0617", "061C"})
FAMILY_X400 = FAMILY_X400_CORE | FAMILY_X400_SRG
FAMILY_X40UH = frozenset({"061F", "0620", "0621", "0622"})
FAMILY_X1000 = frozenset({"0519", "051B", "051A"})
FAMILY_X1000_NO_H780 = frozenset({"0519", "051A"})
FAMILY_FR7 = frozenset({"051E"})
FAMILY_AM7 = frozenset({"051F"})
FAMILY_120DH = frozenset({"0511"})
FAMILY_300H = frozenset({"0513"})
FAMILY_SE = frozenset({"0516"})
FAMILY_360SHE = frozenset({"0604", "0605"})

CAP_ALL_CAMERAS = (
    FAMILY_X400
    | FAMILY_X40UH
    | FAMILY_X1000
    | FAMILY_FR7
    | FAMILY_AM7
    | FAMILY_120DH
    | FAMILY_300H
    | FAMILY_SE
    | FAMILY_360SHE
)
CAP_ADVANCED = FAMILY_X400 | FAMILY_X40UH | FAMILY_X1000
CAP_ADVANCED_LEGACY = CAP_ADVANCED | FAMILY_120DH | FAMILY_300H | FAMILY_SE | FAMILY_360SHE
CAP_X400_X40UH = FAMILY_X400 | FAMILY_X40UH
CAP_X400_X40UH_SE = FAMILY_X400 | FAMILY_X40UH | FAMILY_SE | FAMILY_360SHE | FAMILY_300H
CAP_X400_X1000 = FAMILY_X400_CORE | FAMILY_X1000
CAP_X400_X1000_NO_H780 = FAMILY_X400_CORE | FAMILY_X1000_NO_H780
CAP_X400_CORE_X40UH = FAMILY_X400_CORE | FAMILY_X40UH
CAP_X400_ONLY = FAMILY_X400_CORE
CAP_TELECONVERT = FAMILY_X400_CORE | frozenset({"061C"}) | FAMILY_X1000 | FAMILY_AM7
CAP_ICR = FAMILY_X400 | FAMILY_X40UH | FAMILY_X1000_NO_H780 | FAMILY_SE | FAMILY_360SHE | FAMILY_300H
CAP_X1000 = FAMILY_X1000
CAP_X1000_FR7 = FAMILY_X1000 | FAMILY_FR7
CAP_FR7 = FAMILY_FR7
CAP_FR7_AM7 = FAMILY_FR7 | FAMILY_AM7
CAP_WIDE_DYNAMIC = FAMILY_X1000 | FAMILY_120DH | FAMILY_300H | FAMILY_SE | FAMILY_360SHE
CAP_BRIGHTNESS = FAMILY_120DH | FAMILY_300H | FAMILY_SE | FAMILY_360SHE
CAP_TALLY = FAMILY_X400_CORE | FAMILY_X1000 | FAMILY_360SHE | FAMILY_FR7 | FAMILY_AM7
CAP_PICTURE_EFFECT = FAMILY_X400 | FAMILY_X40UH | FAMILY_120DH | FAMILY_300H | FAMILY_SE | FAMILY_360SHE
CAP_RAMP_CURVE = FAMILY_X400 | FAMILY_X40UH | FAMILY_X1000 | FAMILY_FR7 | FAMILY_AM7
CAP_PT_SLOW = (
    FAMILY_X400
    | FAMILY_X40UH
    | FAMILY_X1000
    | FAMILY_FR7
    | FAMILY_AM7
    | FAMILY_300H
    | FAMILY_SE
    | FAMILY_360SHE
)
# PTZ Auto Framing for SRG-A40/A12 only; FR7/AM7 cinema path is out of scope.
CAP_AUTO_FRAMING = frozenset({"0621", "0622"})
# Spotlight compensation (CAM_Spotlight, 04 3A) is in block 02 of modern PTZ
# families only. SRG-120DH and other legacy cameras reject it with syntax error.
CAP_SPOTLIGHT = CAP_ADVANCED
# Auto slow shutter (04 5A) is in block 01 of X400/X40UH/legacy, not X1000.
CAP_SLOW_SHUTTER = CAP_ADVANCED_LEGACY - FAMILY_X1000
# Individual preset drive speed uses extended VISCA 7E 01 0B.
CAP_PRESET_DRIVE_SPEED = CAP_ADVANCED
# Clear Image Zoom option of CAM_DZoom (04 06 04).
CAP_CLEAR_IMAGE_ZOOM = CAP_ADVANCED
# White-balance Auto2 / ATW (04 35 04).
CAP_WB_ATW = CAP_ADVANCED
# High resolution (04 52): inquiry flag is in X400 block 01, not X40UH
# (that bit is highSensitivity there).
CAP_HIGH_RESOLUTION = FAMILY_X400


def visca_id_for_model(model_key: str) -> str | None:
    """Return the VISCA hex model id used for capability checks."""
    model = MODEL_BY_KEY.get(resolve_model_key(model_key))
    if model is None:
        return None
    return model.visca_id


def has_capability(model_key: str, capability: frozenset[str] | None) -> bool:
    """Return True if the stored model supports a capability set.

    Universal features pass ``capability=None``. ``other`` only gets those.
    ``other_all`` receives every gated feature.
    """
    if capability is None:
        return True
    key = resolve_model_key(model_key)
    if key == GENERIC_ALL_MODEL_KEY:
        return True
    if key == GENERIC_MODEL_KEY:
        return False
    visca_id = visca_id_for_model(key)
    if visca_id is None:
        return False
    return visca_id in capability
