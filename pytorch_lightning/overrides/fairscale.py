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
from pytorch_lightning.core.lightning import LightningModule
from pytorch_lightning.overrides.base import _LightningModuleWrapperBase, unwrap_lightning_module
from pytorch_lightning.utilities import _FAIRSCALE_AVAILABLE, _FAIRSCALE_FULL_SHARDED_AVAILABLE

LightningShardedDataParallel = None
if _FAIRSCALE_AVAILABLE:
    from fairscale.nn.data_parallel.sharded_ddp import ShardedDataParallel

    class LightningShardedDataParallel(_LightningModuleWrapperBase):
        # Just do this for later docstrings
        pass

    def unwrap_lightning_module_sharded(wrapped_model) -> LightningModule:
        model = wrapped_model
        if isinstance(model, ShardedDataParallel):
            model = model.module

        return unwrap_lightning_module(model)


LightningFullShardedDataParallel = None
if _FAIRSCALE_FULL_SHARDED_AVAILABLE:
    from fairscale.nn import FlattenParamsWrapper
    from fairscale.nn.data_parallel import FullyShardedDataParallel

    class LightningFullShardedDataParallel(_LightningModuleWrapperBase):
        # Just do this for later docstrings
        pass

    def unwrap_lightning_module_full_sharded(wrapped_model) -> LightningModule:
        model = wrapped_model
        if isinstance(model, FullyShardedDataParallel):
            model = model.module
        # Additional check if we're using a flattened parameters buffer
        if isinstance(model, FlattenParamsWrapper):
            model = model.module
        return unwrap_lightning_module(model)
