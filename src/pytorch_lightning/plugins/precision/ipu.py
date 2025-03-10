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
from typing import Any, Callable, Union, List, Tuple

from lightning_utilities.core.rank_zero import WarningCache
from torch import Tensor
from torch.nn import Module
from torch.optim import LBFGS, Optimizer

import pytorch_lightning as pl
from lightning_lite.utilities.enums import PrecisionType
from lightning_lite.utilities.types import Optimizable
from pytorch_lightning.plugins.precision.precision_plugin import PrecisionPlugin
from pytorch_lightning.utilities import GradClipAlgorithmType
from pytorch_lightning.utilities.exceptions import MisconfigurationException
from pytorch_lightning.utilities.model_helpers import is_overridden

warning_cache = WarningCache()


class IPUPrecisionPlugin(PrecisionPlugin):
    """Precision plugin for IPU integration.

    Raises:
        ValueError:
            If the precision is neither 16 nor 32.
    """

    def __init__(self, precision: int) -> None:
        supported_precision_values = (PrecisionType.HALF, PrecisionType.FLOAT)
        if precision not in supported_precision_values:
            raise ValueError(
                f"`Trainer(accelerator='ipu', precision={precision!r})` is not supported."
                f" `precision` must be one of: {supported_precision_values}."
            )
        super().__init__()
        self.precision = precision

    def connect(
        self, model: Module, optimizers: List[Optimizer], lr_schedulers: List[Any]
    ) -> Tuple[Module, List[Optimizer], List[Any]]:
        if self.precision == PrecisionType.HALF:
            model = model.half()
        """Connects this plugin to the accelerator and the training process."""
        return model, optimizers, lr_schedulers

    def backward(  # type: ignore[override]
        self,
        tensor: Tensor,
        model: "pl.LightningModule",
        *args: Any,
        **kwargs: Any,
    ) -> None:
        if is_overridden("backward", model):
            warning_cache.warn(
                "You have overridden the `LightningModule.backward` hook but it will be ignored since IPUs handle"
                " the backward logic internally."
            )

    def optimizer_step(  # type: ignore[override]
        self,
        optimizer: Optimizable,
        model: "pl.LightningModule",
        optimizer_idx: int,
        closure: Callable[[], Any],
        **kwargs: Any,
    ) -> Any:
        """IPUs handle the optimizer step internally."""
        if isinstance(optimizer, LBFGS):
            raise MisconfigurationException(
                f"IPUs and the LBFGS optimizer are not compatible (optimizer {optimizer_idx})."
            )
        closure_result = closure()
        self._after_closure(model, optimizer, optimizer_idx)
        skipped_backward = closure_result is None
        # in manual optimization, the closure does not return a value
        if model.automatic_optimization and skipped_backward:
            # we lack coverage here and IPUs are (currently) limited - something to explore if there's demand
            raise MisconfigurationException(
                "Skipping backward by returning `None` from your `training_step` is not implemented for IPUs."
                " Please, open an issue in `https://github.com/Lightning-AI/lightning/issues`"
                " requesting this feature."
            )
        return closure_result

    def clip_gradients(
        self,
        optimizer: Optimizer,
        clip_val: Union[int, float] = 0.0,
        gradient_clip_algorithm: GradClipAlgorithmType = GradClipAlgorithmType.NORM,
    ) -> None:
        if clip_val <= 0:
            return
        raise MisconfigurationException("IPUs currently do not support clipping gradients.")
