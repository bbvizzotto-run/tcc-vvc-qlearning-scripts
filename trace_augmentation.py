"""Randomização de domínio aplicada somente aos traces de treinamento."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np


@dataclass(frozen=True)
class TraceAugmentationConfig:
    """Transformações determinísticas que aumentam a diversidade de rede."""

    apply_probability: float = 1.0
    scale_min: float = 0.75
    scale_max: float = 1.25
    jitter_fraction: float = 0.12
    circular_shift: bool = True
    burst_probability: float = 0.8
    burst_count_min: int = 1
    burst_count_max: int = 3
    burst_length_min: int = 1
    burst_length_max: int = 4
    burst_factor_min: float = 0.10
    burst_factor_max: float = 0.35
    min_bandwidth_kbps: float = 250.0

    def __post_init__(self) -> None:
        if not 0 <= self.apply_probability <= 1:
            raise ValueError("apply_probability deve pertencer a [0, 1]")
        if self.scale_min <= 0 or self.scale_max < self.scale_min:
            raise ValueError("os limites de escala são inválidos")
        if not 0 <= self.jitter_fraction < 1:
            raise ValueError("jitter_fraction deve pertencer a [0, 1)")
        if not 0 <= self.burst_probability <= 1:
            raise ValueError("burst_probability deve pertencer a [0, 1]")
        if not 0 <= self.burst_count_min <= self.burst_count_max:
            raise ValueError("a quantidade de rajadas é inválida")
        if not 1 <= self.burst_length_min <= self.burst_length_max:
            raise ValueError("a duração das rajadas é inválida")
        if not 0 < self.burst_factor_min <= self.burst_factor_max <= 1:
            raise ValueError("os fatores de rajada devem pertencer a (0, 1]")
        if self.min_bandwidth_kbps <= 0:
            raise ValueError("min_bandwidth_kbps deve ser positivo")


def augment_bandwidth_trace(
    trace: Sequence[float],
    config: TraceAugmentationConfig,
    seed: int,
) -> list[float]:
    """Gera uma variante do trace sem alterar a sequência original.

    A semente é explícita para permitir regenerar cada episódio. As quedas são
    criadas após escala, jitter e deslocamento, e podem se sobrepor.
    """

    values = np.asarray(tuple(float(value) for value in trace), dtype=np.float64)
    if values.size == 0:
        raise ValueError("o trace não pode ser vazio")
    if np.any(values <= 0):
        raise ValueError("todas as larguras de banda devem ser positivas")
    if seed < 0:
        raise ValueError("seed não pode ser negativa")

    rng = np.random.default_rng(seed)
    if rng.random() >= config.apply_probability:
        return values.tolist()

    augmented = values.copy()
    if config.circular_shift and augmented.size > 1:
        shift = int(rng.integers(0, augmented.size))
        augmented = np.roll(augmented, shift)

    augmented *= float(rng.uniform(config.scale_min, config.scale_max))
    if config.jitter_fraction > 0:
        jitter = rng.uniform(
            1.0 - config.jitter_fraction,
            1.0 + config.jitter_fraction,
            size=augmented.size,
        )
        augmented *= jitter

    if rng.random() < config.burst_probability:
        burst_count = int(
            rng.integers(config.burst_count_min, config.burst_count_max + 1)
        )
        for _ in range(burst_count):
            start = int(rng.integers(0, augmented.size))
            length = int(
                rng.integers(config.burst_length_min, config.burst_length_max + 1)
            )
            factor = float(
                rng.uniform(config.burst_factor_min, config.burst_factor_max)
            )
            stop = min(start + length, augmented.size)
            augmented[start:stop] *= factor

    np.maximum(augmented, config.min_bandwidth_kbps, out=augmented)
    return augmented.tolist()
