"""PPO with KL to frozen S1 in the same optimizer objective.

The train method follows installed Stable Baselines3 2.9.0
(stable_baselines3/ppo/ppo.py, MIT license) with an additional KL loss.
Source: https://github.com/DLR-RM/stable-baselines3/blob/v2.9.0/stable_baselines3/ppo/ppo.py
Disabled/empty anchors use upstream PPO.train directly.
"""
# The MIT License
# Copyright (c) 2019 Antonin Raffin
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
from __future__ import annotations

import numpy as np
import torch as th
from torch.nn import functional as F
from gymnasium import spaces
from stable_baselines3 import PPO
from stable_baselines3.common.utils import explained_variance


class AnchorPPO(PPO):
    def __init__(self, *args, **kwargs):
        self._anchor_policy = None
        self._anchor_coef = 0.0
        self._anchor_obs_s2 = th.empty(0)
        self._anchor_obs_s1 = th.empty(0)
        self.anchor_kl_before = self.anchor_kl_after = 0.0
        self.anchor_kl_objective = self.anchor_policy_loss = self.anchor_grad_norm = 0.0
        self.anchor_epochs_completed = self.anchor_optimizer_steps = 0
        self.anchor_early_stopped = False
        super().__init__(*args, **kwargs)

    def _excluded_save_params(self):
        # A checkpoint contains trainable PPO state only. Reattach explicit S1 on
        # resume, never pickle a teacher or a rollout into a result checkpoint.
        return super()._excluded_save_params() + [
            "_anchor_policy", "_anchor_coef", "_anchor_obs_s2", "_anchor_obs_s1",
        ]

    def set_anchor_samples(self, policy, obs_s2, obs_s1, coef):
        if not isinstance(self.action_space, spaces.Box) or self.use_sde:
            raise ValueError("objective anchor requires Box actions without gSDE")
        self._anchor_policy = policy
        self._anchor_coef = coef
        self._anchor_obs_s2 = th.as_tensor(obs_s2, dtype=th.float32, device=self.device)
        self._anchor_obs_s1 = th.as_tensor(obs_s1, dtype=th.float32, device=self.device)
        self.anchor_kl_before = self.anchor_kl_after = 0.0

    def _anchor_kl(self, indices):
        with th.no_grad():
            frozen = self._anchor_policy.get_distribution(self._anchor_obs_s1[indices]).distribution
        current = self.policy.get_distribution(self._anchor_obs_s2[indices]).distribution
        return th.distributions.kl_divergence(frozen, current).sum(dim=-1)

    def anchor_loss(self, batch_size):
        indices = th.randint(len(self._anchor_obs_s2), (batch_size,), device=self.device)
        return self._anchor_kl(indices).mean()

    def mean_anchor_kl(self):
        if not len(self._anchor_obs_s2):
            return 0.0
        with th.no_grad():
            total = sum(self._anchor_kl(slice(i, i + self.batch_size)).sum().item()
                        for i in range(0, len(self._anchor_obs_s2), self.batch_size))
        return total / len(self._anchor_obs_s2)

    def train(self) -> None:
        """
        Update policy using the currently gathered rollout buffer.
        """
        self.anchor_kl_objective = self.anchor_policy_loss = self.anchor_grad_norm = 0.0
        self.anchor_epochs_completed = self.anchor_optimizer_steps = 0
        self.anchor_early_stopped = False
        if self._anchor_policy is None or self._anchor_coef <= 0 or len(self._anchor_obs_s2) == 0:
            return super().train()
        self.anchor_kl_before = self.mean_anchor_kl()
        if not any(p.requires_grad for p in self.policy.action_net.parameters()):
            # Critic warmup has no actor gradient: skip KL and its RNG draws.
            super().train()
            self.anchor_kl_after = self.mean_anchor_kl()
            return
        anchor_losses = []
        grad_norms = []
        # Switch to train mode (this affects batch norm / dropout)
        self.policy.set_training_mode(True)
        # Update optimizer learning rate
        self._update_learning_rate(self.policy.optimizer)
        # Compute current clip range
        clip_range = self.clip_range(self._current_progress_remaining)  # type: ignore[operator]
        # Optional: clip range for the value function
        if self.clip_range_vf is not None:
            clip_range_vf = self.clip_range_vf(self._current_progress_remaining)  # type: ignore[operator]

        entropy_losses = []
        pg_losses, value_losses = [], []
        clip_fractions = []

        continue_training = True
        # train for n_epochs epochs
        for epoch in range(self.n_epochs):
            approx_kl_divs = []
            # Do a complete pass on the rollout buffer
            for rollout_data in self.rollout_buffer.get(self.batch_size):
                actions = rollout_data.actions
                if isinstance(self.action_space, spaces.Discrete):
                    # Convert discrete action from float to long
                    actions = rollout_data.actions.long().flatten()

                values, log_prob, entropy = self.policy.evaluate_actions(rollout_data.observations, actions)
                values = values.flatten()
                # Normalize advantage
                advantages = rollout_data.advantages
                # Normalization does not make sense if mini batchsize == 1, see GH issue #325
                if self.normalize_advantage and len(advantages) > 1:
                    advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)

                # ratio between old and new policy, should be one at the first iteration
                ratio = th.exp(log_prob - rollout_data.old_log_prob)

                # clipped surrogate loss
                policy_loss_1 = advantages * ratio
                policy_loss_2 = advantages * th.clamp(ratio, 1 - clip_range, 1 + clip_range)
                policy_loss = -th.min(policy_loss_1, policy_loss_2).mean()

                # Logging
                pg_losses.append(policy_loss.item())
                clip_fraction = th.mean((th.abs(ratio - 1) > clip_range).float()).item()
                clip_fractions.append(clip_fraction)

                if self.clip_range_vf is None:
                    # No clipping
                    values_pred = values
                else:
                    # Clip the difference between old and new value
                    # NOTE: this depends on the reward scaling
                    values_pred = rollout_data.old_values + th.clamp(
                        values - rollout_data.old_values, -clip_range_vf, clip_range_vf
                    )
                # Value loss using the TD(gae_lambda) target
                value_loss = F.mse_loss(rollout_data.returns, values_pred)
                value_losses.append(value_loss.item())

                # Entropy loss favor exploration
                if entropy is None:
                    # Approximate entropy when no analytical form
                    entropy_loss = -th.mean(-log_prob)
                else:
                    entropy_loss = -th.mean(entropy)

                entropy_losses.append(entropy_loss.item())

                loss = policy_loss + self.ent_coef * entropy_loss + self.vf_coef * value_loss
                # Independent uniform samples from the eligible rollout states estimate
                # E[KL(S1 || S2) | recoverable, upright]. No PPO-buffer index coupling.
                anchor_kl = self.anchor_loss(len(rollout_data.observations))
                anchor_losses.append(anchor_kl.item())
                loss = loss + self._anchor_coef * anchor_kl

                # Calculate approximate form of reverse KL Divergence for early stopping
                # see issue #417: https://github.com/DLR-RM/stable-baselines3/issues/417
                # and discussion in PR #419: https://github.com/DLR-RM/stable-baselines3/pull/419
                # and Schulman blog: http://joschu.net/blog/kl-approx.html
                with th.no_grad():
                    log_ratio = log_prob - rollout_data.old_log_prob
                    approx_kl_div = th.mean((th.exp(log_ratio) - 1) - log_ratio).cpu().numpy()
                    approx_kl_divs.append(approx_kl_div)

                if self.target_kl is not None and approx_kl_div > 1.5 * self.target_kl:
                    continue_training = False
                    self.anchor_early_stopped = True
                    if self.verbose >= 1:
                        print(f"Early stopping at step {epoch} due to reaching max kl: {approx_kl_div:.2f}")
                    break

                # Optimization step
                self.policy.optimizer.zero_grad()
                loss.backward()
                # Clip grad norm
                grad_norm = th.nn.utils.clip_grad_norm_(self.policy.parameters(), self.max_grad_norm)
                grad_norms.append(float(grad_norm))
                self.policy.optimizer.step()
                self.anchor_optimizer_steps += 1

            self._n_updates += 1
            self.anchor_epochs_completed += int(continue_training)
            if not continue_training:
                break

        explained_var = explained_variance(self.rollout_buffer.values.flatten(), self.rollout_buffer.returns.flatten())

        # Logs
        self.logger.record("train/entropy_loss", np.mean(entropy_losses))
        self.logger.record("train/policy_gradient_loss", np.mean(pg_losses))
        self.logger.record("train/value_loss", np.mean(value_losses))
        self.logger.record("train/approx_kl", np.mean(approx_kl_divs))
        self.logger.record("train/clip_fraction", np.mean(clip_fractions))
        self.logger.record("train/loss", loss.item())
        self.logger.record("train/explained_variance", explained_var)
        if hasattr(self.policy, "log_std"):
            self.logger.record("train/std", th.exp(self.policy.log_std).mean().item())

        self.logger.record("train/n_updates", self._n_updates, exclude="tensorboard")
        self.logger.record("train/clip_range", clip_range)
        if self.clip_range_vf is not None:
            self.logger.record("train/clip_range_vf", clip_range_vf)

        self.anchor_kl_after = self.mean_anchor_kl()
        self.anchor_kl_objective = float(np.mean(anchor_losses))
        self.anchor_policy_loss = float(np.mean(pg_losses))
        self.anchor_grad_norm = float(np.mean(grad_norms)) if grad_norms else 0.0
        self.logger.record("train/anchor_kl", np.mean(anchor_losses))
