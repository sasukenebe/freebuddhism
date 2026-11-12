# SPDX-License-Identifier: 0BSD
"""Keep individual-sharing grants out of combined readers and bulk exports."""
from __future__ import annotations

INDIVIDUAL_LICENSE = "Sutta Friends — individual sutta sharing permission"
INDIVIDUAL_TERMS = (
    "Please feel free to share individual suttas however you like. Otherwise, "
    "the sutta translations on this site are © Mahamevnawa Buddhist Monastery."
)
INDIVIDUAL_CONDITIONS = ["Individual sutta sharing only; collection distribution not established",
                         "Retain attribution, source and the complete copyright/permission notice"]
INDIVIDUAL_DISTRIBUTION = {"individual_readers": True, "continuous_reader": False,
                           "site_archives": False, "source_archives": False}
INDIVIDUAL_RIGHTS_BASIS = (
    "The pinned Sutta Friends notice permits individual-sutta sharing; only individual article "
    "text/markup is copied. Combined readers, site archives and source archives are excluded."
)


def distribution(record: dict) -> dict:
    explicit = record.get("distribution")
    if record.get("license") == INDIVIDUAL_LICENSE:
        if (explicit != INDIVIDUAL_DISTRIBUTION or not isinstance(explicit, dict)
                or any(type(value) is not bool for value in explicit.values())):
            raise ValueError("Individual-sharing edition needs its exact restricted distribution policy")
        return dict(explicit)
    if explicit is not None:
        # No implicit new grant type or arbitrary per-format policy is accepted.
        raise ValueError("Unreviewed edition distribution policy")
    return {key: True for key in INDIVIDUAL_DISTRIBUTION}


def require_archive_permission(record: dict) -> None:
    if not distribution(record)["site_archives"]:
        raise ValueError("Individual-sharing edition cannot enter a collection archive")
