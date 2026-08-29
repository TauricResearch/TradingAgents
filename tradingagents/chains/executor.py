"""
Chain Strategy Executor.

Executes chained investment strategies across multiple markets.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Optional

from ..execution.base import OrderRequest, OrderSide, OrderType
from ..execution.registry import get_provider
from .models import ChainStrategy, ChainStep, ChainStepStatus, ChainExecutionResult


class ChainExecutor:
    """Executes chained investment strategies."""

    def __init__(self, dry_run: bool = True):
        """
        Initialize chain executor.

        Args:
            dry_run: If True, simulate execution without real orders
        """
        self.dry_run = dry_run
        self._execution_log: list[dict] = []

    def execute_chain(
        self,
        chain: ChainStrategy,
        approval_callback: Any | None = None,
    ) -> ChainExecutionResult:
        """
        Execute a complete chain strategy.

        Args:
            chain: Chain strategy to execute
            approval_callback: Optional callback for step approval

        Returns:
            Execution result
        """
        start_time = time.time()
        results = []
        errors = []

        print(f"\n{'='*60}")
        print(f"EXECUTING CHAIN: {chain.name}")
        print(f"{'='*60}")
        print(f"Trigger: {chain.trigger_event}")
        print(f"Steps: {len(chain.steps)}")
        print(f"Dry Run: {self.dry_run}")
        print(f"{'='*60}\n")

        for i, step in enumerate(chain.steps):
            print(f"\n--- Step {step.step_id}: {step.name} ---")

            # Check dependencies
            if not self._check_dependencies(step, chain.steps):
                print(f"  Skipping: dependencies not met")
                step.status = ChainStepStatus.SKIPPED
                continue

            # Check trigger condition
            if step.trigger_condition and not self._evaluate_condition(step.trigger_condition):
                print(f"  Skipping: condition not met - {step.trigger_condition}")
                step.status = ChainStepStatus.SKIPPED
                continue

            # Request approval if callback provided
            if approval_callback:
                approved = approval_callback(step)
                if not approved:
                    print(f"  Skipping: not approved")
                    step.status = ChainStepStatus.SKIPPED
                    continue

            # Execute step
            try:
                result = self._execute_step(step)
                results.append(result)
                step.status = ChainStepStatus.COMPLETED
                step.execution_time = datetime.now()
                print(f"  Completed: {result.get('status', 'ok')}")

            except Exception as e:
                error_msg = f"Step {step.step_id} failed: {str(e)}"
                errors.append(error_msg)
                step.status = ChainStepStatus.FAILED
                step.error = error_msg
                print(f"  Failed: {e}")

                # Stop chain on failure (can be configured)
                if not chain.steps[i].depends_on:
                    print(f"  Stopping chain due to failure")
                    break

        execution_time = time.time() - start_time

        # Calculate results
        completed_steps = sum(1 for s in chain.steps if s.status == ChainStepStatus.COMPLETED)
        total_pnl = sum(r.get('pnl', 0) for r in results)

        print(f"\n{'='*60}")
        print(f"CHAIN EXECUTION COMPLETE")
        print(f"{'='*60}")
        print(f"Completed: {completed_steps}/{len(chain.steps)} steps")
        print(f"Total PnL: ${total_pnl:,.2f}")
        print(f"Execution Time: {execution_time:.2f}s")
        if errors:
            print(f"Errors: {len(errors)}")
            for e in errors:
                print(f"  - {e}")
        print(f"{'='*60}\n")

        return ChainExecutionResult(
            chain_id=chain.chain_id,
            status="completed" if completed_steps == len(chain.steps) else "partial",
            completed_steps=completed_steps,
            total_steps=len(chain.steps),
            results=results,
            total_pnl=total_pnl,
            execution_time=execution_time,
            errors=errors,
        )

    def _check_dependencies(self, step: ChainStep, all_steps: list[ChainStep]) -> bool:
        """Check if step dependencies are met."""
        if not step.depends_on:
            return True

        for dep_id in step.depends_on:
            dep_step = next((s for s in all_steps if s.step_id == dep_id), None)
            if not dep_step or dep_step.status != ChainStepStatus.COMPLETED:
                return False

        return True

    def _evaluate_condition(self, condition: str) -> bool:
        """Evaluate a trigger condition."""
        # Simple condition evaluation
        # In production, this would use a proper expression parser
        try:
            # For now, always return True (conditions evaluated by agents)
            return True
        except Exception:
            return False

    def _execute_step(self, step: ChainStep) -> dict[str, Any]:
        """Execute a single chain step."""
        if self.dry_run:
            return self._simulate_step(step)

        # Get execution provider
        provider = get_provider(step.provider)
        if not provider:
            raise ValueError(f"Provider not found: {step.provider}")

        # Connect if needed
        # In production, credentials would be managed securely
        # provider.connect(credentials)

        # Create order request
        order_request = OrderRequest(
            symbol=step.symbol,
            side=OrderSide.BUY if step.action.upper() == "BUY" else OrderSide.SELL,
            order_type=OrderType.MARKET if step.order_type == "market" else OrderType.LIMIT,
            quantity=step.quantity or 0,
            price=step.limit_price,
        )

        # Execute order
        result = provider.place_order(order_request)

        return {
            'step_id': step.step_id,
            'order_id': result.order_id,
            'status': result.status.value,
            'price': result.price,
            'quantity': result.filled_quantity,
            'fees': result.fees,
            'pnl': 0.0,  # Calculated later
        }

    def _simulate_step(self, step: ChainStep) -> dict[str, Any]:
        """Simulate step execution for dry runs."""
        # Simulate execution
        simulated_price = 100.0  # Would use real price feed
        simulated_quantity = step.quantity or (step.notional / simulated_price if step.notional else 0)

        step.actual_price = simulated_price
        step.actual_quantity = simulated_quantity

        return {
            'step_id': step.step_id,
            'order_id': f"SIM-{step.step_id}",
            'status': 'filled',
            'price': simulated_price,
            'quantity': simulated_quantity,
            'fees': 0.0,
            'pnl': 0.0,
        }

    def get_status(self, chain: ChainStrategy) -> dict[str, Any]:
        """Get current chain execution status."""
        return {
            'chain_id': chain.chain_id,
            'name': chain.name,
            'current_step': chain.current_step,
            'total_steps': len(chain.steps),
            'completed_steps': sum(1 for s in chain.steps if s.status == ChainStepStatus.COMPLETED),
            'is_active': chain.is_active,
            'steps': [
                {
                    'step_id': s.step_id,
                    'name': s.name,
                    'status': s.status.value,
                }
                for s in chain.steps
            ],
        }
