"""Controladores de bitrate para o ambiente de streaming."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class ControllerDecision:
    bitrate_kbps: int
    action: str


class StaticThresholdController:
    """Baseline que altera um nível de bitrate conforme o buffer.

    Abaixo do limiar inferior, reduz um nível. Acima do limiar superior,
    aumenta um nível. Na zona intermediária, mantém a representação atual.
    """

    def __init__(
        self,
        bitrates_kbps: Sequence[int],
        low_buffer_s: float = 4.0,
        high_buffer_s: float = 10.0,
    ) -> None:
        bitrates = tuple(sorted(set(int(value) for value in bitrates_kbps)))
        if not bitrates or any(value <= 0 for value in bitrates):
            raise ValueError("forneça ao menos um bitrate positivo")
        if low_buffer_s < 0 or high_buffer_s <= low_buffer_s:
            raise ValueError("os limiares do buffer são inválidos")

        self.bitrates_kbps = bitrates
        self.low_buffer_s = float(low_buffer_s)
        self.high_buffer_s = float(high_buffer_s)
        self.current_index = 0

    def reset(self) -> None:
        self.current_index = 0

    def select_bitrate(self, buffer_s: float) -> ControllerDecision:
        previous_index = self.current_index
        if buffer_s < self.low_buffer_s:
            self.current_index = max(0, self.current_index - 1)
        elif buffer_s > self.high_buffer_s:
            self.current_index = min(
                len(self.bitrates_kbps) - 1,
                self.current_index + 1,
            )

        if self.current_index < previous_index:
            action = "decrease"
        elif self.current_index > previous_index:
            action = "increase"
        else:
            action = "maintain"

        return ControllerDecision(
            bitrate_kbps=self.bitrates_kbps[self.current_index],
            action=action,
        )
