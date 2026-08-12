"""Manifesto validado de segmentos pré-codificados e suas representações."""

from __future__ import annotations

import csv
import hashlib
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


REQUIRED_COLUMNS: tuple[str, ...] = (
    "sequence",
    "segment",
    "bitrate_kbps",
    "duration_s",
    "size_bytes",
)
OPTIONAL_COLUMNS: tuple[str, ...] = (
    "psnr_y_db",
    "source_file",
    "sha256",
)
SHA256_PATTERN = re.compile(r"[0-9a-fA-F]{64}")


@dataclass(frozen=True)
class SegmentMetadata:
    """Metadados de uma representação para um segmento de vídeo."""

    sequence: str
    segment: int
    bitrate_kbps: int
    duration_s: float
    size_bytes: int
    psnr_y_db: float | None = None
    source_file: str | None = None
    sha256: str | None = None

    def __post_init__(self) -> None:
        sequence = self.sequence.strip()
        if not sequence:
            raise ValueError("sequence não pode ser vazia")
        if self.segment < 0:
            raise ValueError("segment não pode ser negativo")
        if self.bitrate_kbps <= 0:
            raise ValueError("bitrate_kbps deve ser positivo")
        if not math.isfinite(self.duration_s) or self.duration_s <= 0:
            raise ValueError("duration_s deve ser positivo e finito")
        if self.size_bytes <= 0:
            raise ValueError("size_bytes deve ser positivo")
        if self.psnr_y_db is not None and (
            not math.isfinite(self.psnr_y_db) or self.psnr_y_db <= 0
        ):
            raise ValueError("psnr_y_db deve ser positivo e finito")
        if self.sha256 is not None and not SHA256_PATTERN.fullmatch(self.sha256):
            raise ValueError("sha256 deve conter 64 dígitos hexadecimais")

        object.__setattr__(self, "sequence", sequence)
        if self.source_file is not None:
            source_file = self.source_file.strip()
            object.__setattr__(self, "source_file", source_file or None)
        if self.sha256 is not None:
            object.__setattr__(self, "sha256", self.sha256.lower())

    @property
    def size_kbits(self) -> float:
        """Tamanho em kilobits decimais, compatível com kbps."""

        return self.size_bytes * 8.0 / 1000.0


class SegmentManifest:
    """Catálogo completo de uma sequência e uma escada de representações."""

    def __init__(
        self,
        entries: Sequence[SegmentMetadata],
        source_path: str | Path | None = None,
    ) -> None:
        if not entries:
            raise ValueError("o manifesto não pode ser vazio")
        self.source_path = Path(source_path).resolve() if source_path else None
        self.manifest_sha256 = (
            hashlib.sha256(self.source_path.read_bytes()).hexdigest()
            if self.source_path is not None
            else None
        )

        by_key: dict[tuple[int, int], SegmentMetadata] = {}
        sequences: set[str] = set()
        for entry in entries:
            key = (entry.segment, entry.bitrate_kbps)
            if key in by_key:
                raise ValueError(
                    "representação duplicada para "
                    f"segment={entry.segment}, bitrate={entry.bitrate_kbps}"
                )
            by_key[key] = entry
            sequences.add(entry.sequence)
        if len(sequences) != 1:
            raise ValueError("cada manifesto deve conter exatamente uma sequência")

        segment_indices = tuple(sorted({key[0] for key in by_key}))
        expected_segments = tuple(range(len(segment_indices)))
        if segment_indices != expected_segments:
            raise ValueError("os segmentos devem ser consecutivos e começar em zero")

        bitrates = tuple(sorted({key[1] for key in by_key}))
        for segment in segment_indices:
            segment_entries = [by_key.get((segment, bitrate)) for bitrate in bitrates]
            if any(entry is None for entry in segment_entries):
                raise ValueError(
                    f"a escada de representações está incompleta no segmento {segment}"
                )
            durations = [
                entry.duration_s for entry in segment_entries if entry is not None
            ]
            if not all(
                math.isclose(duration, durations[0], rel_tol=0, abs_tol=1e-9)
                for duration in durations[1:]
            ):
                raise ValueError(
                    f"as representações do segmento {segment} têm durações diferentes"
                )

        self._entries = by_key
        self.sequence = next(iter(sequences))
        self.segment_indices = segment_indices
        self.bitrates_kbps = bitrates

    @classmethod
    def load(cls, path: str | Path) -> "SegmentManifest":
        """Carrega um CSV e informa erros com o número da linha."""

        source_path = Path(path).resolve()
        entries: list[SegmentMetadata] = []
        with source_path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            fields = set(reader.fieldnames or ())
            missing = [column for column in REQUIRED_COLUMNS if column not in fields]
            if missing:
                raise ValueError(
                    "colunas obrigatórias ausentes no manifesto: "
                    + ", ".join(missing)
                )
            for row_number, row in enumerate(reader, start=2):
                try:
                    psnr_text = (row.get("psnr_y_db") or "").strip()
                    source_file = (row.get("source_file") or "").strip() or None
                    sha256 = (row.get("sha256") or "").strip() or None
                    entries.append(
                        SegmentMetadata(
                            sequence=str(row["sequence"]),
                            segment=int(row["segment"]),
                            bitrate_kbps=int(row["bitrate_kbps"]),
                            duration_s=float(row["duration_s"]),
                            size_bytes=int(row["size_bytes"]),
                            psnr_y_db=float(psnr_text) if psnr_text else None,
                            source_file=source_file,
                            sha256=sha256,
                        )
                    )
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        f"manifesto inválido na linha {row_number}: {exc}"
                    ) from exc
        return cls(entries, source_path)

    @property
    def segment_count(self) -> int:
        return len(self.segment_indices)

    def get(self, segment: int, bitrate_kbps: int) -> SegmentMetadata:
        try:
            return self._entries[(int(segment), int(bitrate_kbps))]
        except KeyError as exc:
            raise ValueError(
                "representação ausente no manifesto para "
                f"segment={segment}, bitrate={bitrate_kbps}"
            ) from exc

    def metadata(self) -> dict[str, object]:
        """Resumo serializável para logs, modelos e manifestos experimentais."""

        return {
            "source": self.source_path.name if self.source_path else None,
            "manifest_sha256": self.manifest_sha256,
            "sequence": self.sequence,
            "segment_count": self.segment_count,
            "bitrates_kbps": list(self.bitrates_kbps),
            "size_unit": "bytes",
        }


def load_segment_manifest(path: str | Path) -> SegmentManifest:
    """Atalho público equivalente a ``SegmentManifest.load``."""

    return SegmentManifest.load(path)
