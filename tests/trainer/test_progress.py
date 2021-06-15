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
import pytest
import torch

from pytorch_lightning import Trainer
from pytorch_lightning.callbacks import ModelCheckpoint
from pytorch_lightning.trainer.progress import FitLoopProgress, LoopProgress, Progress, Tracker, TrainingLoopProgress
from tests.helpers import BoringModel


def test_progress_geattr_setattr():
    p = Tracker(ready=10, completed=None)
    # can read
    assert p.completed is None
    # can't read non-existing attr
    with pytest.raises(AttributeError, match="object has no attribute 'non_existing_attr'"):
        p.non_existing_attr  # noqa
    # can set new attr
    p.non_existing_attr = 10
    # can't write unused attr
    with pytest.raises(AttributeError, match="'completed' attribute is meant to be unused"):
        p.completed = 10
    with pytest.raises(TypeError, match="unsupported operand type"):
        # default python error, would need to override `__getattribute__`
        # but we want to allow reading the `None` value
        p.completed += 10


def test_progress_reset():
    p = Tracker(ready=1, started=2, completed=None)
    p.reset()
    assert p == Tracker(completed=None)


def test_progress_repr():
    assert repr(Tracker(ready=None, started=None)) == "Tracker(processed=0, completed=0)"


@pytest.mark.parametrize("attr", ("ready", "started", "processed", "completed"))
def test_base_progress_increment(attr):
    p = Progress()
    fn = getattr(p, f"increment_{attr}")
    fn()
    expected = Tracker(**{attr: 1})
    assert p.total == expected
    assert p.current == expected


def test_base_progress_from_defaults():
    actual = Progress.from_defaults(completed=5, started=None)
    expected = Progress(total=Tracker(started=None, completed=5), current=Tracker(started=None, completed=5))
    assert actual == expected


def test_loop_progress_increment_epoch():
    p = LoopProgress()
    p.increment_epoch_completed()
    p.increment_epoch_completed()
    assert p.epoch.total == Tracker(completed=2)
    assert p.epoch.current == Tracker()
    assert p.batch.current == Tracker()


def test_loop_progress_increment_sequence():
    """ Test sequences for incrementing batches reads and epochs. """
    p = LoopProgress(batch=Progress(total=Tracker(started=None)))

    p.batch.increment_ready()
    assert p.batch.total == Tracker(ready=1, started=None)
    assert p.batch.current == Tracker(ready=1)

    p.batch.increment_started()
    assert p.batch.total == Tracker(ready=1, started=None)
    assert p.batch.current == Tracker(ready=1)

    p.batch.increment_processed()
    assert p.batch.total == Tracker(ready=1, started=None, processed=1)
    assert p.batch.current == Tracker(ready=1, processed=1)

    p.batch.increment_completed()
    assert p.batch.total == Tracker(ready=1, started=None, processed=1, completed=1)
    assert p.batch.current == Tracker(ready=1, processed=1, completed=1)

    assert p.epoch.total == Tracker()
    assert p.epoch.current == Tracker()
    p.increment_epoch_completed()
    assert p.batch.total == Tracker(ready=1, started=None, processed=1, completed=1)
    assert p.batch.current == Tracker()
    assert p.epoch.total == Tracker(completed=1)
    assert p.epoch.current == Tracker()

    p.batch.increment_ready()
    assert p.batch.total == Tracker(ready=2, started=None, processed=1, completed=1)
    assert p.batch.current == Tracker(ready=1)
    assert p.epoch.total == Tracker(completed=1)
    assert p.epoch.current == Tracker()

    p.reset_on_epoch()
    assert p.batch.total == Tracker(ready=2, started=None, processed=1, completed=1)
    assert p.batch.current == Tracker()
    assert p.epoch.total == Tracker(completed=1)
    assert p.epoch.current == Tracker()


@pytest.mark.parametrize("use_multiple_optimizers", [True])
def test_progress_tracking(use_multiple_optimizers, tmpdir):
    """
    This test verify that progress is correctly incremented during using FitLoop.
    """

    class TestModel(BoringModel):

        def __init__(self, use_multiple_optimizers: bool):
            super().__init__()
            if use_multiple_optimizers:
                self.configure_optimizers = self.configure_optimizers_3

        def training_step(self, batch, batch_idx, optimizer_idx: int = None):
            return super().training_step(batch, batch_idx)

        def configure_optimizers_3(self):
            optimizer = torch.optim.SGD(self.layer.parameters(), lr=0.1)
            lr_scheduler = torch.optim.lr_scheduler.StepLR(optimizer, step_size=1)
            optimizer_1 = torch.optim.Adam(self.layer.parameters(), lr=0.1)
            lr_scheduler_1 = torch.optim.lr_scheduler.StepLR(optimizer_1, step_size=1)
            optimizer_2 = torch.optim.Adam(self.layer.parameters(), lr=0.1)
            return [optimizer, optimizer_1,
                    optimizer_2], [lr_scheduler, {
                        "scheduler": lr_scheduler_1,
                        "interval": "step"
                    }]

    model = TestModel(use_multiple_optimizers)
    model.training_epoch_end = None

    chk = ModelCheckpoint(dirpath=tmpdir, save_last=True)

    trainer = Trainer(default_root_dir=tmpdir, max_epochs=2, limit_train_batches=3, limit_val_batches=0, callbacks=chk)

    trainer.fit(model)

    assert isinstance(trainer.fit_loop.progress, FitLoopProgress)
    assert isinstance(trainer.fit_loop.training_loop.progress, TrainingLoopProgress)
    assert trainer.fit_loop.training_loop.progress is trainer.fit_loop.progress.train

    pr = trainer.fit_loop.training_loop.progress

    assert pr.epoch.total == Tracker(ready=2, started=2, processed=2, completed=2)
    assert pr.epoch.current == Tracker(ready=2, started=2, processed=2, completed=2)

    pr = trainer.fit_loop.training_loop.batch_loop.progress

    assert pr.batch.total == Tracker(ready=6, started=6, processed=6, completed=6)
    assert pr.batch.current == Tracker(ready=1, started=1, processed=1, completed=1)

    num_optimizers = 3 if use_multiple_optimizers else 1
    for opt_idx in range(num_optimizers):

        assert pr.optimizations[opt_idx].optimizer.total == Tracker(ready=6, started=6, processed=None, completed=6)
        assert pr.optimizations[opt_idx].optimizer.current == Tracker(ready=1, started=1, processed=None, completed=1)

        assert pr.optimizations[opt_idx].zero_grad.total == Tracker(ready=6, started=6, processed=None, completed=6)
        assert pr.optimizations[opt_idx].zero_grad.current == Tracker(ready=1, started=1, processed=None, completed=1)

        if use_multiple_optimizers:
            if opt_idx == 0:
                # update on epoch
                assert pr.optimizations[opt_idx].scheduler.total == Tracker(
                    ready=2, started=None, processed=None, completed=2
                )
                assert pr.optimizations[opt_idx].scheduler.current == Tracker(
                    ready=1, started=None, processed=None, completed=1
                )
            elif opt_idx == 1:
                # update on steps
                assert pr.optimizations[opt_idx].scheduler.total == Tracker(
                    ready=6, started=None, processed=None, completed=6
                )
                assert pr.optimizations[opt_idx].scheduler.current == Tracker(
                    ready=1, started=None, processed=None, completed=1
                )
            else:
                # no optimizer
                assert pr.optimizations[opt_idx].scheduler.total == Tracker(
                    ready=0, started=None, processed=None, completed=0
                )
                assert pr.optimizations[opt_idx].scheduler.current == Tracker(
                    ready=0, started=None, processed=None, completed=0
                )
        else:
            assert pr.optimizations[opt_idx].scheduler.total == Tracker(
                ready=2, started=None, processed=None, completed=2
            )
            assert pr.optimizations[opt_idx].scheduler.current == Tracker(
                ready=1, started=None, processed=None, completed=1
            )

    assert pr.optimizer_idx == (2 if use_multiple_optimizers else 0)

    progress = trainer.fit_loop.progress

    trainer = Trainer(
        default_root_dir=tmpdir,
        max_epochs=3,
        limit_train_batches=3,
        limit_val_batches=0,
        resume_from_checkpoint=chk.last_model_path
    )

    # todo: (tchaton)  Update this when restore progress is supported.
    trainer.fit_loop.progress = progress
    trainer.fit_loop.training_loop.progress = progress.train

    trainer.fit(model)

    pr = trainer.fit_loop.training_loop.progress

    assert pr.epoch.total == Tracker(ready=3, started=3, processed=3, completed=3)
    assert pr.epoch.current == Tracker(ready=1, started=1, processed=1, completed=1)