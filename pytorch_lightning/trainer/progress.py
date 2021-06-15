# Copyright The PyTorch Lightning team.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Optional, Tuple


@dataclass
class Tracker:
    """
    Track an event's progress.

    Args:
        ready: Intended to track the number of events ready to start.
        started: Intended to be incremented after the event is started (e.g. after ``on_*_start`` runs).
        processed: Intended to be incremented after the event is processed.
        completed: Intended to be incremented after the event completes (e.g. after ``on_*_end`` runs).

    Attributes set to ``None`` are treated as unused and are restricted.
    """
    ready: Optional[int] = 0
    started: Optional[int] = 0
    processed: Optional[int] = 0
    completed: Optional[int] = 0

    def reset(self) -> None:
        if self.ready is not None:
            self.ready = 0
        if self.started is not None:
            self.started = 0
        if self.processed is not None:
            self.processed = 0
        if self.completed is not None:
            self.completed = 0

    def __setattr__(self, key: str, value: int) -> None:
        if getattr(self, key, 0) is None:
            raise AttributeError(f"The '{key}' attribute is meant to be unused")
        return super().__setattr__(key, value)

    def __repr__(self):
        # hide `None` fields
        args = [f"{k}={v}" for k, v in self.__dict__.items() if v is not None]
        return f"{self.__class__.__name__}({', '.join(args)})"


@dataclass
class Progress:
    """
    Track aggregated and current progress.

    Args:
        total: Intended to track the total progress of an event
        current: Intended to track the current progress of an event
    """
    total: Tracker = field(default_factory=Tracker)
    current: Tracker = field(default_factory=Tracker)

    def increment_ready(self) -> None:
        if self.total.ready is None or self.current.ready is None:
            return
        self.total.ready += 1
        self.current.ready += 1

    def increment_started(self) -> None:
        if self.total.started is None or self.current.started is None:
            return
        self.total.started += 1
        self.current.started += 1

    def increment_processed(self) -> None:
        if self.total.processed is None or self.current.processed is None:
            return
        self.total.processed += 1
        self.current.processed += 1

    def increment_completed(self) -> None:
        if self.total.completed is None or self.current.completed is None:
            return
        self.total.completed += 1
        self.current.completed += 1

    @classmethod
    def from_defaults(cls, **kwargs: Optional[int]) -> 'Progress':
        return cls(total=Tracker(**kwargs), current=Tracker(**kwargs))


@dataclass
class LoopProgress:
    """
    Track loop progress during execution.

    These counters are local to a trainer rank. By default, they are not globally synced across all ranks.

    Args:
        epoch: Tracks epochs progress.
        batch: Tracks batch progress.
    """
    epoch: Progress = field(default_factory=Progress)
    batch: Progress = field(default_factory=Progress)

    def increment_epoch_completed(self) -> None:
        self.epoch.increment_completed()
        self.reset_on_epoch()

    def reset_on_epoch(self) -> None:
        self.batch.current.reset()
        self.epoch.current.reset()


@dataclass
class OptimizationProgress:
    """
    Track optimization progress.

    Args:
        optimizer: Tracks optimizer progress.
        scheduler: Tracks scheduler progress.
    """
    optimizer: Progress = Progress.from_defaults(processed=None)
    scheduler: Progress = Progress.from_defaults(started=None, processed=None)
    zero_grad: Progress = Progress.from_defaults(processed=None)

    @property
    def optimizer_steps(self) -> int:
        return self.optimizer.total.completed

    @property
    def scheduler_steps(self) -> int:
        return self.scheduler.total.completed


@dataclass
class BatchLoopProgress:

    batch: Progress = field(default_factory=Progress)
    optimizer_idx: Optional[int] = field(default_factory=int)
    num_optimizers: int = field(default=1, repr=False)
    optimizations: Tuple[OptimizationProgress, ...] = field(init=False)

    def __post_init__(self):
        # todo (tchaton) weird bug where ``OptimizationProgress`` share same counters if deepcopy is not used.
        self.optimizations = tuple(deepcopy(OptimizationProgress()) for _ in range(self.num_optimizers))

    def reset_on_batch(self) -> None:
        for opt in self.optimizations:
            opt.optimizer.current.reset()
            opt.scheduler.current.reset()
            opt.zero_grad.current.reset()
        self.batch.current.reset()


@dataclass
class TrainingLoopProgress(LoopProgress):

    epoch: Progress = field(default_factory=Progress)
    batch_loop: BatchLoopProgress = field(default_factory=BatchLoopProgress)

    def increment_epoch_completed(self) -> None:
        self.epoch.increment_completed()
        self.reset_on_epoch()

    def reset_on_batch(self) -> None:
        if self.batch_loop.optimizations is not None:
            for opt in self.batch_loop.optimizations:
                opt.optimizer.current.reset()
                opt.scheduler.current.reset()
                opt.zero_grad.current.reset()

    def reset_on_epoch(self) -> None:
        # override to avoid resetting `epoch.current`
        self.batch_loop.reset_on_batch()


@dataclass
class FitLoopProgress:
    train: TrainingLoopProgress = field(default_factory=TrainingLoopProgress)
    val: LoopProgress = field(default_factory=LoopProgress)