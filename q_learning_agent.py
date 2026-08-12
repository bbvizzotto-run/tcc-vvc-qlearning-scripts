"""Implementação reutilizável do algoritmo Q-Learning tabular."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np


class QLearningAgent:
    """Agente tabular com política epsilon-greedy e persistência em NPZ."""

    def __init__(
        self,
        state_space_size: int,
        action_space_size: int,
        learning_rate: float = 0.1,
        discount_factor: float = 0.95,
        epsilon: float = 1.0,
        epsilon_min: float = 0.05,
        epsilon_decay: float = 0.995,
        seed: int | None = None,
    ) -> None:
        if state_space_size <= 0 or action_space_size <= 0:
            raise ValueError("os espaços de estados e ações devem ser positivos")
        if not 0 < learning_rate <= 1:
            raise ValueError("learning_rate deve pertencer ao intervalo (0, 1]")
        if not 0 <= discount_factor <= 1:
            raise ValueError("discount_factor deve pertencer ao intervalo [0, 1]")
        if not 0 <= epsilon <= 1:
            raise ValueError("epsilon deve pertencer ao intervalo [0, 1]")
        if not 0 <= epsilon_min <= epsilon:
            raise ValueError("epsilon_min deve pertencer ao intervalo [0, epsilon]")
        if not 0 < epsilon_decay <= 1:
            raise ValueError("epsilon_decay deve pertencer ao intervalo (0, 1]")

        self.state_space_size = int(state_space_size)
        self.action_space_size = int(action_space_size)
        self.learning_rate = float(learning_rate)
        self.discount_factor = float(discount_factor)
        self.epsilon = float(epsilon)
        self.epsilon_min = float(epsilon_min)
        self.epsilon_decay = float(epsilon_decay)
        self.seed = seed
        self.rng = np.random.default_rng(seed)
        self.q_table = np.zeros(
            (self.state_space_size, self.action_space_size),
            dtype=np.float64,
        )

    def _validate_state(self, state_index: int) -> None:
        if not 0 <= state_index < self.state_space_size:
            raise IndexError(f"estado fora da Q-table: {state_index}")

    def choose_action(self, state_index: int, explore: bool = True) -> int:
        """Seleciona uma ação e desempata valores Q máximos aleatoriamente."""

        self._validate_state(state_index)
        if explore and self.rng.random() < self.epsilon:
            return int(self.rng.integers(self.action_space_size))

        values = self.q_table[state_index]
        best_actions = np.flatnonzero(np.isclose(values, np.max(values)))
        return int(self.rng.choice(best_actions))

    def update_q_table(
        self,
        current_state_index: int,
        action: int,
        reward: float,
        next_state_index: int,
        terminal: bool = False,
    ) -> float:
        """Aplica a atualização de Bellman e retorna o erro TD."""

        self._validate_state(current_state_index)
        self._validate_state(next_state_index)
        if not 0 <= action < self.action_space_size:
            raise IndexError(f"ação fora da Q-table: {action}")

        future_value = 0.0 if terminal else float(np.max(self.q_table[next_state_index]))
        td_target = float(reward) + self.discount_factor * future_value
        td_error = td_target - self.q_table[current_state_index, action]
        self.q_table[current_state_index, action] += self.learning_rate * td_error
        return float(td_error)

    def decay_epsilon(self) -> float:
        self.epsilon = max(self.epsilon_min, self.epsilon * self.epsilon_decay)
        return self.epsilon

    @staticmethod
    def get_action_meaning(action: int) -> str:
        meanings = ("decrease", "maintain", "increase")
        if not 0 <= action < len(meanings):
            raise ValueError(f"ação desconhecida: {action}")
        return meanings[action]

    def save(
        self,
        path: str | Path,
        metadata: Mapping[str, Any] | None = None,
    ) -> Path:
        """Salva Q-table, hiperparâmetros e metadados sem usar pickle."""

        destination = Path(path)
        if destination.suffix != ".npz":
            destination = destination.with_suffix(".npz")
        destination.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            destination,
            q_table=self.q_table,
            state_space_size=self.state_space_size,
            action_space_size=self.action_space_size,
            learning_rate=self.learning_rate,
            discount_factor=self.discount_factor,
            epsilon=self.epsilon,
            epsilon_min=self.epsilon_min,
            epsilon_decay=self.epsilon_decay,
            seed=-1 if self.seed is None else self.seed,
            metadata_json=json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
        )
        return destination

    @classmethod
    def load(
        cls,
        path: str | Path,
        seed: int | None = None,
    ) -> tuple["QLearningAgent", dict[str, Any]]:
        """Carrega um modelo e valida as dimensões declaradas."""

        with np.load(Path(path), allow_pickle=False) as data:
            stored_seed = int(data["seed"])
            agent = cls(
                state_space_size=int(data["state_space_size"]),
                action_space_size=int(data["action_space_size"]),
                learning_rate=float(data["learning_rate"]),
                discount_factor=float(data["discount_factor"]),
                epsilon=float(data["epsilon"]),
                epsilon_min=float(data["epsilon_min"]),
                epsilon_decay=float(data["epsilon_decay"]),
                seed=seed if seed is not None else (None if stored_seed < 0 else stored_seed),
            )
            q_table = np.asarray(data["q_table"], dtype=np.float64)
            if q_table.shape != agent.q_table.shape:
                raise ValueError(
                    f"Q-table incompatível: {q_table.shape} != {agent.q_table.shape}"
                )
            agent.q_table = q_table.copy()
            metadata = json.loads(str(data["metadata_json"].item()))
        return agent, metadata
